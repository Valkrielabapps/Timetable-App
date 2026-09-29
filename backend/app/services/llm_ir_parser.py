"""
Parse a school's free-text rule into the IR (app/services/constraint_ir.py).

The legacy parser in llm_constraint_parser.py asks the model to pick one of
nine named types, so a sentence outside those nine has nowhere to go and lands
in `scheduling_rule` - recorded, shown, never applied. That was one rule in
seven of docs/research/constraint-catalogue.tsv.

Here the model is asked for a *shape* instead: which lessons the rule is about
(selector), what it is counted or compared over (scope), and which of five
arithmetic forms applies. Those compose, so rules nobody wrote a type for are
expressible without anyone adding one.

Two tools, and the model chooses
--------------------------------
`record_rule` is the normal path. `report_unclear` is the other half, and it is
not a failure path: with the IR the model can almost always produce something
well-formed, so the old "doesn't fit any type" signal that made a misreading
visible is gone. Left with only `record_rule`, a model handed "make the
timetable balanced and nice for everyone" will invent a rule rather than say it
cannot. Giving it somewhere honest to go is what keeps a confident guess from
becoming a constraint.

The same tool carries genuine ambiguity: "only 12th can use the physics lab in
the afternoon" has two readings that block opposite groups, and asking is the
only correct answer. See docs/research/constraint-traps.tsv.

Never raises; returns None if the LLM path can't be used at all, so the caller
can fall back exactly as it does today.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import settings
from app.services.constraint_ir import IRError, Rule, rule_from_dict
from app.services.constraint_ir_english import render
from app.services.llm_constraint_parser import _READING_RULES, _period_summary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

_SELECTOR_SCHEMA = {
    "type": ["object", "null"],
    "description": (
        "Which lessons this side of the rule is about. Fields are ANDed and "
        "values inside a field are ORed, so {subjects:['PE'], days:[4]} means "
        "PE lessons on Friday. Leave a field out to place no restriction on "
        "it; an empty selector means every lesson in the school, which is what "
        "rules about a teacher's total load need."
    ),
    "properties": {
        "subjects": {
            "type": ["array", "null"], "items": {"type": "string"},
            "description": "Subject names, exactly as given in the known list.",
        },
        "not_subjects": {
            "type": ["array", "null"], "items": {"type": "string"},
            "description": (
                "Subjects to EXCLUDE - use for phrases defined by what they are "
                "not, like 'theory periods' meaning everything except PE, Art, "
                "Music and Library."
            ),
        },
        "teachers": {
            "type": ["array", "null"], "items": {"type": "string"},
            "description": "Teacher names, exactly as given in the known list.",
        },
        "class_groups": {
            "type": ["array", "null"], "items": {"type": "string"},
            "description": (
                "Class group labels, exactly as given. A grade label like "
                "'Grade 8' covers every section in it; 'Grade 8 - A' is one "
                "section."
            ),
        },
        "days": {
            "type": ["array", "null"], "items": {"type": "integer"},
            "description": "0=Monday .. 6=Sunday.",
        },
        "period_orders": {
            "type": ["array", "null"], "items": {"type": "integer"},
            "description": (
                "Period numbers, using the numbering in the timetable structure "
                "above. Use for 'the first period', 'period 3', 'the last two "
                "periods', or a time of day resolved against the break "
                "positions."
            ),
        },
    },
}

_SCOPE_SCHEMA = {
    "type": ["array", "null"],
    "items": {"type": "string", "enum": ["teacher", "class_group", "subject", "day", "period"]},
    "description": (
        "The grouping the rule is applied over, separately for each group. This "
        "is the field that decides what a rule MEANS, so read it carefully:\n"
        "- ['teacher','day'] with count <= 6 is 'no teacher more than 6 periods "
        "in a DAY' (one check per teacher per day)\n"
        "- ['teacher'] with count <= 28 is 'no teacher more than 28 a WEEK'\n"
        "- ['class_group'] applies once per section\n"
        "- ['class_group','day'] applies per section per day\n"
        "- [] is a single check across the whole school\n"
        "Include 'day' whenever the sentence says 'in a day', 'daily' or 'that "
        "day'. Leave it out for weekly totals."
    ),
}

_RULE_TOOL = {
    "name": "record_rule",
    "description": "Record one school-timetabling rule in the general rule representation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "form": {
                "type": "string",
                "enum": ["count", "run", "adjacency", "bucket", "conditional"],
                "description": (
                    "count: how many matching periods there may be (also how you "
                    "say 'never' - relation '==' with value 0 - and 'at least "
                    "once' - relation '>=' with value 1). Most rules are counts.\n"
                    "run: how many matching periods may sit back to back, or that "
                    "they must come as a block.\n"
                    "adjacency: how close two DIFFERENT sets of lessons may be.\n"
                    "bucket: whether two sets share a day, or must happen at the "
                    "same time as each other.\n"
                    "conditional: apply a rule only where another count holds."
                ),
            },
            "scope": _SCOPE_SCHEMA,
            "selector": _SELECTOR_SCHEMA,
            "relation": {
                "type": ["string", "null"], "enum": ["<=", ">=", "==", None],
                "description": (
                    "For count. '<=' for caps ('no more than 6'), '>=' for "
                    "minimums ('at least one'), '==' for exact ('never' is '==' "
                    "with 0). 'less than 6' is '<=' with 5."
                ),
            },
            "value": {"type": ["integer", "null"], "description": "For count: the number."},
            "distinct": {
                "type": ["string", "null"], "enum": ["subject", "teacher", "class_group", None],
                "description": (
                    "For count, when the sentence counts KINDS rather than "
                    "periods: 'at most 6 different subjects a day' is "
                    "distinct='subject'. Leave null to count periods."
                ),
            },
            "max_consecutive": {
                "type": ["integer", "null"],
                "description": (
                    "For run: the most matching periods allowed back to back. 'No "
                    "double English' is 1. Use this, not adjacency, when both "
                    "sides are the same subject."
                ),
            },
            "block_size": {
                "type": ["integer", "null"],
                "description": (
                    "For run: the subject must be scheduled in blocks of this "
                    "many consecutive periods, e.g. a practical needing a double."
                ),
            },
            "first": {**_SELECTOR_SCHEMA, "description":
                      "For adjacency and bucket: the first-named set of lessons."},
            "second": {**_SELECTOR_SCHEMA, "description":
                       "For adjacency and bucket: the second-named set."},
            "min_gap": {
                "type": ["integer", "null"],
                "description": (
                    "For adjacency: how many periods must separate the two. 1 "
                    "means they may not be back to back (periods 1 and 3 are "
                    "fine, 1 and 2 are not)."
                ),
            },
            "directional": {
                "type": ["boolean", "null"],
                "description": (
                    "For adjacency. true when only ONE order is forbidden - "
                    "'Maths can't come right after PE' (first=PE, second=Maths) "
                    "says nothing about PE after Maths. false when the sentence "
                    "is symmetric, like 'X and Y shouldn't be next to each "
                    "other'. Getting this wrong makes the rule stricter or looser "
                    "than what was asked."
                ),
            },
            "must_follow": {
                "type": ["boolean", "null"],
                "description": (
                    "For adjacency: true when `second` MUST come in the period "
                    "straight after `first`, e.g. 'the practical should be right "
                    "after the theory class'."
                ),
            },
            "dimension": {
                "type": ["string", "null"], "enum": ["day", "period", None],
                "description": (
                    "For bucket: 'day' for rules about sharing a day, 'period' "
                    "for rules about happening at the same time."
                ),
            },
            "bucket_relation": {
                "type": ["string", "null"], "enum": ["same", "different", None],
                "description": "For bucket: whether the two sets must share the dimension or not.",
            },
            "when": {
                "type": ["object", "null"],
                "description": (
                    "For conditional: a count that says when the rule applies, as "
                    "{scope, selector, relation, value}. 'On days Priya teaches "
                    "Grade 12' is scope ['teacher','day'], selector "
                    "{teachers:['Priya'], class_groups:['Grade 12']}, '>=' 1."
                ),
            },
            "then": {
                "type": ["object", "null"],
                "description": (
                    "For conditional: the rule to apply where `when` holds, as a "
                    "full rule object including its own `form`."
                ),
            },
            "strength": {
                "type": ["string", "null"],
                "enum": ["required", "strong_preference", "preference", None],
                "description": (
                    "'required' for must/cannot/never - the timetable is invalid "
                    "if broken. 'preference' for prefer/ideally/try to/if "
                    "possible/where possible. 'strong_preference' for emphatic "
                    "hedging like 'really should'. Default to 'required' when the "
                    "sentence is flat with no hedging."
                ),
            },
            "description": {
                "type": "string",
                "description": "One short sentence restating the rule, for the UI.",
            },
        },
        "required": ["form", "description"],
    },
}

_UNCLEAR_TOOL = {
    "name": "report_unclear",
    "description": (
        "Use ONLY when you genuinely cannot tell which of two different rules "
        "was meant, when there is nothing measurable to enforce at all, or when "
        "a name has no match in the school's data.\n\n"
        "Do NOT use it because a rule is long, unusual, or has a detail you "
        "cannot capture exactly. A rule whose main effect you can state belongs "
        "in record_rule with that effect and a description saying what you left "
        "out - the admin sees your sentence and corrects it. Asking about a rule "
        "you could have expressed costs them more than an imperfect first "
        "attempt they can edit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "enum": ["ambiguous", "too_vague", "unknown_reference", "not_a_rule",
                         "contradictory", "not_supported"],
            },
            "explanation": {
                "type": "string",
                "description": (
                    "One or two sentences to the admin saying what is unclear, in "
                    "their words rather than ours - no mention of forms, scopes "
                    "or selectors."
                ),
            },
            "question": {
                "type": ["string", "null"],
                "description": "The single question that would resolve it, if one would.",
            },
            "readings": {
                "type": ["array", "null"], "items": {"type": "string"},
                "description": (
                    "When the text has two or more genuine readings, each stated "
                    "plainly so the admin can pick one."
                ),
            },
        },
        "required": ["reason", "explanation"],
    },
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

# Worked examples. These carry more of the model's accuracy than the field
# descriptions do: selector-and-scope is a way of thinking about a rule rather
# than a form to fill in, and it is learned from seeing rules decomposed. Drawn
# from docs/research/constraint-catalogue.tsv and chosen to span the forms and,
# more importantly, to contrast rules that sound alike and differ in scope.
_EXAMPLES = """Worked examples:

"No teacher should teach more than 6 periods in a day"
  form=count scope=["teacher","day"] selector={} relation="<=" value=6
  (scope has "day" because the cap is per day; selector is empty because it
  counts every lesson, whatever the subject)

"Priya should not have more than 28 periods a week"
  form=count scope=["teacher"] selector={teachers:["Priya"]} relation="<=" value=28
  (same form as above, no "day" in scope - that is the entire difference
  between a daily and a weekly cap)

"No PE on Fridays"
  form=count scope=["class_group"] selector={subjects:["PE"],days:[4]} relation="==" value=0

"Mrs. Rao doesn't come on Saturdays"
  form=count scope=[] selector={teachers:["Mrs. Rao"],days:[5]} relation="==" value=0

"Mr. Khan can't take the first period on Tuesdays"
  form=count scope=[] selector={teachers:["Mr. Khan"],days:[1],period_orders:[1]} relation="==" value=0

"Maths should always be the first period for Grade 10"
  form=count scope=["class_group"] selector={subjects:["Maths"],class_groups:["Grade 10"],period_orders:[1]} relation=">=" value=1

"Grade 6 can have at most 6 different subjects in a day"
  form=count scope=["class_group","day"] selector={class_groups:["Grade 6"]} relation="<=" value=6 distinct="subject"

"Not more than 2 Maths periods in a row"
  form=run scope=["class_group"] selector={subjects:["Maths"]} max_consecutive=2

"Chemistry practicals need two periods together"
  form=run scope=["class_group"] selector={subjects:["Chemistry"]} block_size=2

"Maths can't come right after PE"
  form=adjacency scope=["class_group"] first={subjects:["PE"]} second={subjects:["Maths"]} directional=true min_gap=1

"Maths and Science should never be back to back"
  form=adjacency scope=["class_group"] first={subjects:["Maths"]} second={subjects:["Science"]} directional=false min_gap=1

"Keep Physics and Chemistry on different days"
  form=bucket scope=["class_group"] first={subjects:["Physics"]} second={subjects:["Chemistry"]} dimension="day" bucket_relation="different"

"Biology and Computer Science for Grade 11 at the same time"
  form=bucket scope=[] first={subjects:["Biology"],class_groups:["Grade 11"]} second={subjects:["Computer Science"],class_groups:["Grade 11"]} dimension="period" bucket_relation="same"

"If Priya has a Grade 12 class that day, give her at most 5 periods"
  form=conditional scope=["teacher","day"]
    when={scope:["teacher","day"],selector:{teachers:["Priya"],class_groups:["Grade 12"]},relation:">=",value:1}
    then={form:"count",scope:["teacher","day"],selector:{teachers:["Priya"]},relation:"<=",value:5}

Informal rules reduce the same way. These all sound harder than they are:

"atleast 1 maths class every week shd be 1st period for all 10th sections"
  form=count scope=["class_group"] selector={subjects:["Maths"],class_groups:["Grade 10"],period_orders:[1]} relation=">=" value=1

"6th std max 6 diff subjects a day. bag weight complaint pannitanga parents again"
  form=count scope=["class_group","day"] selector={class_groups:["Grade 6"]} relation="<=" value=6 distinct="subject"
  (the reason for a rule is not part of the rule - read past it)

"priya takes english AND library for 7B. dont give her 7B more than twice a day"
  form=count scope=["teacher","day"] selector={teachers:["Priya"],class_groups:["Grade 7 - B"]} relation="<=" value=2
  (no subject filter: "counting all subjects together" is what an absent
  subjects field already means)

"every teacher needs atleast one light day mon to fri, 4 periods or less"
  form=count scope=["teacher","day"] selector={days:[0,1,2,3,4]} relation="<=" value=4 strength="preference"
  (the exact rule is "at least one such day", which cannot be said here. The
  main effect can, so record it and say in `description` that it applies to
  every weekday rather than to one - do not refuse over the gap)

"rao mam - on days she has 12th dont give her 10th also, too much prep switching"
  form=conditional scope=["teacher","day"]
    when={scope:["teacher","day"],selector:{teachers:["Mrs. Rao"],class_groups:["Grade 12"]},relation:">=",value:1}
    then={form:"count",scope:["teacher","day"],selector:{teachers:["Mrs. Rao"],class_groups:["Grade 10"]},relation:"==",value:0}

"Make the timetable balanced and nice for everyone"
  report_unclear, reason="too_vague" - "balanced" has no measurable meaning here.

"chem lab - need 1 perod gap between 2 practicals, suresh has to clean n set up"
  report_unclear, reason="not_supported" - this is about a room, which cannot
  be represented yet. Note that the reason is the room, not the phrasing."""


# What the representation genuinely cannot say yet, named so the model stops
# guessing at the boundary. Without this it has no way to tell "I have no field
# for rooms" from "this sentence is vague", so it reports both as vague - and,
# worse, generalises the caution to rules it could have expressed perfectly.
#
# Rooms and dates are deferred on purpose rather than missing by oversight:
# rooms are assigned in a pass after the schedule is fixed, and the timetable is
# a weekly pattern with no calendar behind it. Both need structural work in the
# solver, not a field here. See docs/research/README.md.
_OUT_OF_SCOPE = """Some rules cannot be represented at all yet. For these, use
report_unclear with reason='not_supported' and say plainly which part cannot be
handled - do not approximate them, and do not let them make you cautious about
anything else:
- rooms, labs, halls and equipment: which room a lesson uses, room capacity,
  two classes sharing a space, moving between buildings
- calendar dates: "from 20 January", "during exam week", "on 18 December",
  alternate Saturdays, anything tied to a date rather than a weekday
- groups of students inside a section: a few children exempted from a subject,
  wheelchair access, one batch going elsewhere
- ranking rules against each other, or limiting how much a rule may be broken

Everything else is in scope. In particular, a rule about how many periods a
teacher or a class has, when a subject may be placed, what may sit next to
what, what shares a day, or what happens only on certain days, can be
expressed - even when the sentence is long or informal."""


def _system_prompt(teacher_names, subject_names, class_group_labels, periods) -> str:
    return (
        "You turn one sentence from a school admin into a structured scheduling "
        "rule. A rule is three things: WHICH lessons it is about (selector), "
        "WHAT IT IS COUNTED OVER (scope), and which arithmetic form applies. "
        "Think about scope before anything else - it is what separates 'six "
        "periods a day' from 'six periods a week'.\n\n"
        "IMPORTANT - your answer is not applied straight away. It is rendered "
        "back into plain English and shown to the admin, who confirms, edits or "
        "rejects it before anything is saved. So an imperfect first attempt is "
        "cheap: they will see it and fix it. Refusing to answer is what costs "
        "them, because there is nothing to correct.\n\n"
        "Prefer record_rule. Reach for report_unclear only when two genuinely "
        "different rules are equally plausible, when there is nothing "
        "measurable to enforce, or when a name matches nothing in the school's "
        "data. If a rule has a clear main effect and a detail you cannot "
        "capture, record the main effect and say in `description` what you left "
        "out.\n\n"
        + _OUT_OF_SCOPE
        + "\n\n"
        f"Known teachers: {teacher_names}\n"
        f"Known subjects: {subject_names}\n"
        f"Known class groups (grades and sections): {class_group_labels}\n"
        + (f"{_period_summary(periods)}\n" if periods else "")
        + "\nOnly use names that appear verbatim in those lists. If a name in "
        "the text doesn't clearly match one, use report_unclear with "
        "reason='unknown_reference' rather than guessing which person was "
        "meant.\n\n"
        + _READING_RULES
        + "\n\n"
        + _EXAMPLES
    )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class Unclear:
    """The model declining to guess, with something the admin can act on."""

    reason: str
    explanation: str
    question: str | None = None
    readings: list[str] = field(default_factory=list)


@dataclass
class IRParse:
    """What one piece of text resolved to.

    Exactly one of `rule`, `unclear` and `invalid` is set. `sentence` is the
    rendered English for a rule - the thing the admin actually confirms - and is
    generated here so every caller shows the same words.

    `invalid` is kept apart from `unclear` even though an admin sees much the
    same message for both, because they are opposite facts about the system: a
    decline is the model working correctly, while an invalid rule is the model
    trying to answer and the schema or the prompt failing to carry the shape.
    Folding the second into the first hid 16 real defects behind a decline
    count in the second evaluation run - including rules that were verbatim
    examples in the prompt.
    """

    rule: Rule | None = None
    unclear: Unclear | None = None
    # The validator's complaint, verbatim. For a person this needs rewording;
    # for working out why a rule failed it is the only thing that helps.
    invalid: str | None = None
    sentence: str = ""


def _rule_payload(data: dict) -> dict:
    """Map the flat tool input onto the IR's nested shape.

    The tool is flat because a model fills a flat object more reliably than a
    discriminated union, and `bucket_relation` is spelled out rather than
    reusing `relation` so the two can't be confused when a bucket rule and a
    count rule appear in the same conversation.
    """
    payload = {
        "form": data.get("form"),
        "scope": data.get("scope") or [],
        "strength": data.get("strength") or "required",
        "description": data.get("description") or "",
    }
    form = payload["form"]

    if form == "count":
        payload.update({
            "selector": data.get("selector") or {},
            "relation": data.get("relation"),
            "value": data.get("value"),
            "distinct": data.get("distinct"),
        })
    elif form == "run":
        payload.update({
            "selector": data.get("selector") or {},
            "max_consecutive": data.get("max_consecutive"),
            "block_size": data.get("block_size"),
        })
    elif form == "adjacency":
        payload.update({
            "first": data.get("first") or {},
            "second": data.get("second") or {},
            "min_gap": data.get("min_gap") if data.get("min_gap") is not None else 1,
            "directional": bool(data.get("directional")),
            "must_follow": bool(data.get("must_follow")),
        })
    elif form == "bucket":
        payload.update({
            "first": data.get("first") or {},
            "second": data.get("second") or {},
            "dimension": data.get("dimension"),
            "relation": data.get("bucket_relation"),
        })
    elif form == "conditional":
        when = dict(data.get("when") or {})
        when.setdefault("form", "count")
        then = dict(data.get("then") or {})
        payload.update({"when": when, "then": _rule_payload(then) if then.get("form") else then})

    return {k: v for k, v in payload.items() if v is not None}


def _drop_empty(selector: dict | None) -> dict:
    """Strip the nulls a model sends for fields it isn't using.

    The IR refuses unknown selector fields, and would otherwise reject a
    perfectly good rule because the model spelled out `not_subjects: null`.
    """
    if not isinstance(selector, dict):
        return {}
    return {k: v for k, v in selector.items() if v not in (None, [], "")}


def _clean(payload: dict) -> dict:
    for key in ("selector", "first", "second"):
        if key in payload:
            payload[key] = _drop_empty(payload[key])
    if isinstance(payload.get("when"), dict):
        payload["when"] = _clean(payload["when"])
    if isinstance(payload.get("then"), dict):
        payload["then"] = _clean(payload["then"])
    return payload


def parse_rule_llm(
    text: str,
    teacher_names: list[str],
    subject_names: list[str],
    class_group_labels: list[str],
    periods: list[tuple[int, int, str | None, bool]] | None = None,
) -> IRParse | None:
    """Parse one rule into the IR. Returns None if the LLM path is unavailable.

    An IRError from a well-formed-looking tool call is turned into an Unclear
    rather than being raised: from the admin's side a rule the model built
    wrongly and a rule they stated ambiguously look the same, and both want the
    same response - say what went wrong and ask.
    """
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; IR parsing unavailable")
        return None

    try:
        # The SDK retries with exponential backoff and honours Retry-After.
        # Above its default of 2 because a 429 here costs an admin their rule:
        # this returns None on failure and the caller falls back, so a burst
        # that a few seconds of waiting would clear otherwise looks to them
        # like the parser simply not understanding them.
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=5)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=1500,
            system=_system_prompt(teacher_names, subject_names, class_group_labels, periods),
            tools=[_RULE_TOOL, _UNCLEAR_TOOL],
            # "any" rather than a named tool: the model must be able to choose
            # report_unclear, which is the whole point of offering it.
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": text}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
    except Exception:
        logger.exception("IR constraint parsing failed")
        return None

    if block.name == "report_unclear":
        data = block.input
        return IRParse(unclear=Unclear(
            reason=data.get("reason", "ambiguous"),
            explanation=data.get("explanation") or "This rule needs clarifying.",
            question=data.get("question"),
            readings=list(data.get("readings") or []),
        ))

    try:
        rule = rule_from_dict(_clean(_rule_payload(block.input)))
    except IRError as exc:
        # Logged at warning, not info: this is the model answering and the
        # schema failing to accept it, which is a defect on our side and should
        # be visible without turning logging up.
        logger.warning("model produced an invalid IR rule for %r: %s", text, exc)
        return IRParse(invalid=str(exc))

    return IRParse(rule=rule, sentence=render(rule))

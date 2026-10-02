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

import html
import json
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
                "Period NUMBERS, using the numbering in the timetable structure "
                "above. Use for 'period 3', 'the first two periods', or a time "
                "of day worked out from where the breaks fall. Never negative - "
                "for 'the last period' use period_positions instead."
            ),
        },
        "period_positions": {
            "type": ["array", "null"],
            "items": {"type": "string", "enum": ["first", "last"]},
            "description": (
                "Use for 'the first period' or 'the last period' when the "
                "sentence says exactly that. This resolves per day, which "
                "matters when days differ in length: on a half-day Saturday the "
                "last period is the 4th, not the 8th. Prefer this over a number "
                "whenever the words are 'first' or 'last'."
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
                "enum": ["count", "run", "adjacency", "bucket", "balance", "span",
                         "conditional"],
                "description": (
                    "count: how many matching periods there may be (also how you "
                    "say 'never' - relation '==' with value 0 - and 'at least "
                    "once' - relation '>=' with value 1). Most rules are counts.\n"
                    "run: how many matching periods may sit back to back, or that "
                    "they must come as a block.\n"
                    "adjacency: how close two DIFFERENT sets of lessons may be, or "
                    "which order they come in.\n"
                    "bucket: whether two sets share a day, or must happen at the "
                    "same time as each other.\n"
                    "balance: keep counts EVEN across days or classes - for "
                    "'spread evenly', 'roughly the same', 'don't bunch'. Use this "
                    "rather than a count when the sentence compares groups to each "
                    "other instead of capping any one of them.\n"
                    "span: how stretched a day is - how far apart the first and "
                    "last period are, or how many free periods sit between them. "
                    "For 'don't leave gaps in the middle', 'all within 4 "
                    "continuous periods'.\n"
                    "conditional: apply a rule only where another count holds."
                ),
            },
            "scope": _SCOPE_SCHEMA,
            "selector": _SELECTOR_SCHEMA,
            "relation": {
                "type": ["string", "null"],
                # Words, not <= >= ==. Those are exactly the characters that get
                # HTML-escaped or quote-mangled in transit, and in the third
                # evaluation run they cost 8 of 13 invalid rules: '&lt;=',
                # '<="', '{"<=":"value"}'. The model had understood each rule
                # and could not spell the operator.
                "enum": ["at_most", "at_least", "exactly", None],
                "description": (
                    "For count. 'at_most' for caps ('no more than 6'), "
                    "'at_least' for minimums ('at least one'), 'exactly' for an "
                    "exact number - and 'never' is 'exactly' with value 0. "
                    "Note 'less than 6' means at_most 5."
                ),
            },
            "value": {"type": ["integer", "null"], "description": "For count: the number."},
            "distinct": {
                "type": ["string", "null"],
                "enum": ["subject", "teacher", "class_group", "day", None],
                "description": (
                    "For count, when the sentence counts KINDS rather than "
                    "periods: 'at most 6 different subjects a day' is "
                    "distinct='subject', and 'all their classes in 3 days' is "
                    "distinct='day'. Leave null to count periods."
                ),
            },
            "exists_over": {
                "type": ["array", "null"],
                "items": {"type": "string",
                          "enum": ["teacher", "class_group", "subject", "day", "period"]},
                "description": (
                    "For count. Names the scope dimensions that only ONE group has "
                    "to satisfy, instead of all of them. 'Every teacher needs at "
                    "least one light day of 4 periods or less' is "
                    "scope=['teacher','day'], exists_over=['day'], '<=' 4 - for "
                    "each teacher, SOME day is light. Without it the rule would "
                    "say every day must be light, which is far harsher. Only use "
                    "for 'at least one', 'some day', 'one of the'; leave null "
                    "otherwise. It cannot cover the whole scope."
                ),
            },
            "across": {
                "type": ["array", "null"],
                "items": {"type": "string",
                          "enum": ["teacher", "class_group", "subject", "day", "period"]},
                "description": (
                    "For balance: the dimension to even out, usually ['day']. "
                    "Must not also appear in scope."
                ),
            },
            "max_spread": {
                "type": ["integer", "null"],
                "description": (
                    "For balance: how many periods the fullest bucket may exceed "
                    "the emptiest. 0 means exactly equal. Use 1 or 2 for vague "
                    "wording like 'evenly' or 'roughly the same' - and set "
                    "strength to a preference, because an exact balance is rarely "
                    "achievable alongside everything else."
                ),
            },
            "max_span": {
                "type": ["integer", "null"],
                "description": (
                    "For span: how many periods may separate the first and last, "
                    "inclusive. 'All his periods within 4 continuous periods, "
                    "which 4 doesn't matter' is 4."
                ),
            },
            "max_idle": {
                "type": ["integer", "null"],
                "description": (
                    "For span: how many free periods may sit BETWEEN the first and "
                    "last. Free periods before the first or after the last don't "
                    "count - those are arriving late or leaving early, not gaps in "
                    "the middle. 'Don't leave teachers with 3 free periods in the "
                    "middle of the day' is 2."
                ),
            },
            "must_precede": {
                "type": ["boolean", "null"],
                "description": (
                    "For adjacency: true when `second` must come LATER IN THE DAY "
                    "than `first`, at any distance. 'English must come before "
                    "Maths' is this, not must_follow - must_follow would force "
                    "them into neighbouring periods, which was not asked for."
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

Rules that sound vague and are not. Say these, don't refuse them:

"rao mam son is in 9B, she shouldnt teach 9B"
  form=count scope=[] selector={teachers:["Mrs. Rao"],class_groups:["Grade 9 - B"]} relation="==" value=0

"English every day for primary"
  form=count scope=["class_group","day"] selector={subjects:["English"],class_groups:["Grade 1"]} relation=">=" value=1
  (one per grade named; "every day" is scope, not a filter)

"Students should never have a free period"
  form=count scope=["class_group","period"] selector={} relation=">=" value=1
  (every class, in every slot, has at least one lesson)

"No more than 3 of Maths, Science and English in a day"
  form=count scope=["class_group","day"] selector={subjects:["Maths","Science","English"]} relation="<=" value=3
  (several subjects in one selector are ORed, so this counts them together -
  count periods unless the sentence says "different subjects")

"each science teacher atleast one board class (10th or 12th)"
  form=count scope=["teacher"] selector={teachers:["Mr. Khan"],class_groups:["Grade 10","Grade 12"]} relation=">=" value=1

"every teacher needs atleast one light day mon to fri, 4 periods or less"
  form=count scope=["teacher","day"] exists_over=["day"] selector={days:[0,1,2,3,4]} relation="<=" value=4 strength="preference"
  (exists_over is what makes this "some day" rather than "every day")

"Spread Mr. Khan's classes evenly through the week"
  form=balance scope=["teacher"] across=["day"] selector={teachers:["Mr. Khan"]} max_spread=1 strength="preference"

"same grade sections should have roughly same number of free gaps"
  form=balance scope=[] across=["class_group"] selector={class_groups:["Grade 9"]} max_spread=2 strength="preference"

"Don't leave teachers with 3 free periods in the middle of the day"
  form=span scope=["teacher","day"] max_idle=2 strength="preference"

"iyer sir is part time, on the days he comes all his periods shd be within 4 continuous periods"
  form=span scope=["teacher","day"] selector={teachers:["Mr. Iyer"]} max_span=4

"Try to give part-time teachers all their classes in 3 days"
  form=count scope=["teacher"] selector={teachers:["Mr. Iyer"]} distinct="day" relation="<=" value=3 strength="preference"

"if eng and math are both there that day, english must come before maths"
  form=adjacency scope=["class_group"] first={subjects:["English"]} second={subjects:["Maths"]} must_precede=true

A two-sided form needs its sides to be DIFFERENT lessons. If you find yourself
filling `first` and `second` identically, the rule is not an adjacency or a
bucket:

"8A and 8B have PE together"
  form=bucket scope=[] first={subjects:["PE"],class_groups:["Grade 8 - A"]} second={subjects:["PE"],class_groups:["Grade 8 - B"]} dimension="period" bucket_relation="same"
  (the two sides differ by SECTION - naming 8A on both sides says nothing)

"The same teacher should take Science for all of Grade 9"
  form=count scope=[] selector={subjects:["Science"],class_groups:["Grade 9"]} distinct="teacher" relation="at_most" value=1
  (one distinct teacher across those lessons. NOT "every teacher has exactly 1
  Grade 9 Science period", which spreads it across the whole staff instead)

"Grade 1 should have English in the same period every day"
  form=count scope=["class_group"] selector={subjects:["English"],class_groups:["Grade 1"]} distinct="period_order" relation="at_most" value=1 strength="preference"
  (one position used - the mirror image of "vary the period")

"Mrs. Rao would like her classes in the morning if possible"
  form=count scope=[] selector={teachers:["Mrs. Rao"],period_orders:[6,7,8]} relation="exactly" value=0 strength="preference"
  (the timetable structure says where lunch falls, so "morning" is the periods
  before it - said as "none in the afternoon ones")

block_size means EVERY one of those lessons must come as a block. It cannot say
how MANY blocks there are:

"Only one double Maths period per week"
  report_unclear, reason="not_supported" - block_size would force every Maths
  period into a double, which is the opposite of a limit of one. Counting
  blocks is not something this can express.

"PE shouldn't be on two days in a row"
  report_unclear, reason="not_supported" - this is about which DAYS are next to
  each other, and only positions within a day can be compared. "Spread PE
  across the week" is a balance rule; "two days in a row" is not.

"maths not in last period - ok if 2 or 3 sections break it, not more"
  report_unclear, reason="not_supported" - a budget for how many sections may
  break a rule. The rule itself is sayable; the allowance is not, and recording
  only the rule would make it stricter than was asked.

"Libary for 8th - each section diff day. 8A 8B 8C 8D cant be same day"
  form=count scope=[] selector={subjects:["Library"],class_groups:["Grade 8"]} distinct="day" relation="at_least" value=4
  ("all four on different days" is four different days used - a count of
  distinct days, not a bucket. A bucket compares two named sets, so it cannot
  say "all of these differ from each other".)

"dont put hindi P4 every single day, vary the period"
  form=count scope=["class_group"] selector={subjects:["Hindi"]} distinct="period_order" relation="at_least" value=2 strength="preference"
  (period_order is the position in the day - P4 - as opposed to `period`, which
  is one slot in the week. "Vary the period" means more than one position gets
  used.)

"every teacher atleast one free before lunch"
  form=count scope=["teacher","day"] selector={period_orders:[1,2,3,4,5]} relation="at_most" value=4
  (with five periods before lunch, teaching at most four of them leaves one
  free. This is "on every day", so no exists_over - a free period before lunch
  on ONE day of the week was not what was asked for.)

"Don't give the same teacher the last period every day"
  form=count scope=["teacher"] selector={period_positions:["last"]} relation="at_most" value=2 strength="preference"
  (period_positions, not a number - the last period is the 8th on a full day
  and the 4th on a half-day Saturday)

"Don't keep tests or Maths just before lunch"
  form=count scope=["class_group"] selector={subjects:["Maths"],period_orders:[5]} relation="exactly" value=0
  (the timetable structure above says where lunch is, so "just before lunch" is
  a period number. A break is not a subject and cannot go in a selector.)

"same grade sections should have roughly same number of free gaps"
  form=balance scope=[] across=["class_group"] selector={class_groups:["Grade 9"]} max_spread=2 strength="preference"
  (a dimension being evened out goes in `across` and NOT in `scope` - putting
  it in both asks to even out the days within each day)

"Make the timetable balanced and nice for everyone"
  report_unclear, reason="too_vague" - "balanced" has no measurable meaning
  here. Note the contrast with "spread evenly through the week", which names
  what to even out and is a balance rule.

"chem lab - need 1 perod gap between 2 practicals, suresh has to clean n set up"
  report_unclear, reason="not_supported" - this is about a room, which cannot
  be represented yet. Note that the reason is the room, not the phrasing.

"arjun sir PE periods back to back as much as poss, dont make him walk to ground 4 times"
  report_unclear, reason="not_supported" - "as few separate stretches as
  possible" is a thing to minimise rather than a limit to set, and there is no
  form for that. Do not send a run rule with neither max_consecutive nor
  block_size; if a specific block would do ("PE comes in doubles"), say that
  instead and note the difference in `description`.

"fri should be lighter than mon-thurs where possible"
  report_unclear, reason="not_supported" - balance evens groups out against
  each other; it cannot make one named group lighter than the rest. Only reach
  for balance when the sentence says "evenly", "spread" or "roughly the same",
  and never put the same dimension in both `scope` and `across`."""


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
    # (input, output, cache_read, cache_write) tokens for this call, or None if
    # it never reached the API. Carried so a caller can report what a run cost:
    # a prepaid balance disappearing with nothing on screen to explain it is a
    # worse failure than a slow script.
    #
    # The cache figures are not decoration. Caching fails silently - the
    # request succeeds, the bill is just higher - so the only way to know it is
    # working is to look at cache_read, and the only way to notice it stopped
    # is to keep looking.
    usage: tuple[int, int, int, int] | None = None


# ---------------------------------------------------------------------------
# Normalising what a model actually sends
# ---------------------------------------------------------------------------
#
# A JSON schema says what is allowed; it does not stop a model sending
# something near it. The second evaluation run lost 16 rules to the validator,
# several of them verbatim examples from this file's own prompt, which is the
# clearest possible sign that rejecting a near-miss is the wrong response to
# one.
#
# So the IR stays strict and this layer absorbs the variation. Every
# substitution is logged, because the useful output of this is not the rescued
# rule - it is finding out which wordings a model reaches for, so the schema
# can be renamed to match rather than translated forever.

_SCOPE_ALIASES = {
    "teachers": "teacher", "staff": "teacher",
    "class": "class_group", "classes": "class_group", "class_groups": "class_group",
    "section": "class_group", "sections": "class_group",
    "grade": "class_group", "grades": "class_group",
    "subjects": "subject",
    "days": "day", "weekday": "day", "day_of_week": "day",
    "periods": "period", "slot": "period", "slots": "period", "period_order": "period",
}

# "week" is the absence of "day", not a dimension. A model reaching for it has
# understood the rule correctly and guessed at the vocabulary, so dropping it
# gives exactly the weekly total that was meant.
_SCOPE_DROP = {"week", "weekly", "term", "year", "school", "overall", "total"}

_SELECTOR_ALIASES = {
    "subject": "subjects", "subject_names": "subjects",
    "not_subject": "not_subjects", "exclude_subjects": "not_subjects",
    "except_subjects": "not_subjects", "other_than": "not_subjects",
    "teacher": "teachers", "teacher_names": "teachers",
    "class_group": "class_groups", "class_group_names": "class_groups",
    "classes": "class_groups", "sections": "class_groups", "grades": "class_groups",
    "day": "days", "days_of_week": "days", "weekdays": "days",
    "period": "period_orders", "periods": "period_orders",
    "period_order": "period_orders", "period_numbers": "period_orders",
}

_RELATION_ALIASES = {
    "at_most": "<=", "max": "<=", "maximum": "<=", "no_more_than": "<=",
    "less_than_or_equal": "<=", "lte": "<=", "<=": "<=", "=<": "<=", "<": "<=",
    "at_least": ">=", "min": ">=", "minimum": ">=", "no_fewer_than": ">=",
    "greater_than_or_equal": ">=", "gte": ">=", ">=": ">=", "=>": ">=", ">": ">=",
    "equal": "==", "equals": "==", "exactly": "==", "eq": "==", "==": "==", "=": "==",
}

_BUCKET_RELATION_ALIASES = {
    "same_day": "same", "same_period": "same", "same_time": "same", "together": "same",
    "different_day": "different", "different_period": "different",
    "differ": "different", "apart": "different", "not_same": "different",
}


def _note(seen: list[str], message: str) -> None:
    seen.append(message)


def _normalise_scope(value, seen: list[str]):
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return value
    out = []
    for item in value:
        name = str(item).strip().lower().replace(" ", "_")
        if name in _SCOPE_DROP:
            _note(seen, f"scope {item!r} dropped (absence of 'day' already means the week)")
            continue
        if name in _SCOPE_ALIASES:
            _note(seen, f"scope {item!r} -> {_SCOPE_ALIASES[name]!r}")
            name = _SCOPE_ALIASES[name]
        if name not in out:
            out.append(name)
    return out


def _normalise_selector(value, seen: list[str]):
    """Rename near-miss selector keys, and drop the nulls a model pads with."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for key, v in value.items():
        if v in (None, [], ""):
            continue
        name = str(key).strip().lower()
        if name in _SELECTOR_ALIASES:
            _note(seen, f"selector {key!r} -> {_SELECTOR_ALIASES[name]!r}")
            name = _SELECTOR_ALIASES[name]
        # A single name sent unwrapped is unambiguous, so wrap it rather than
        # refusing a rule over a pair of brackets.
        if name in ("subjects", "not_subjects", "teachers", "class_groups") and isinstance(v, str):
            v = [v]
        if name in ("days", "period_orders") and isinstance(v, (int, str)):
            v = [v]
        if name == "period_positions" and isinstance(v, str):
            v = [v]
        if name == "period_orders" and isinstance(v, (list, tuple)):
            # Negative indexing: a model sending -1 has read "the last period"
            # and guessed at the notation, which is a near miss rather than a
            # mistake. -1 is the last, -2 the one before it - but only -1 has an
            # unambiguous name here, so anything further is dropped rather than
            # guessed at.
            positive = [x for x in v if not (isinstance(x, int) and x < 0)]
            if any(x == -1 for x in v if isinstance(x, int)):
                _note(seen, "period_orders -1 -> period_positions ['last']")
                out.setdefault("period_positions", []).append("last")
            if len(positive) != len(v):
                dropped = [x for x in v if isinstance(x, int) and x < -1]
                if dropped:
                    _note(seen, f"period_orders {dropped} dropped (no name for them)")
            if not positive:
                continue
            v = positive
        out[name] = v
    return out


def _unmangle(raw: str) -> str:
    """Strip the damage an operator picks up in transit.

    The third evaluation run produced '&lt;=', '<="', '=="' and
    '{"<=":"value"}' as relation values - the model had read each rule
    correctly and could not get the characters through intact. The schema now
    asks for words instead, which removes the cause; this stays for anything
    that still arrives mangled, since a rule lost to an escaped angle bracket
    is the worst possible reason to lose one.
    """
    text = html.unescape(raw).strip()
    # A whole JSON object where a string was expected: take the first key.
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed:
                text = str(next(iter(parsed)))
        except ValueError:
            pass
    return text.strip().strip('"\'' + "`").strip()


def _normalise_relation(value, seen: list[str], aliases, field_name: str):
    if not isinstance(value, str):
        return value
    raw = value.strip()
    cleaned = _unmangle(raw)
    if cleaned != raw:
        _note(seen, f"{field_name} {raw!r} unmangled to {cleaned!r}")
    name = cleaned.lower().replace(" ", "_").replace("-", "_")
    if name in aliases:
        if aliases[name] != cleaned:
            _note(seen, f"{field_name} {cleaned!r} -> {aliases[name]!r}")
        return aliases[name]
    return cleaned


def _rule_payload(data: dict, seen: list[str] | None = None) -> dict:
    """Map the flat tool input onto the IR's nested shape.

    The tool is flat because a model fills a flat object more reliably than a
    discriminated union, and `bucket_relation` is spelled out rather than
    reusing `relation` so the two can't be confused when a bucket rule and a
    count rule appear in the same conversation.
    """
    seen = seen if seen is not None else []
    form = str(data.get("form") or "").strip().lower()
    payload = {
        "form": form or None,
        "scope": _normalise_scope(data.get("scope"), seen),
        "strength": data.get("strength") or "required",
        "description": data.get("description") or "",
    }
    if form == "count":
        payload.update({
            "selector": _normalise_selector(data.get("selector"), seen),
            "relation": _normalise_relation(data.get("relation"), seen, _RELATION_ALIASES, "relation"),
            "value": data.get("value"),
            "distinct": data.get("distinct"),
            # Normalised through the same aliases as scope, so "days" here and
            # "day" there can't end up naming different things and silently
            # turning an existential rule back into a universal one.
            "exists_over": _normalise_scope(data.get("exists_over"), seen),
        })
        # Naming a dimension as existential while leaving it out of scope says
        # the rule is grouped by it - that is what "at least one day" means. The
        # IR refuses the combination, so repair it rather than lose a rule the
        # model read correctly.
        missing = [d for d in payload["exists_over"] if d not in payload["scope"]]
        if missing:
            _note(seen, f"scope gained {missing} because exists_over named them")
            payload["scope"] = list(payload["scope"]) + missing
    elif form == "run":
        max_consecutive = data.get("max_consecutive")
        block_size = data.get("block_size")
        # block_size=1 is not a block, it is the opposite of one. A model that
        # sends it has read "no double periods" and reached for the wrong
        # field; the IR would refuse it, so say what was meant instead.
        if block_size == 1:
            _note(seen, "block_size 1 -> max_consecutive 1 (a block of one is not a block)")
            block_size, max_consecutive = None, max_consecutive or 1
        payload.update({
            "selector": _normalise_selector(data.get("selector"), seen),
            "max_consecutive": max_consecutive,
            "block_size": block_size,
        })
    elif form == "adjacency":
        min_gap = data.get("min_gap")
        must_precede = bool(data.get("must_precede"))
        if min_gap == 0 and not must_precede:
            # A gap of zero forbids nothing, so nobody means it literally. It
            # comes from reading "A must come before B", which is ordering
            # rather than distance - which the IR now says directly.
            _note(seen, "min_gap 0 -> must_precede (a gap of zero forbids nothing)")
            must_precede, min_gap = True, None
        payload.update({
            "first": _normalise_selector(data.get("first"), seen),
            "second": _normalise_selector(data.get("second"), seen),
            "min_gap": min_gap if min_gap is not None else 1,
            "directional": bool(data.get("directional")),
            "must_follow": bool(data.get("must_follow")),
            "must_precede": must_precede,
        })
    elif form == "bucket":
        payload.update({
            "first": _normalise_selector(data.get("first"), seen),
            "second": _normalise_selector(data.get("second"), seen),
            "dimension": data.get("dimension"),
            "relation": _normalise_relation(
                data.get("bucket_relation"), seen, _BUCKET_RELATION_ALIASES, "bucket_relation"),
        })
    elif form == "balance":
        payload.update({
            "selector": _normalise_selector(data.get("selector"), seen),
            "across": _normalise_scope(data.get("across"), seen),
            "max_spread": data.get("max_spread"),
        })
    elif form == "span":
        payload.update({
            "selector": _normalise_selector(data.get("selector"), seen),
            "max_span": data.get("max_span"),
            "max_idle": data.get("max_idle"),
            "min_idle_gap": data.get("min_idle_gap"),
        })
    elif form == "conditional":
        when = dict(data.get("when") or {})
        when.setdefault("form", "count")
        then = dict(data.get("then") or {})
        payload.update({
            "when": _rule_payload(when, seen),
            "then": _rule_payload(then, seen) if then.get("form") else then,
        })

    return {k: v for k, v in payload.items() if v is not None}


def _clean(payload: dict) -> dict:
    """Kept as the single entry point callers use, now that _rule_payload
    normalises as it goes. Selectors arrive already stripped of the nulls a
    model pads with, so this only has to recurse into a conditional."""
    for key in ("when", "then"):
        if isinstance(payload.get(key), dict):
            payload[key] = _clean(payload[key])
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
        # The SDK retries with exponential backoff and honours Retry-After. One
        # above the default of 2, not three above: a retry re-sends the whole
        # ~3,000-token prompt, so a high budget turns one rate-limited call into
        # six calls' worth of tokens and pushes the next batch over the same
        # limit - the retries feeding the thing they are retrying against. Five
        # was set to be safe and burned through a prepaid balance instead.
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=3)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=1500,
            # Cached, because every call in a sitting sends the same ~8,900
            # tokens of tool schemas and worked examples and only the one
            # sentence at the end differs. Reads cost a tenth of the write.
            #
            # The breakpoint goes on the last system block and covers the tools
            # too: the prompt renders tools -> system -> messages, so a marker
            # here caches everything before it. That ordering is the whole
            # reason this is worth doing - the two tool schemas are about as
            # large as the system prompt, and measuring the system prompt alone
            # put the prefix under Haiku 4.5's 4,096-token minimum and led to
            # the wrong conclusion that caching could not apply.
            system=[{
                "type": "text",
                "text": _system_prompt(teacher_names, subject_names, class_group_labels, periods),
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[_RULE_TOOL, _UNCLEAR_TOOL],
            # "any" rather than a named tool: the model must be able to choose
            # report_unclear, which is the whole point of offering it.
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": text}],
        )
        block = next(b for b in response.content if b.type == "tool_use")
        usage = (
            response.usage.input_tokens,
            response.usage.output_tokens,
            getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )
    except Exception:
        logger.exception("IR constraint parsing failed")
        return None

    if block.name == "report_unclear":
        data = block.input
        return IRParse(usage=usage, unclear=Unclear(
            reason=data.get("reason", "ambiguous"),
            explanation=data.get("explanation") or "This rule needs clarifying.",
            question=data.get("question"),
            readings=list(data.get("readings") or []),
        ))

    seen: list[str] = []
    try:
        rule = rule_from_dict(_clean(_rule_payload(block.input, seen)))
        if seen:
            # The point of logging these is not the rescued rule - it is
            # finding out which wordings the model reaches for, so the schema
            # can be renamed to match rather than translated forever.
            logger.info("normalised model output for %r: %s", text, "; ".join(seen))
    except IRError as exc:
        # Logged at warning, not info: this is the model answering and the
        # schema failing to accept it, which is a defect on our side and should
        # be visible without turning logging up.
        logger.warning("model produced an invalid IR rule for %r: %s", text, exc)
        return IRParse(invalid=str(exc), usage=usage)

    return IRParse(rule=rule, sentence=render(rule), usage=usage)

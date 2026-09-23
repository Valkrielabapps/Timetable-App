"""
LLM-based constraint parser — calls Claude to turn a free-text scheduling
rule into a structured constraint, instead of the fixed regex patterns in
app/services/constraint_parser.py. This understands a much wider range of
phrasing and a richer set of constraint types (see ParsedConstraint below),
because it's real language understanding rather than keyword matching.

Design choices:
  - Uses forced tool-use (`tool_choice`), not free-text completion, so the
    response is always valid structured data — no second parsing step, no
    "the model wrapped its answer in prose" failure mode.
  - Grounds the model against the school's actual teacher/subject/class-group
    names (passed in the system prompt) and instructs it to only use exact
    names from those lists, or null. This keeps the *matching* logic here
    (in the prompt) rather than pushing fuzzy string matching into the
    router — the router just does an exact dict lookup on whatever name
    comes back, same as the regex parser did.
  - Returns None on ANY failure — no API key configured, network error,
    rate limit, malformed response, whatever. The caller
    (app/routers/constraints.py) falls back to the regex parser when this
    returns None, so a flaky LLM call never blocks constraint entry
    entirely. This is a deliberate availability-over-purity tradeoff.
"""
import logging
import re
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)

# Constraint types this parser (and the solver) understand:
#   workload_limit          - caps a teacher's periods/week
#   availability             - a teacher is unavailable on a given day
#   subject_period_position  - a subject must (mode=require) or must not
#                               (mode=exclude) be in the first/last period
#                               of the day, optionally scoped to one grade
#                               or section via class_group_name
#   max_consecutive_periods  - caps how many periods can run back-to-back
#                               on the same day for either a subject (any
#                               class, optionally scoped via
#                               class_group_name) or a teacher (their whole
#                               schedule, any subject/class — set
#                               teacher_name instead of subject_name)
#   min_gap_between_subjects  - first_subject_name and second_subject_name
#                               must be separated by at least min_gap
#                               periods on the same day, for the same class
#                               (e.g. "leave at least 1 period between PE
#                               and Math"), optionally scoped via
#                               class_group_name
#   subject_day_position      - a subject must (mode=require) or must not
#                               (mode=exclude) be scheduled on a given day
#                               of the week (e.g. "No PE on Fridays"),
#                               optionally scoped via class_group_name
#   subject_sequence          - second_subject_name must not be scheduled
#                               in the period immediately after
#                               first_subject_name, for the same class
#                               (e.g. "Math can't immediately follow PE"),
#                               optionally scoped via class_group_name
#   scheduling_rule           - catch-all; recorded but not enforced
_TOOL_SCHEMA = {
    "name": "record_constraint",
    "description": "Record a structured school-timetabling constraint extracted from one sentence of free text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": [
                    "workload_limit",
                    "availability",
                    "subject_period_position",
                    "subject_day_position",
                    "max_consecutive_periods",
                    "min_gap_between_subjects",
                    "subject_sequence",
                    "scheduling_rule",
                ],
            },
            "teacher_name": {
                "type": ["string", "null"],
                "description": "Must exactly match one of the provided known teacher names verbatim, or null if none is mentioned/matched. For max_consecutive_periods, set this (and leave subject_name null) when the rule caps a specific teacher's back-to-back periods rather than a subject's.",
            },
            "subject_name": {
                "type": ["string", "null"],
                "description": "Must exactly match one of the provided known subject names verbatim, or null. Used by subject_period_position, subject_day_position, and the subject variant of max_consecutive_periods.",
            },
            "first_subject_name": {
                "type": ["string", "null"],
                "description": "For subject_sequence and min_gap_between_subjects: the first-named subject. Must exactly match a known subject name, or null.",
            },
            "second_subject_name": {
                "type": ["string", "null"],
                "description": "For subject_sequence and min_gap_between_subjects: the second-named subject. Must exactly match a known subject name, or null.",
            },
            "class_group_name": {
                "type": ["string", "null"],
                "description": "Must exactly match one of the provided known class-group labels verbatim (a whole grade like 'Grade 3', or one section like 'Grade 3 - A'), or null if the rule applies school-wide / isn't about a specific class.",
            },
            "max_periods_per_week": {"type": ["integer", "null"], "description": "For workload_limit."},
            "day_of_week": {"type": ["integer", "null"], "description": "0=Monday .. 6=Sunday. For availability and subject_day_position."},
            "position": {"type": ["string", "null"], "enum": ["first", "last", None], "description": "For subject_period_position."},
            "mode": {
                "type": ["string", "null"],
                "enum": ["require", "exclude", None],
                "description": "For subject_period_position and subject_day_position: 'require' if the sentence says the subject MUST/SHOULD be there, 'exclude' if it says the subject must NOT/CAN'T/SHOULDN'T be there.",
            },
            "max_consecutive": {"type": ["integer", "null"], "description": "For max_consecutive_periods — the max number of back-to-back periods allowed."},
            "min_gap": {"type": ["integer", "null"], "description": "For min_gap_between_subjects — the minimum number of periods that must separate the two subjects on the same day."},
            "description": {
                "type": "string",
                "description": "A short, human-readable one-sentence summary of the rule, for display in a UI card.",
            },
        },
        "required": ["type", "description"],
    },
}


@dataclass
class ParsedConstraint:
    type: str
    description: str
    teacher_name: str | None = None
    subject_name: str | None = None
    first_subject_name: str | None = None
    second_subject_name: str | None = None
    class_group_name: str | None = None
    max_periods_per_week: int | None = None
    day_of_week: int | None = None
    position: str | None = None
    mode: str | None = None
    max_consecutive: int | None = None
    min_gap: int | None = None


# The batch tool's "constraints" array reuses this exact per-item shape
# (same properties/required as _TOOL_SCHEMA's single-constraint input) so
# the model doesn't need to learn two different constraint shapes
# depending on whether it's parsing one sentence or several.
_BATCH_TOOL_SCHEMA = {
    "name": "record_constraints",
    "description": "Record every distinct school-timetabling constraint found in the provided text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "constraints": {
                "type": "array",
                "description": "One entry per distinct constraint mentioned in the text — several if the admin listed multiple rules, one if there's only one.",
                "items": _TOOL_SCHEMA["input_schema"],
            },
        },
        "required": ["constraints"],
    },
}


def _parsed_constraint_from_tool_input(data: dict, fallback_description: str) -> ParsedConstraint:
    """Shared by parse_constraint_llm and parse_constraints_batch_llm —
    turns one record_constraint-shaped dict (single call's `tool_use.input`
    or one entry of a batch call's `constraints` array) into a
    ParsedConstraint. `fallback_description` covers the (should-be-rare)
    case where the model leaves `description` empty despite it being a
    required tool field."""
    return ParsedConstraint(
        type=data.get("type", "scheduling_rule"),
        description=data.get("description") or fallback_description,
        teacher_name=data.get("teacher_name"),
        subject_name=data.get("subject_name"),
        first_subject_name=data.get("first_subject_name"),
        second_subject_name=data.get("second_subject_name"),
        class_group_name=data.get("class_group_name"),
        max_periods_per_week=data.get("max_periods_per_week"),
        day_of_week=data.get("day_of_week"),
        position=data.get("position"),
        mode=data.get("mode"),
        max_consecutive=data.get("max_consecutive"),
        min_gap=data.get("min_gap"),
    )


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# A label carrying no information beyond its position - "Period 3", "P3", "3".
# Anything else (e.g. "Lunch", "Assembly", "Games") is worth naming in the
# prompt, because it is the only way a rule phrased around it can be resolved.
_GENERIC_LABEL = re.compile(r"^\s*(p|period)?\s*\d+\s*$", re.IGNORECASE)


def _period_summary(periods: list[tuple[int, int, str | None]]) -> str:
    """Describe the school's week compactly enough to be worth sending.

    Without this the model has no idea what "the last period" or "period 3"
    refer to - it sees teachers, subjects and class groups, and has to guess
    at the shape of the timetable those sit in.

    Deliberately a summary, not the rows: a school with 8 periods across 5
    days has 40 Period rows, and enumerating them costs several hundred
    tokens per parse to say what two sentences say. Irregular weeks (days
    with different period counts) fall back to a per-day breakdown, and any
    label that isn't just a number is listed individually - a period named
    "Lunch" is exactly the thing rules get phrased around.
    """
    if not periods:
        return ""

    by_day: dict[int, list[tuple[int, str | None]]] = {}
    for day, order, label in periods:
        by_day.setdefault(day, []).append((order, label))

    days = sorted(by_day)
    day_names = [_DAY_NAMES[d] if 0 <= d < 7 else f"day {d}" for d in days]
    counts = {d: len(by_day[d]) for d in days}

    if len(set(counts.values())) == 1:
        n = counts[days[0]]
        structure = (
            f"Teaching days: {', '.join(day_names)}. "
            f"{n} periods per day, numbered 1 to {n} "
            f"(so \"first period\" = 1 and \"last period\" = {n})."
        )
    else:
        breakdown = "; ".join(f"{_DAY_NAMES[d] if 0 <= d < 7 else d}: {counts[d]}" for d in days)
        structure = (
            f"Teaching days: {', '.join(day_names)}. "
            f"Periods differ by day - {breakdown}. "
            "\"Last period\" means the highest-numbered period on the day in question."
        )

    # Collapse labels that sit at the same slot every day - a school with a
    # lunch period has one on all five days, and saying so five times is five
    # times the tokens for the same fact.
    slots: dict[tuple[int, str], set[int]] = {}
    for day in days:
        for order, label in by_day[day]:
            if label and not _GENERIC_LABEL.match(label):
                slots.setdefault((order, label), set()).add(day)

    named = []
    for (order, label), on_days in sorted(slots.items()):
        if on_days == set(days):
            named.append(f'period {order} is "{label}" every day')
        else:
            where = ", ".join(_DAY_NAMES[d] if 0 <= d < 7 else str(d) for d in sorted(on_days))
            named.append(f'period {order} is "{label}" on {where}')
    if named:
        structure += " Named periods: " + "; ".join(named) + "."

    return structure


def _grounding_system_prompt(
    teacher_names: list[str],
    subject_names: list[str],
    class_group_labels: list[str],
    periods: list[tuple[int, int, str | None]] | None = None,
) -> str:
    """The "only use exact names from these lists" grounding instructions
    shared by both the single-constraint and batch prompts — factored out
    so the two can't quietly drift apart on how strict that matching rule
    is worded.

    `periods` is what lets positional phrasing resolve at all: without it the
    model is told who teaches what, but nothing about the shape of the week
    those lessons sit in, so "the last period" or "period 3" are guesses.
    Optional because the regex-era callers (and the tests) don't supply it,
    and a missing timetable structure should degrade the prompt rather than
    break it."""
    return (
        f"Known teachers: {teacher_names}\n"
        f"Known subjects: {subject_names}\n"
        f"Known class groups (grades and sections): {class_group_labels}\n"
        + (f"{_period_summary(periods)}\n\n" if periods else "\n")
        + "Only reference names that appear verbatim in these lists; if a name in the "
        "text doesn't clearly match one of them, use null rather than guessing. "
        "If a rule doesn't fit any of the specific constraint types, use "
        "type='scheduling_rule' and just fill in description."
    )


def parse_constraint_llm(
    text: str,
    teacher_names: list[str],
    subject_names: list[str],
    class_group_labels: list[str],
    periods: list[tuple[int, int, str | None]] | None = None,
) -> ParsedConstraint | None:
    """Returns None (never raises) if the LLM path can't be used right
    now — no key configured, or the call/response failed for any reason.
    Callers must handle None by falling back to the regex parser."""
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; falling back to regex constraint parser")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system_prompt = (
            "You extract a single structured school-timetabling constraint from one "
            "sentence written by a school admin. Use the record_constraint tool.\n\n"
            + _grounding_system_prompt(teacher_names, subject_names, class_group_labels, periods)
        )
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=500,
            system=system_prompt,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_constraint"},
            messages=[{"role": "user", "content": text}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return _parsed_constraint_from_tool_input(tool_use.input, fallback_description=text)
    except Exception:
        logger.exception("LLM constraint parsing failed; falling back to regex parser")
        return None


def parse_constraints_batch_llm(
    text: str,
    teacher_names: list[str],
    subject_names: list[str],
    class_group_labels: list[str],
    periods: list[tuple[int, int, str | None]] | None = None,
) -> list[ParsedConstraint] | None:
    """Batch counterpart to parse_constraint_llm — extracts every distinct
    constraint from a whole block of text (e.g. several rules pasted or
    typed together) in a single call, instead of requiring one call per
    sentence. Same never-raises contract: returns None if the LLM path
    can't be used right now (no key, package missing, call/response
    failed for any reason). Callers must handle None by falling back to
    splitting the text into lines and parsing each with
    parse_constraint_llm/the regex parser individually — see
    app/routers/constraints.py's _resolve_constraints_batch_text."""
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; falling back to per-line constraint parsing")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system_prompt = (
            "You extract EVERY distinct structured school-timetabling constraint "
            "mentioned in the text below, which may contain several rules written "
            "together (one per line, or run together in a paragraph) rather than "
            "just one sentence. Use the record_constraints tool, with one array "
            "entry per distinct rule you find — do not merge unrelated rules into "
            "one entry, and do not skip any rule just because it's vague; use "
            "type='scheduling_rule' for anything that doesn't fit a specific "
            "type rather than dropping it.\n\n"
            + _grounding_system_prompt(teacher_names, subject_names, class_group_labels, periods)
        )
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=4000,
            system=system_prompt,
            tools=[_BATCH_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_constraints"},
            messages=[{"role": "user", "content": text}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        raw_constraints = tool_use.input.get("constraints") or []
        return [
            _parsed_constraint_from_tool_input(data, fallback_description=text)
            for data in raw_constraints
        ]
    except Exception:
        logger.exception("LLM batch constraint parsing failed; falling back to per-line parsing")
        return None

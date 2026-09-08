"""
Conversational timetable editing — turns a plain-English instruction like
"move Grade 8's Math to period 2 on Wednesdays" or "lock Mrs. Sharma's
Monday classes" into the SAME structured edit the existing drag-and-drop
UI produces (PATCH .../entries/{id} or POST .../swap-with/{id} in
app/routers/timetables.py), rather than a new mutation path of its own.

Design choice that's different from every other LLM-calling service in
this app (app/services/llm_constraint_parser.py,
app/services/infeasibility_explainer.py): there is deliberately NO
non-LLM fallback here. Constraint parsing has a regex fallback because a
handful of fixed phrasings cover most real constraint sentences well
enough; resolving "which one of potentially hundreds of existing
timetable entries, at which one of the school's periods" from free text
has no equivalent fixed-pattern shortcut worth building — the ambiguity
resolution (which entry did they mean? which period?) genuinely needs the
model's judgment, grounded against the actual current state of this
timetable. If no ANTHROPIC_API_KEY is configured, this feature is simply
unavailable and the admin uses drag-and-drop instead — see
app/routers/timetables.py's edit_command endpoint for how that's
surfaced.

Rather than asking the model to name a class group/subject/day/period in
free text and then fuzzy-matching that in Python (like the constraint
parsers do for teacher/subject names), this grounds the model against the
timetable's actual entries and the school's actual periods, each tagged
with its own id, and asks the model to return those ids directly. This
pushes ALL of the disambiguation (which of the 3 weekly Math slots did
they mean? does "period 2" mean order=2 or the period labeled "Period
2"?) into the one place that already has full context to resolve it,
instead of the router trying to re-derive partial matches from scratch.
Every returned id is re-validated against the same lists server-side
before anything is mutated — a hallucinated id that doesn't appear in
what was actually offered is treated as ordinary parse failure, not
trusted.
"""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOOL_SCHEMA = {
    "name": "record_edit_command",
    "description": (
        "Record what timetable edit the admin is asking for, resolved against the "
        "specific entries and periods provided, or explain why it can't be resolved "
        "confidently."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["move", "lock", "unlock", "swap", "unresolved"],
                "description": (
                    "'move' changes an entry's period (and optionally teacher). 'lock'/"
                    "'unlock' toggles one entry's locked flag. 'swap' exchanges two "
                    "entries' periods. 'unresolved' if you cannot confidently identify "
                    "which entry (or period, or second entry for a swap) is meant — use "
                    "this rather than guessing."
                ),
            },
            "entry_id": {
                "type": ["integer", "null"],
                "description": "The id of the entry being moved/locked/unlocked/swapped, from the provided entry list. Null if unresolved.",
            },
            "target_period_id": {
                "type": ["integer", "null"],
                "description": "For 'move' only: the id of the destination period, from the provided period list.",
            },
            "target_teacher_id": {
                "type": ["integer", "null"],
                "description": "For 'move' only, and only if the instruction also names a different teacher: the id of that teacher, from the provided teacher list. Null to keep the entry's current teacher.",
            },
            "other_entry_id": {
                "type": ["integer", "null"],
                "description": "For 'swap' only: the id of the second entry being swapped with entry_id, from the provided entry list.",
            },
            "description": {
                "type": "string",
                "description": "One short sentence describing the edit performed (or, for 'unresolved', what's ambiguous and what extra detail would resolve it) — shown to the admin as confirmation or as the error message.",
            },
        },
        "required": ["action", "description"],
    },
}


def parse_edit_command_llm(
    text: str,
    entries: list[dict],
    periods: list[dict],
    teachers: list[dict],
) -> dict | None:
    """
    `entries`/`periods`/`teachers` are plain dicts (not ORM objects) —
    the exact fields the model is grounded against, so the caller decides
    what's in scope rather than this function reaching into the database
    itself:
      - entries: {id, class_group_name, subject_name, teacher_name,
        day_of_week, order, period_label, locked}
      - periods: {id, day_of_week, order, label}
      - teachers: {id, name}

    Returns the raw tool-input dict (action, entry_id, target_period_id,
    target_teacher_id, other_entry_id, description) on success, or None
    if the LLM path can't be used right now (no key, package missing,
    call/response failed for any reason) — never raises. The router is
    responsible for validating every returned id actually appears in the
    lists passed in before mutating anything; this function only relays
    what the model said.
    """
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; conversational timetable editing unavailable")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        system_prompt = (
            "You resolve a school admin's plain-English timetable editing instruction "
            "into a specific, unambiguous edit using ONLY the entries/periods/teachers "
            "listed below. Use the record_edit_command tool.\n\n"
            f"Current timetable entries: {entries}\n\n"
            f"Available periods: {periods}\n\n"
            f"Known teachers: {teachers}\n\n"
            "Every id you return MUST be copied exactly from one of these lists — never "
            "invent an id. If the instruction could match more than one entry (e.g. a "
            "subject that appears several times in the week and no day/period was given "
            "to narrow it down), or no entry/period matches at all, use "
            "action='unresolved' and explain what's ambiguous in `description` rather "
            "than guessing."
        )
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=500,
            system=system_prompt,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_edit_command"},
            messages=[{"role": "user", "content": text}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        return tool_use.input
    except Exception:
        logger.exception("Conversational edit-command parsing failed")
        return None

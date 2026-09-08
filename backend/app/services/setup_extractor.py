"""
Setup-from-document extraction: an admin uploads a spreadsheet they
already have lying around — an old staff list, a manually-made timetable
export, whatever — that is NOT in this app's expected bulk-import column
format (see app/services/bulk_import.py), and Claude reads it freeform
and proposes teachers/subjects/class-groups to create.

This is deliberately a different, simpler code path than bulk_import.py:

  - bulk_import.py assumes a known header row (name, email,
    qualified_subjects, ...) and is precise/mechanical — it's for an
    admin who is willing to format a file to match this app.
  - This module assumes NOTHING about structure. The file might have no
    header row at all (e.g. a raw timetable grid with days as columns
    and teacher names in the grid), so rows are read as plain grids of
    cell strings and handed to Claude to interpret, not parsed into
    header-keyed dicts.

Because of that, this is read-only until the admin reviews the result:
extract_setup_llm() never touches the database, and nothing is created
until the admin explicitly confirms a selection through the /commit
endpoint (see app/routers/setup_extraction.py), which re-shapes the
confirmed items into the same row-dict shape bulk_import.py's import_*
functions expect and calls those directly — so upsert-by-name behavior,
"missing name" validation, etc. all come for free from that existing,
tested code rather than being reimplemented here.

Scope, v1 (documented, not silent):
  - CSV and .xlsx only, matching bulk_import.py's supported types. PDF
    upload is NOT supported — there's no PDF-parsing dependency in this
    codebase, and scanned/PDF staff lists would need OCR, which has very
    different failure modes (silently wrong text) than a spreadsheet
    read. Left as a known future gap rather than bolted on half-working.
  - Only the first MAX_ROWS rows of the file are sent to the LLM. This
    bounds prompt size/cost for the realistic case (a school's staff or
    class list) and is generous enough that no normal admin file will
    ever hit it in practice — if it does, the extraction will just be
    based on a truncated prefix rather than erroring, which is
    consistent with this codebase's "best-effort" bias (see
    bulk_import.py's docstring) but is worth knowing about.
  - Follows the same never-raises contract as
    app/services/llm_constraint_parser.py, email_service.py,
    infeasibility_explainer.py, and edit_command_parser.py: any failure
    (no API key, network error, malformed response) returns None rather
    than raising, and the router turns that into a clear error for the
    admin rather than a 500.
"""
import csv
import io
import logging

import openpyxl

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_ROWS = 200  # see module docstring

_TOOL_SCHEMA = {
    "name": "record_extracted_setup",
    "description": "Records the school setup data (teachers, subjects, class groups) found in an uploaded document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "teachers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": ["string", "null"]},
                        "subject_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Subjects this teacher appears qualified for or is shown teaching, "
                                "matching names in the subjects array by name. Empty if not evident."
                            ),
                        },
                    },
                    "required": ["name"],
                },
            },
            "subjects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
            "class_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "grade": {"type": ["string", "null"]},
                    },
                    "required": ["name"],
                },
            },
            "notes": {
                "type": "string",
                "description": (
                    "Anything ambiguous, inconsistent, or that couldn't be confidently extracted — "
                    "shown to the admin alongside the preview. Empty string if nothing to flag."
                ),
            },
        },
        "required": ["teachers", "subjects", "class_groups", "notes"],
    },
}

_SYSTEM_PROMPT = """You extract school staffing/scheduling setup data from an arbitrary \
spreadsheet a school admin uploaded. It could be a staff directory, a subject list, an \
existing manually-made timetable, or something else entirely — you don't know its \
structure in advance.

Identify:
- Distinct TEACHERS (by name). Include their email if a column clearly has one.
- Distinct SUBJECTS mentioned anywhere (a subject taught, a column header that's a
  subject name, a class period labeled with a subject, etc.).
- Distinct CLASS GROUPS — sections, divisions, or grades like "Grade 8 - A" or "10B".

Only extract what's clearly present. Do not invent teachers, subjects, or groups that \
aren't evidenced by the data. If a teacher's subjects are evident from context (e.g. a \
"subject" or "teaches" column, or their name appearing in a subject's row/column in a \
timetable grid), include those in subject_names — matching a name in the subjects list \
you're also returning. If genuinely unclear or inconsistent, leave it out and mention it \
in notes instead of guessing.

Call record_extracted_setup with your findings."""


def read_spreadsheet_rows(filename: str, content: bytes) -> list[list[str]]:
    """
    Reads an uploaded CSV/.xlsx file into a plain grid of cell strings —
    no header-row assumption, unlike bulk_import.py's parse_rows(), since
    this feature doesn't know the document's structure ahead of time.
    Raises ValueError (caught by the router, turned into a 400) for an
    unsupported file type or a genuinely empty file.
    """
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        text = content.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
    elif lower_name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
    else:
        raise ValueError(
            "Unsupported file type — upload a .csv or .xlsx file. "
            "(PDF documents aren't supported yet.)"
        )

    rows = [r for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("The file has no data in it.")
    return rows


def _rows_to_text(rows: list[list[str]]) -> str:
    truncated = rows[:MAX_ROWS]
    lines = [" | ".join(str(c).strip() for c in row) for row in truncated]
    text = "\n".join(lines)
    if len(rows) > MAX_ROWS:
        text += f"\n\n[... {len(rows) - MAX_ROWS} more rows omitted ...]"
    return text


def extract_setup_llm(rows: list[list[str]]) -> dict | None:
    """
    Sends the raw grid to Claude and returns the parsed tool-use input
    dict on success, or None on any failure (no API key configured, the
    anthropic package missing, a network/API error, or a malformed
    response) — never raises. The router treats None as "extraction
    isn't available right now" (503), the same pattern used by
    infeasibility_explainer.explain_infeasibility and
    edit_command_parser.parse_edit_command_llm.
    """
    if not rows:
        return None
    if not settings.anthropic_api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed; setup extraction unavailable")
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model,
            max_tokens=2000,
            system=_SYSTEM_PROMPT,
            tools=[_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "record_extracted_setup"},
            messages=[{"role": "user", "content": _rows_to_text(rows)}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_extracted_setup":
                return block.input
        return None
    except Exception:
        logger.exception("Setup extraction LLM call failed")
        return None

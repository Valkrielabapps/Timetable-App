"""
Import a school's own subjects or teachers sheet, whatever its layout.

Schools don't fill in templates; they upload the staff list they already
have - a title row above the headings, "Teacher Name" instead of "name",
"Subject 1 / Subject 2" columns, a second sheet with the real list. This
reads such a file into the rows app/services/bulk_import.py already knows
how to import:

  1. Every sheet is read, and the row that looks most like the headings is
     found (it needn't be the first).
  2. Each heading is matched to a field by name ("Teacher Name", "Staff",
     "Subjects Taught", "Classes", ...).
  3. Only if a heading is left over, or no name column was found, the AI is
     shown the headings and five sample rows - never the whole sheet - and
     asked which field each column is. A few thousand tokens per file,
     however long the list, and every row is still copied by code, exactly
     as typed.
  4. Columns that say the same thing are combined: "Subject 1" and
     "Subject 2" become one list, "First name" and "Last name" one name.

Subjects a teacher sheet mentions that the school doesn't have yet are
added as subjects, so one upload is enough.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re

import openpyxl
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.school import Subject
from app.services.uploads import capped, check_xlsx

logger = logging.getLogger(__name__)

# The fields each kind of sheet can fill, and what each is called in plain
# words (shown to the AI, and back to the school as "read as").
FIELDS = {
    "subjects": {
        "name": "subject name",
        "required_room_type": "type of room it needs (lab, computer room...)",
    },
    "teachers": {
        "name": "teacher's full name",
        "first_name": "teacher's first name",
        "last_name": "teacher's last name / surname",
        "email": "email address",
        "max_periods_per_week": "most periods a week they may teach",
        "qualified_subjects": "subjects they teach",
        "qualified_grades": "grades or classes they teach",
    },
}

# Headings matched without asking the AI. Compared after lowercasing and
# dropping everything but letters and digits, so "Teacher's Name:" and
# "TEACHER NAME" are the same.
SYNONYMS = {
    "subjects": {
        "name": ["name", "subject", "subjects", "subjectname", "subjecttitle", "title", "course", "paper"],
        "required_room_type": ["requiredroomtype", "roomtype", "room", "roomneeded", "lab", "venue", "venuetype"],
    },
    "teachers": {
        "name": ["name", "teacher", "teachername", "teachersname", "staff", "staffname", "faculty", "facultyname",
                 "fullname", "nameofteacher", "nameofthestaff", "nameofstaff", "employeename", "employee"],
        "first_name": ["firstname", "givenname", "fname"],
        "last_name": ["lastname", "surname", "familyname", "lname"],
        "email": ["email", "emailid", "emailaddress", "mail", "mailid"],
        "max_periods_per_week": ["maxperiodsperweek", "maxperiods", "periodsperweek", "workload", "load",
                                 "periodsweek", "maximumperiods", "weeklyload", "weeklyperiods"],
        "qualified_subjects": ["qualifiedsubjects", "subjects", "subject", "subjectstaught", "subjecttaught",
                               "teaches", "subjecthandled", "subjectshandled", "specialisation", "specialization"],
        "qualified_grades": ["qualifiedgrades", "grades", "grade", "eligiblegrades", "classes", "class",
                             "classestaught", "classtaught", "standards", "standard", "std", "gradestaught"],
    },
}

# Columns that may appear more than once and are merged into one list.
LIST_FIELDS = {"qualified_subjects", "qualified_grades"}

_SAMPLE_ROWS = 5


def _key(heading: str) -> str:
    return re.sub(r"[^a-z0-9]", "", heading.lower())


def _strip_number(key: str) -> str:
    """"subject1", "subject2" -> "subject": numbered copies of a column."""
    return re.sub(r"\d+$", "", key)


def read_sheets(filename: str, content: bytes) -> list[tuple[str, list[list[str]]]]:
    """Every sheet (one for a CSV) as rows of cell text, blank rows dropped."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        sheets = [("CSV", capped(csv.reader(io.StringIO(text))))]
    elif lower.endswith(".xlsx"):
        check_xlsx(content)
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets = [(ws.title, [["" if c is None else str(c) for c in row]
                              for row in capped(ws.iter_rows(values_only=True))]) for ws in wb.worksheets]
    else:
        raise ValueError("Upload the sheet as .xlsx or .csv (in Excel: File > Save As > Excel Workbook).")
    out = []
    for title, rows in sheets:
        # Blank rows kept, so a row's position is the one the school sees in Excel.
        rows = [[str(c).strip() for c in r] for r in rows]
        if any(any(c for c in r) for r in rows):
            out.append((title, rows))
    if not out:
        raise ValueError("The file has no data in it.")
    return out


def _rule_map(headings: list[str], kind: str) -> dict[int, str]:
    lookup = {}
    for field, words in SYNONYMS[kind].items():
        for w in words:
            lookup.setdefault(w, field)
    mapping: dict[int, str] = {}
    for i, h in enumerate(headings):
        k = _key(h)
        if not k:
            continue
        field = lookup.get(k)
        if field is None:
            # "Subject 2" is a numbered copy of a list column; "Teacher 7"
            # is a name in a data row, not a heading.
            stripped = lookup.get(_strip_number(k))
            field = stripped if stripped in LIST_FIELDS else None
        if field is None:
            continue
        if field in mapping.values() and field not in LIST_FIELDS:
            continue  # a second "name" column: keep the first
        mapping[i] = field
    return mapping


def _header_row(rows: list[list[str]], kind: str) -> tuple[int, dict[int, str]]:
    """The row among the first ten that matches the most known headings -
    a title like "Staff list 2026-27" above the headings is skipped."""
    best = (0, {}, -1)
    for idx, row in enumerate(rows[:12]):
        if not any(row):
            continue
        m = _rule_map(row, kind)
        score = len(m) + (2 if "name" in m.values() or "first_name" in m.values() else 0)
        if score > best[2]:
            best = (idx, m, score)
    if best[2] <= 0:
        # Nothing recognised: the first row with several filled cells.
        for idx, row in enumerate(rows[:10]):
            if sum(1 for c in row if c) >= 2:
                return idx, {}
        return 0, {}
    return best[0], best[1]


def _ai_map(headings: list[str], samples: list[list[str]], kind: str) -> dict[int, str] | None:
    """Ask the AI which field each column is, from the headings and a few
    rows only. None when there's no API key or the call fails."""
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    fields = FIELDS[kind]
    columns = "\n".join(
        f"{i}: heading {h!r}, e.g. " + ", ".join(repr(r[i]) for r in samples if i < len(r) and r[i])[:200]
        for i, h in enumerate(headings)
    )
    tool = {
        "name": "map_columns",
        "description": "Say which field each spreadsheet column holds.",
        "input_schema": {
            "type": "object",
            "properties": {
                "columns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "index": {"type": "integer"},
                            "field": {"type": "string", "enum": [*fields, "ignore"]},
                        },
                        "required": ["index", "field"],
                    },
                }
            },
            "required": ["columns"],
        },
    }
    prompt = (
        f"A school uploaded its {kind} list. Match each column to one of these fields, or 'ignore' if it is "
        "none of them (serial numbers, phone numbers, remarks...):\n"
        + "\n".join(f"- {f}: {d}" for f, d in fields.items())
        + "\n\nColumns:\n" + columns
    )
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.llm_model, max_tokens=600, tools=[tool],
            tool_choice={"type": "tool", "name": "map_columns"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "tool_use":
                out = {}
                for c in block.input.get("columns", []):
                    i, f = c.get("index"), c.get("field")
                    if isinstance(i, int) and 0 <= i < len(headings) and f in fields:
                        out[i] = f
                return out
    except Exception:  # noqa: BLE001 - the rule-based reading still stands
        logger.exception("smart import column mapping failed")
    return None


def smart_rows(kind: str, filename: str, content: bytes, ai=_ai_map) -> tuple[list[dict], dict]:
    """The file's rows keyed by bulk_import's field names, and what was read
    from where: {"sheet", "header_row", "read_as": [...], "used_ai"}."""
    best = None
    for title, rows in read_sheets(filename, content):
        idx, mapping = _header_row(rows, kind)
        score = len(mapping) + (2 if {"name", "first_name"} & set(mapping.values()) else 0)
        if best is None or score > best[0]:
            best = (score, title, rows, idx, mapping)
    _, title, rows, idx, mapping = best
    headings = rows[idx]
    body = [r for r in rows[idx + 1:] if any(r)]

    used_ai = False
    leftover = [i for i, h in enumerate(headings) if h and i not in mapping]
    has_name = {"name", "first_name"} & set(mapping.values())
    if leftover or not has_name:
        guessed = ai(headings, body[:_SAMPLE_ROWS], kind)
        if guessed:
            used_ai = True
            for i, f in guessed.items():
                if i in mapping:
                    continue
                if f in mapping.values() and f not in LIST_FIELDS:
                    continue
                mapping[i] = f
    if not ({"name", "first_name"} & set(mapping.values())):
        what = "subject" if kind == "subjects" else "teacher"
        raise ValueError(
            f"Couldn't find the column with each {what}'s name. Give that column a heading like "
            f"\"{what.capitalize()} name\" and upload again."
        )

    out = []
    for row in body:
        rec: dict[str, str] = {}
        lists: dict[str, list[str]] = {}
        first = last = ""
        for i, field in mapping.items():
            value = row[i].strip() if i < len(row) else ""
            if not value:
                continue
            if field in LIST_FIELDS:
                lists.setdefault(field, []).append(value)
            elif field == "first_name":
                first = value
            elif field == "last_name":
                last = value
            else:
                rec.setdefault(field, value)
        if not rec.get("name") and (first or last):
            rec["name"] = f"{first} {last}".strip()
        for field, values in lists.items():
            # "Maths / Physics" in one cell is two subjects, like "Maths; Physics".
            rec[field] = ";".join(v.replace("/", ";") for v in values)
        if kind == "teachers" and "qualified_grades" in mapping.values():
            rec.setdefault("qualified_grades", "")
        if rec.get("name"):
            out.append(rec)

    read_as = [f"“{headings[i]}” as {FIELDS[kind][f]}" for i, f in sorted(mapping.items()) if headings[i]]
    return out, {"sheet": title, "header_row": idx + 1, "read_as": read_as, "used_ai": used_ai}


def add_missing_subjects(db: Session, school_id: int, rows: list[dict]) -> list[str]:
    """Subjects a teacher sheet names that the school doesn't have yet,
    created so the teachers can be linked to them. Returns their names."""
    have = {s.name.lower() for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    added: list[str] = []
    for row in rows:
        for name in re.split(r"[;,]", row.get("qualified_subjects", "")):
            name = name.strip()
            if name and name.lower() not in have:
                db.add(Subject(school_id=school_id, name=name))
                have.add(name.lower())
                added.append(name)
    if added:
        db.commit()
    return added

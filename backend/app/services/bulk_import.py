"""
Bulk import: turns an uploaded CSV or Excel file into rows of Subjects,
Rooms, Teachers, or Class Groups, so a school with 40+ teachers doesn't
have to be typed in one at a time through the Data Entry forms.

Design choices:
  - CSV and .xlsx are both accepted, detected by file extension. openpyxl
    (already a dependency, used by app/services/export.py) reads the
    Excel case; the standard library's csv module handles CSV. Both paths
    converge on the same shape — a list of dicts keyed by the header
    row's column names, lowercased and stripped — so every import_*
    function below only has to deal with one input shape regardless of
    which file type was uploaded.
  - Best-effort, not all-or-nothing: a bad row (missing a required
    column, an unresolvable subject name, whatever) is recorded as an
    error and skipped, but every other row in the file still gets
    imported. A single typo shouldn't force a 40-row admin to fix and
    re-upload the whole spreadsheet from scratch. This mirrors the same
    philosophy as the solver's room assignment (best-effort, not
    infeasible-or-nothing) and constraint parsing (fall back, don't
    block) elsewhere in this codebase.
  - Upsert by name (or grade+name for class groups), not blind insert:
    re-uploading the same file (e.g. after fixing a typo in one row) is
    idempotent rather than creating duplicates, which matters because the
    realistic workflow is "export current roster, edit it, re-upload."
"""
import csv
import io
import re
from dataclasses import dataclass, field

import openpyxl
from sqlalchemy.orm import Session

from app.models.school import ClassGroup, Room, Subject, Teacher


@dataclass
class BulkImportResult:
    created: int = 0
    updated: int = 0
    # human-readable, e.g. "Row 4: missing required 'name' column"
    errors: list[str] = field(default_factory=list)


def parse_rows(filename: str, content: bytes) -> list[dict]:
    """
    Parses an uploaded file into a list of row dicts keyed by lowercased,
    stripped header names. Raises ValueError (caught by the router and
    turned into a 400) if the file type isn't recognized or has no header
    row — everything past that point is per-row, not per-file, error
    handling.
    """
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        text = content.decode("utf-8-sig")  # -sig strips a BOM, common from Excel's "Save as CSV"
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    elif lower_name.endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
    else:
        raise ValueError("Unsupported file type — upload a .csv or .xlsx file.")

    rows = [r for r in rows if any(str(c).strip() for c in r)]  # drop fully blank rows
    if not rows:
        raise ValueError("The file has no data in it.")

    header = [str(c).strip().lower() for c in rows[0]]
    data_rows = []
    for row in rows[1:]:
        padded = list(row) + [""] * (len(header) - len(row))  # short rows just get blank trailing cells
        data_rows.append({header[i]: str(padded[i]).strip() for i in range(len(header))})
    return data_rows


def _int_or_none(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))  # float() first so "40.0" from Excel doesn't raise
    except ValueError:
        return None


def import_subjects(db: Session, school_id: int, rows: list[dict]) -> BulkImportResult:
    """Expected columns: name (required), required_room_type (optional)."""
    result = BulkImportResult()
    existing = {s.name.lower(): s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}

    for i, row in enumerate(rows, start=2):  # row 1 is the header
        name = row.get("name", "").strip()
        if not name:
            result.errors.append(f"Row {i}: missing required 'name' column")
            continue
        required_room_type = row.get("required_room_type", "").strip() or None

        match = existing.get(name.lower())
        if match:
            match.required_room_type = required_room_type
            result.updated += 1
        else:
            subject = Subject(school_id=school_id, name=name, required_room_type=required_room_type)
            db.add(subject)
            existing[name.lower()] = subject
            result.created += 1

    db.commit()
    return result


def import_rooms(db: Session, school_id: int, rows: list[dict]) -> BulkImportResult:
    """Expected columns: name (required), capacity (optional int), room_type (optional)."""
    result = BulkImportResult()
    existing = {r.name.lower(): r for r in db.query(Room).filter(Room.school_id == school_id).all()}

    for i, row in enumerate(rows, start=2):
        name = row.get("name", "").strip()
        if not name:
            result.errors.append(f"Row {i}: missing required 'name' column")
            continue
        capacity = _int_or_none(row.get("capacity", ""))
        room_type = row.get("room_type", "").strip() or None

        match = existing.get(name.lower())
        if match:
            match.capacity = capacity
            match.room_type = room_type
            result.updated += 1
        else:
            room = Room(school_id=school_id, name=name, capacity=capacity, room_type=room_type)
            db.add(room)
            existing[name.lower()] = room
            result.created += 1

    db.commit()
    return result


# Accepted headers for the grades column. Schools write their own sheets, and
# a header the importer doesn't recognise is skipped without a word - which is
# exactly how a "subjects" column went missing once.
GRADE_COLUMNS = ("qualified_grades", "grades", "eligible_grades")


_ROMAN = {r: str(n) for n, r in enumerate(
    ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"], start=1)}


def _grade_key(label: str) -> str:
    """A grade label reduced to what people actually vary: "Grade 6",
    "Class 6", "Class VI", "Std. 6", "6th", "6" - and "6.0", which is how
    Excel hands back a cell holding just the number - all become "6"."""
    key = re.sub(r"\s+", " ", label.strip().lower())
    key = re.sub(r"^(grade|class|std\.?|standard)\s*", "", key)
    key = re.sub(r"^(\d+)(st|nd|rd|th|\.0)$", r"\1", key)
    return _ROMAN.get(key, key)


def _resolve_grades(raw: str, grades: list[str]) -> tuple[list[str], list[str]]:
    """Turn a grades cell into the school's own grade labels.

    Returns (resolved, unresolved). Each item may be a grade as the school
    writes it ("Grade 6"), loosely ("6", "Class 6", "6th"), or a range of
    numbered grades ("6-8", "Grade 6 to Grade 8"). Resolved labels are the
    school's exact strings, because that is what the solver compares against
    each section's grade.
    """
    exact = {g.lower(): g for g in grades}
    by_key: dict[str, str] = {}
    for g in grades:
        by_key.setdefault(_grade_key(g), g)

    resolved: list[str] = []
    unresolved: list[str] = []
    for item in [t.strip() for t in raw.replace(";", ",").split(",") if t.strip()]:
        # Whole item first, so a grade with a hyphen in its name ("Pre-KG")
        # is never mistaken for a range.
        match = exact.get(item.lower()) or by_key.get(_grade_key(item))
        if match:
            found = [match]
        else:
            ends = re.split(r"\s*(?:-|–|\bto\b)\s*", item, flags=re.IGNORECASE)
            low, high = (_grade_key(e) for e in ends) if len(ends) == 2 else ("", "")
            if low.isdigit() and high.isdigit():
                lo, hi = sorted((int(low), int(high)))
                found = [g for g in grades if _grade_key(g).isdigit() and lo <= int(_grade_key(g)) <= hi]
            else:
                found = []
        if not found:
            unresolved.append(item)
        for g in found:
            if g not in resolved:
                resolved.append(g)
    return resolved, unresolved


def import_teachers(db: Session, school_id: int, rows: list[dict]) -> BulkImportResult:
    """
    Expected columns: name (required), email (optional),
    max_periods_per_week (optional int), qualified_subjects (optional —
    subject names separated by ';' or ',', matched case-insensitively
    against this school's existing subjects; add the subjects first if
    they don't exist yet, or they're silently skipped with a warning),
    qualified_grades (optional — also accepted as "grades" or
    "eligible_grades"; see below).

    Grades: the grades a teacher may teach, separated by ';' or ','. Matched
    against the grades of the school's sections, loosely - "6", "Class 6" and
    "Grade 6" are the same grade - and "6-8" is a range. An EMPTY cell means
    every grade. With no grades column at all, a teacher's existing grades are
    left as they are.
    """
    result = BulkImportResult()
    existing = {t.name.lower(): t for t in db.query(Teacher).filter(Teacher.school_id == school_id).all()}
    subjects_by_name = {s.name.lower(): s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    # Natural order - "Grade 6" before "Grade 11" - so ranges and the grades
    # listed in an error read the way the school counts them.
    school_grades = sorted(
        {g for (g,) in db.query(ClassGroup.grade).filter(ClassGroup.school_id == school_id) if g},
        key=lambda g: [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", g.lower())],
    )

    for i, row in enumerate(rows, start=2):
        name = row.get("name", "").strip()
        if not name:
            result.errors.append(f"Row {i}: missing required 'name' column")
            continue
        email = row.get("email", "").strip() or None
        max_periods = _int_or_none(row.get("max_periods_per_week", ""))

        qualified_ids = []
        raw_subjects = row.get("qualified_subjects", "")
        if raw_subjects:
            names = [n.strip() for n in raw_subjects.replace(";", ",").split(",") if n.strip()]
            unresolved = []
            for sname in names:
                subj = subjects_by_name.get(sname.lower())
                if subj:
                    qualified_ids.append(subj.id)
                else:
                    unresolved.append(sname)
            if unresolved:
                result.errors.append(
                    f"Row {i} ({name}): couldn't match subject(s) {', '.join(unresolved)} — "
                    f"add them as subjects first, then re-import to pick them up."
                )

        # None = leave as is. [] = every grade.
        grades_column = next((c for c in GRADE_COLUMNS if c in row), None)
        qualified_grades: list[str] | None = None
        if grades_column is not None:
            raw_grades = row.get(grades_column, "").strip()
            if not raw_grades:
                qualified_grades = []
            else:
                resolved, unresolved_grades = _resolve_grades(raw_grades, school_grades)
                is_existing = name.lower() in existing
                if unresolved_grades:
                    where = (
                        f"this school's grades are {', '.join(school_grades)}"
                        if school_grades
                        else "this school has no sections with a grade yet - add them first"
                    )
                    if resolved:
                        kept = "the rest were applied"
                    elif is_existing:
                        kept = "grades left unchanged"
                    else:
                        kept = "teacher left eligible for every grade"
                    result.errors.append(
                        f"Row {i} ({name}): couldn't match grade(s) {', '.join(unresolved_grades)} "
                        f"({where}); {kept}."
                    )
                # Nothing matched: don't widen an existing teacher to every
                # grade because of a typo.
                if resolved or not is_existing:
                    qualified_grades = resolved

        match = existing.get(name.lower())
        if match:
            match.email = email
            match.max_periods_per_week = max_periods
            if qualified_ids:
                match.qualified_subject_ids = qualified_ids
            if qualified_grades is not None:
                match.qualified_grades = qualified_grades
            result.updated += 1
        else:
            teacher = Teacher(
                school_id=school_id,
                name=name,
                email=email,
                max_periods_per_week=max_periods,
                qualified_subject_ids=qualified_ids,
                qualified_grades=qualified_grades or [],
            )
            db.add(teacher)
            existing[name.lower()] = teacher
            result.created += 1

    db.commit()
    return result


def import_class_groups(
    db: Session, school_id: int, rows: list[dict],
    max_new: int | None = None, limit_message: str | None = None,
) -> BulkImportResult:
    """Expected columns: name (required), grade (optional), student_count (optional int).

    max_new caps how many *new* sections may be created (the school's plan
    allowance, app/services/plans.py); updates to existing sections are never
    capped. Rows past the cap are skipped and reported, not silently dropped."""
    result = BulkImportResult()
    skipped_for_plan = 0
    groups = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    existing = {(g.grade or "").lower(): {} for g in groups}
    for g in groups:
        existing.setdefault((g.grade or "").lower(), {})[g.name.lower()] = g

    for i, row in enumerate(rows, start=2):
        name = row.get("name", "").strip()
        if not name:
            result.errors.append(f"Row {i}: missing required 'name' column")
            continue
        grade = row.get("grade", "").strip() or None
        student_count = _int_or_none(row.get("student_count", ""))

        match = existing.get((grade or "").lower(), {}).get(name.lower())
        if match:
            match.student_count = student_count
            result.updated += 1
        elif max_new is not None and result.created >= max_new:
            skipped_for_plan += 1
        else:
            cg = ClassGroup(school_id=school_id, grade=grade, name=name, student_count=student_count)
            db.add(cg)
            existing.setdefault((grade or "").lower(), {})[name.lower()] = cg
            result.created += 1

    if skipped_for_plan:
        result.errors.append(
            f"{skipped_for_plan} section{'s' if skipped_for_plan != 1 else ''} not added. "
            + (limit_message or "Your plan's section limit has been reached.")
        )
    db.commit()
    return result


# Downloadable starter templates — header row + one example row, so an
# admin doesn't have to guess column names or formatting from scratch.
TEMPLATES: dict[str, str] = {
    "subjects": "name,required_room_type\nChemistry,lab\nMath,\n",
    "rooms": "name,capacity,room_type\nRoom 101,35,\nChem Lab,30,lab\n",
    "teachers": "name,email,max_periods_per_week,qualified_subjects,qualified_grades\n"
                "Priya Sharma,priya@example.com,24,Math;Science,Grade 6;Grade 7\n"
                "Rahul Mehta,rahul@example.com,28,English,\n",
    "class_groups": "name,grade,student_count\nA,Grade 8,32\nB,Grade 8,30\n",
}

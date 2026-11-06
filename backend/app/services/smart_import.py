"""
Import a school's own subjects or teachers sheet, whatever its layout.

Schools don't fill in templates; they upload the staff list they already
have. This reads it into the rows app/services/bulk_import.py imports, with
the AI doing the understanding and code doing the copying:

  1. Every sheet is read, and the row that looks most like the headings is
     found (it needn't be the first).
  2. The AI looks at the headings and five sample rows - never the whole
     sheet - and says what each column is, even when the heading looks
     familiar: a "Class" column can be the class a teacher is in charge of,
     not the classes they teach. It also says how the sheet is laid out: one
     teacher per row; a grid with a column per subject (or grade) and a mark
     where a teacher teaches it; or teachers across the top instead of down
     the side, which is turned round first.
  3. Every row is then read by code, exactly as typed.
  4. The different subject and grade values in the sheet - usually a few
     dozen short words - go to the AI once more, with the school's own
     subjects and grades, to say what each one means: "Maths", "Math" and
     "Mathematics" are one subject, "Eng" is English, "IX" and "Std 9" are
     Grade 9, "Maths and Physics" is two subjects.

Without an API key (or if a call fails) the same steps run on rules - known
headings, common short forms - so an upload never depends on the AI being
there; it is just read less cleverly. Subjects a teacher sheet mentions that
the school doesn't have yet are added, so one upload is enough.
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
        "subject_mark": "a column for one subject (named in the heading): a tick, Y, X or a number means "
                        "the teacher teaches it",
        "grade_mark": "a column for one grade or class (named in the heading): a mark means the teacher "
                      "teaches it",
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


def read_sheets(filename: str, content: bytes, kind: str = "teachers") -> list[tuple[str, list[list[str]]]]:
    """Every sheet (one for a CSV; each table of a Word document) as rows
    of cell text. Blank rows kept, so a row's position is the one the school
    sees in Excel."""
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        sheets = [("CSV", capped(csv.reader(io.StringIO(text))))]
    elif lower.endswith(".xlsx"):
        check_xlsx(content)
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets = [(ws.title, [["" if c is None else str(c) for c in row]
                              for row in capped(ws.iter_rows(values_only=True))]) for ws in wb.worksheets]
    elif lower.endswith(".docx"):
        sheets = docx_sheets(content, kind)
    elif lower.endswith(".doc"):
        raise ValueError("That's an old Word file (.doc). In Word: File > Save As > Word Document (.docx), "
                         "then upload that.")
    else:
        raise ValueError("Upload the list as an Excel sheet (.xlsx), a CSV or a Word document (.docx).")
    out = []
    for title, rows in sheets:
        rows = [[str(c).strip() for c in r] for r in rows]
        if any(any(c for c in r) for r in rows):
            out.append((title, rows))
    if not out:
        raise ValueError("The file has no data in it.")
    return out


# ------------------------------------------------------- Word documents

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# "Priya Sharma - Maths, Physics", "Priya Sharma: Maths", "Priya Sharma (Maths)"
_LINE = re.compile(r"^(?:\d+[.)]\s*)?(.+?)\s*(?:\s[-\u2013\u2014]\s|:|\t|\()\s*(.+?)\)?$")


def _text(el) -> str:
    """A paragraph's or cell's text: tabs kept, line breaks as new lines,
    paragraphs on their own lines."""
    paras = []
    for p in el.iter(f"{_W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        paras.append("".join(parts))
    return "\n".join(paras)


def _table_rows(tbl) -> list[list[str]]:
    rows, above = [], []
    for tr in tbl.findall(f"{_W}tr"):
        row = []
        for tc in tr.findall(f"{_W}tc"):
            pr = tc.find(f"{_W}tcPr")
            span = pr.find(f"{_W}gridSpan") if pr is not None else None
            merge = pr.find(f"{_W}vMerge") if pr is not None else None
            text = _text(tc).strip()
            col = len(row)
            # A cell merged down from the one above ("Priya Sharma" over two
            # subject rows) belongs to every row it covers.
            if merge is not None and merge.get(f"{_W}val") in (None, "continue") and col < len(above):
                text = above[col]
            row.append(text)
            width = int(span.get(f"{_W}val", "1")) if span is not None else 1
            row += [""] * (width - 1)
        rows.append(row)
        above = row
    return rows


def _list_rows(lines: list[str], kind: str) -> list[list[str]] | None:
    """A list typed as text, one per line: split by tabs, "Name - subjects",
    "Name: subjects", or just names."""
    lines = [ln.strip() for ln in lines if ln.strip()]
    if not lines:
        return None
    tabbed = [ln for ln in lines if "\t" in ln]
    if len(tabbed) >= 0.6 * len(lines):
        return [re.split(r"\t+", ln) for ln in lines]
    pairs = [_LINE.match(ln) for ln in lines]
    second = "Subjects" if kind == "teachers" else "Details"
    if sum(1 for m in pairs if m) >= 0.6 * len(lines):
        # A heading line or title above the list has no separator: dropped.
        return [["Name", second]] + [[m.group(1).strip(), m.group(2).strip()] for m in pairs if m]
    # Just names. A first line like "Subjects" or "List of teachers" is the
    # list's title, not one of them.
    titles = set(SYNONYMS[kind]["name"]) | {"teachers", "subjects", "stafflist", "teacherslist", "subjectlist",
                                             "subjectslist", "listofteachers", "listofsubjects", "ourteachers",
                                             "oursubjects", "teachingstaff"}
    if _key(lines[0]) in titles or _strip_number(_key(lines[0])) in titles:
        lines = lines[1:]
    return [["Name"]] + [[re.sub(r"^\d+[.)]\s*", "", ln)] for ln in lines]


def docx_sheets(content: bytes, kind: str = "teachers") -> list[tuple[str, list[list[str]]]]:
    """A Word document read like a workbook: each table is a sheet (tables
    with the same headings, one per department say, joined into one), and a
    document without tables is read as a list, one per line."""
    import zipfile
    from xml.etree import ElementTree

    check_xlsx(content, what="Word document")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
    except KeyError:
        raise ValueError("That file isn't a valid Word document (.docx).") from None
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise ValueError("That file isn't a valid Word document (.docx).")
    body = ElementTree.fromstring(xml).find(f"{_W}body")
    if body is None:
        raise ValueError("The file has no data in it.")

    tables: list[tuple[str, list[list[str]]]] = []
    lines: list[str] = []
    for el in body:
        if el.tag == f"{_W}tbl":
            rows = capped(_table_rows(el))
            if not any(any(c for c in r) for r in rows):
                continue
            head = next((r for r in rows if any(r)), [])
            same = next((t for t in tables if next((r for r in t[1] if any(r)), None) == head), None)
            if same is not None and len(head) > 1:
                start = rows.index(head) + 1
                same[1].extend(rows[start:])
            else:
                tables.append((f"table {len(tables) + 1} of the document", rows))
        elif el.tag == f"{_W}p":
            lines += _text(el).split("\n")
    if tables:
        return tables
    rows = _list_rows(capped(lines), kind)
    return [("the document's text", rows)] if rows else []


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


# ---------------------------------------------------------------- the AI

# Marks that mean "yes" under a subject or grade column in a grid layout,
# and the ones that plainly mean "no". Anything else filled in - a tick, a
# number of periods, a section letter - counts as yes.
_NO_MARKS = {"n", "no", "-", "--", "0", "false", "nil", "na", "n/a", "none"}


def _marked(value: str) -> bool:
    v = value.strip().lower()
    return bool(v) and v not in _NO_MARKS


class LiveAI:
    """The two questions the importer asks the AI. Each sees only a small
    piece of the sheet; each returns None when there's no API key or the
    call fails, and the importer carries on with its rules."""

    def _ask(self, tool: dict, prompt: str, max_tokens: int = 1200):
        if not settings.anthropic_api_key:
            return None
        try:
            import anthropic
        except ImportError:
            return None
        try:
            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
            response = client.messages.create(
                model=settings.llm_model, max_tokens=max_tokens, tools=[tool],
                tool_choice={"type": "tool", "name": tool["name"]},
                messages=[{"role": "user", "content": prompt}],
            )
            for block in response.content:
                if block.type == "tool_use":
                    return block.input
        except Exception:  # noqa: BLE001 - the rules still stand
            logger.exception("smart import AI call failed (%s)", tool["name"])
        return None

    def columns(self, headings: list[str], samples: list[list[str]], kind: str,
                school_subjects: list[str]) -> dict | None:
        """{"layout": "rows" | "teachers_across", "columns": {index: field}}"""
        fields = FIELDS[kind]
        listing = "\n".join(
            f"{i}: heading {h!r}, e.g. " + ", ".join(repr(r[i]) for r in samples if i < len(r) and r[i])[:240]
            for i, h in enumerate(headings)
        )
        tool = {
            "name": "read_sheet",
            "description": "Say how the sheet is laid out and what each column holds.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "layout": {"type": "string", "enum": ["rows", "teachers_across"]},
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
                    },
                },
                "required": ["layout", "columns"],
            },
        }
        layouts = (
            "\nLayout: 'rows' if each row is one teacher (the usual case, including grids where each subject "
            "or class has its own column); 'teachers_across' if the teachers' names run along the top as column "
            "headings and subjects or classes run down the side."
            if kind == "teachers" else "\nLayout: always 'rows'."
        )
        prompt = (
            f"A school uploaded its {kind} list. Say what each column holds, using one of these fields, or "
            "'ignore' for anything else (serial numbers, phone numbers, remarks, the class a teacher is in "
            "charge of as class teacher, a teacher's own qualifications...). Judge by the sample values as "
            "well as the heading.\n"
            + "\n".join(f"- {f}: {d}" for f, d in fields.items())
            + layouts
            + (f"\nThe school's subjects so far: {', '.join(school_subjects)}." if school_subjects else "")
            + "\n\nColumns:\n" + listing
        )
        out = self._ask(tool, prompt)
        if not out:
            return None
        cols = {}
        for c in out.get("columns", []):
            i, f = c.get("index"), c.get("field")
            if isinstance(i, int) and 0 <= i < len(headings) and (f in fields or f == "ignore"):
                cols[i] = f
        layout = out.get("layout") if out.get("layout") in ("rows", "teachers_across") else "rows"
        return {"layout": layout, "columns": cols}

    def values(self, subject_items: list[str], grade_items: list[str],
               school_subjects: list[str], school_grades: list[str]) -> dict | None:
        """{"subjects": {item: [names]}, "grades": {item: [school grades]}}"""
        if not subject_items and not grade_items:
            return {"subjects": {}, "grades": {}}
        pair = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"item": {"type": "string"}, "means": {"type": "array", "items": {"type": "string"}}},
                "required": ["item", "means"],
            },
        }
        tool = {
            "name": "match_values",
            "description": "Say what each value from the sheet means.",
            "input_schema": {
                "type": "object",
                "properties": {"subjects": pair, "grades": pair},
                "required": ["subjects", "grades"],
            },
        }
        prompt = (
            "These values come from a school's spreadsheet of teachers.\n\n"
            "SUBJECTS. For each value, list the subject(s) it means. Use the school's own name when it is the "
            "same subject (\"Maths\", \"Math\" -> \"Mathematics\" if that is the school's name); otherwise a "
            "clean, properly capitalised name, and the same name every time the same subject appears. A value "
            "can name several (\"Maths and Physics\") or none (\"-\", \"NA\"): then give []. Keep subjects "
            "the school keeps apart apart (English Language and English Literature are two).\n"
            f"School's subjects: {', '.join(school_subjects) or '(none yet)'}\n"
            f"Values: {json.dumps(subject_items, ensure_ascii=False)}\n\n"
            "GRADES. For each value, list which of the school's grades it means (\"IX\" or \"Std 9\" -> "
            "\"Grade 9\", \"6 to 8\" -> three grades, \"Primary\" -> the school's primary grades). Only "
            "the school's exact grade names; [] if it doesn't name any.\n"
            f"School's grades: {', '.join(school_grades) or '(none yet)'}\n"
            f"Values: {json.dumps(grade_items, ensure_ascii=False)}"
        )
        out = self._ask(tool, prompt, max_tokens=2500)
        if not out:
            return None
        grades_ok = set(school_grades)
        subjects = {}
        for p in out.get("subjects", []):
            item, means = p.get("item"), p.get("means")
            if isinstance(item, str) and isinstance(means, list):
                subjects[item] = [m.strip() for m in means if isinstance(m, str) and m.strip() and len(m) <= 60]
        grades = {}
        for p in out.get("grades", []):
            item, means = p.get("item"), p.get("means")
            if isinstance(item, str) and isinstance(means, list):
                grades[item] = [m for m in means if m in grades_ok]
        return {"subjects": subjects, "grades": grades}


# ------------------------------------------------------- reading the sheet

# Short forms read without the AI, as a fallback. Keyed by a subject's
# letters only; a value matches a school subject when both reduce to the
# same key.
_SUBJECT_ALIASES = {
    "math": "math", "maths": "math", "mathematics": "math",
    "bio": "biology", "biology": "biology",
    "phy": "physics", "physics": "physics",
    "chem": "chemistry", "chemistry": "chemistry",
    "cs": "computer", "comp": "computer", "computer": "computer", "computers": "computer",
    "computerscience": "computer", "computerapplications": "computer",
    "sst": "social", "socialstudies": "social", "socialscience": "social", "sscience": "social",
    "evs": "evs", "environmentalstudies": "evs", "environmentalscience": "evs",
    "pe": "pe", "pt": "pe", "physicaleducation": "pe", "games": "pe", "sports": "pe",
    "gk": "gk", "generalknowledge": "gk",
}


def _concept(name: str) -> str:
    k = _key(name)
    return _SUBJECT_ALIASES.get(k, k)


def _rule_subjects(items: list[str], school_subjects: list[str]) -> dict[str, list[str]]:
    by_concept = {_concept(s): s for s in school_subjects}
    out, new_by_concept = {}, {}
    for item in items:
        c = _concept(item)
        if not c:
            out[item] = []
        elif c in by_concept:
            out[item] = [by_concept[c]]
        else:
            # Two spellings of one new subject become one.
            out[item] = [new_by_concept.setdefault(c, item.strip())]
    return out


def _split_items(cell: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;,/\n]", cell) if p.strip()]


def _rule_marks(headings, body, mapping, school_subjects, school_grades) -> dict[int, str]:
    """Without the AI: a grid with a column per subject or grade, found by
    headings that are the school's subjects or grades over columns of short
    marks."""
    from app.services.bulk_import import _resolve_grades

    concepts = {_concept(x) for x in school_subjects} | set(_SUBJECT_ALIASES.values())
    out = dict(mapping)
    for i, h in enumerate(headings):
        if i in out or not h:
            continue
        values = [r[i].strip() for r in body if i < len(r) and r[i].strip()]
        if not values or sum(1 for v in values if len(v) <= 3) < 0.8 * len(values):
            continue
        if _concept(h) in concepts:
            out[i] = "subject_mark"
        elif school_grades and _resolve_grades(h, school_grades)[0]:
            out[i] = "grade_mark"
    return out


def _transpose(rows: list[list[str]], start: int) -> list[list[str]]:
    """Teachers across the top: turn the sheet so each teacher is a row."""
    block = [r for r in rows[start:] if any(r)]
    width = max(len(r) for r in block)
    block = [r + [""] * (width - len(r)) for r in block]
    return [list(col) for col in zip(*block)]


# ------------------------------------------------- one small table per class

# The commonest staff sheet in Indian schools: for each class a little table
# - a label ("CLASS 6-AB"), then Subjects | Periods | Teacher, then a Total -
# several side by side and several stacked. Read as one big table it gives
# "Total" and "CLASS 6-AB" as subjects and misses every table but the first.

_SUBJECT_HEADS = {"subjects", "subject", "subjectname"}
_TEACHER_HEADS = {"teacher", "teachers", "teachername", "faculty", "staff", "subjectteacher", "nameofteacher"}
_PERIOD_HEADS = {"periods", "period", "periodsperweek", "noofperiods", "periodsweek", "pds", "load"}
_CLASS_LABEL = re.compile(r"^\s*(?:class|grade|std\.?|standard)\b", re.I)
_NOT_A_TEACHER = {"classteacher", "ct", "tbd", "tba", "vacant", "new", "newteacher", "none", "na", "nil", "all",
                  "allteachers"}


def is_label(text: str) -> bool:
    """A heading, total, class label or note, never a subject or teacher."""
    t = text.strip()
    k = _key(t)
    if not k or k.isdigit():
        return True
    if k in _SUBJECT_HEADS | _TEACHER_HEADS | _PERIOD_HEADS | {"name", "names", "sno", "srno", "slno"}:
        return True
    if k.startswith("total") or k in ("grandtotal", "sum"):
        return True
    if _CLASS_LABEL.match(t):
        return True
    # A sentence: "Science Practical periods should be together".
    return len(t.split()) >= 5 or t.endswith(".")


def _grade_of(label: str) -> str | None:
    """"CLASS 6-AB" -> "6", "Class 9 (Sci)" -> "9", "Std IX" -> "IX"."""
    m = re.search(r"(?:class|grade|std\.?|standard)\s*[-:]?\s*(\d{1,2}|[ivx]{1,4})\b", label, re.I)
    if m:
        return m.group(1).upper() if not m.group(1).isdigit() else m.group(1)
    m = re.search(r"\b(\d{1,2})\b", label)
    return m.group(1) if m else None


def _class_tables(rows: list[list[str]]) -> list[dict]:
    """Every Subjects | (Periods) | Teacher table in a sheet, with the label
    above it and the rows under it."""
    def cell(r, c):
        return rows[r][c].strip() if r < len(rows) and c < len(rows[r]) else ""

    anchors = []
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            if _key(v) not in _SUBJECT_HEADS:
                continue
            near = {_key(cell(r, c + d)): c + d for d in (1, 2, 3)}
            tea = next((i for k, i in near.items() if k in _TEACHER_HEADS), None)
            per = next((i for k, i in near.items() if k in _PERIOD_HEADS), None)
            if tea is not None or per is not None:
                anchors.append((r, c, per, tea))
    tables = []
    for n, (r, c, per, tea) in enumerate(anchors):
        label = ""
        for up in (1, 2, 3):
            if r - up < 0:
                break
            found = next((cell(r - up, cc) for cc in range(c, (tea or per or c) + 1) if cell(r - up, cc)), "")
            if found:
                label = found
                break
        items, blanks = [], 0
        for rr in range(r + 1, len(rows)):
            subj = cell(rr, c)
            teacher = cell(rr, tea) if tea is not None else ""
            k = _key(subj)
            if k in _SUBJECT_HEADS or _CLASS_LABEL.match(subj) or k.startswith("total"):
                break
            if not subj and not teacher:
                blanks += 1
                if blanks >= 2:
                    break
                continue
            blanks = 0
            if subj and not is_label(subj):
                items.append((subj, cell(rr, per) if per is not None else "", teacher))
        tables.append({"label": label or f"table {n + 1}", "items": items})
    return [t for t in tables if t["items"]]


def _split_people(cell: str) -> list[str]:
    out = []
    for p in re.split(r"\s*(?:/|,|&|\band\b|\+)\s*", cell):
        p = p.strip(" .-")
        if p and _key(p) not in _NOT_A_TEACHER and not is_label(p):
            out.append(p)
    return out


def _split_subjects(cell: str) -> list[str]:
    return [p.strip(" .-") for p in re.split(r"\s*(?:/|,|\+|&)\s*", cell) if p.strip(" .-")]


def _from_class_tables(tables: list[dict], kind: str, school_grades: list[str]) -> tuple[list[str], list[list[str]], dict]:
    """The class tables as one plain table the rest of the importer reads:
    subjects, or teachers with what and which classes they teach."""
    if kind == "subjects":
        names = list(dict.fromkeys(s for t in tables for subj, _, _ in t["items"] for s in _split_subjects(subj)))
        return ["Subject"], [[n] for n in names], {0: "name"}
    teachers: dict[str, dict] = {}
    for t in tables:
        grade = _grade_of(t["label"])
        for subj, _, cell in t["items"]:
            people, subjects = _split_people(cell), _split_subjects(subj)
            # "Maths/Bio" taught by "Aman/Deepak": Aman Maths, Deepak Bio.
            paired = len(people) == len(subjects) > 1
            for i, person in enumerate(people):
                rec = teachers.setdefault(_key(person), {"name": person, "subjects": [], "grades": []})
                rec["subjects"] += [subjects[i]] if paired else subjects
                if grade:
                    rec["grades"].append(grade)
    headings = ["Teacher", "Subjects"] + (["Classes"] if school_grades else [])
    body = [[r["name"], ";".join(dict.fromkeys(r["subjects"]))]
            + ([";".join(dict.fromkeys(r["grades"]))] if school_grades else []) for r in teachers.values()]
    mapping = {0: "name", 1: "qualified_subjects"} | ({2: "qualified_grades"} if school_grades else {})
    return headings, body, mapping


def smart_rows(kind: str, filename: str, content: bytes, school_subjects=(), school_grades=(),
               ai=None) -> tuple[list[dict], dict]:
    """The file's rows keyed by bulk_import's field names, with subjects and
    grades already matched to the school's own, and an account of how it was
    read: {"sheet", "header_row", "layout", "read_as", "matched", "used_ai"}."""
    ai = LiveAI() if ai is None else ai
    school_subjects, school_grades = list(school_subjects), list(school_grades)

    sheets = read_sheets(filename, content, kind)
    # One small table per class, anywhere on a sheet: read every one of them.
    by_class = max(((title, _class_tables(rows)) for title, rows in sheets), key=lambda x: len(x[1]))
    class_tables = by_class[1] if len(by_class[1]) >= 2 else []

    used_ai = False
    layout = "rows"
    if class_tables:
        title, layout = by_class[0], "class_tables"
        headings, body, mapping = _from_class_tables(class_tables, kind, school_grades)
        rows, idx = [headings] + body, 0
    else:
        best = None
        for title, rows in sheets:
            idx, mapping = _header_row(rows, kind)
            score = len(mapping) + (2 if {"name", "first_name"} & set(mapping.values()) else 0)
            if best is None or score > best[0]:
                best = (score, title, rows, idx, mapping)
        _, title, rows, idx, mapping = best
        headings = rows[idx]
        body = [r for r in rows[idx + 1:] if any(r)]

    def confirm(headings, body, mapping):
        answer = ai.columns(headings, body[:_SAMPLE_ROWS], kind, school_subjects)
        if not answer:
            return None, mapping
        merged = dict(mapping)
        for i, f in answer["columns"].items():
            merged[i] = f  # the AI's reading wins, "ignore" included
        merged = {i: f for i, f in merged.items() if f != "ignore"}
        return answer["layout"], merged

    found_layout, confirmed = (layout, mapping) if class_tables else confirm(headings, body, mapping)
    if class_tables:
        found_layout = None
    elif found_layout is None and kind == "teachers":
        mapping = _rule_marks(headings, body, mapping, school_subjects, school_grades)
    if found_layout is not None:
        used_ai = True
        mapping = confirmed
        if found_layout == "teachers_across" and kind == "teachers":
            layout = "teachers_across"
            rows = _transpose(rows, idx)
            idx, mapping = _header_row(rows, kind)
            headings = rows[idx]
            body = [r for r in rows[idx + 1:] if any(r)]
            _, mapping = confirm(headings, body, mapping)

    # One name column only, the first.
    seen_single = set()
    for i in sorted(mapping):
        f = mapping[i]
        if f not in LIST_FIELDS and f not in ("subject_mark", "grade_mark"):
            if f in seen_single:
                del mapping[i]
            seen_single.add(f)

    if not ({"name", "first_name"} & set(mapping.values())):
        what = "subject" if kind == "subjects" else "teacher"
        raise ValueError(
            f"Couldn't find the column with each {what}'s name. Give that column a heading like "
            f"\"{what.capitalize()} name\" and upload again."
        )

    # Read every row, as typed.
    raw_rows = []
    for row in body:
        rec: dict = {}
        subjects: list[str] = []
        grades: list[str] = []
        first = last = ""
        for i, field in sorted(mapping.items()):
            value = row[i].strip() if i < len(row) else ""
            if not value:
                continue
            if field == "qualified_subjects":
                subjects += _split_items(value)
            elif field == "qualified_grades":
                grades += _split_items(value)
            elif field == "subject_mark":
                if _marked(value):
                    subjects.append(headings[i].strip())
            elif field == "grade_mark":
                if _marked(value):
                    grades.append(headings[i].strip())
            elif field == "first_name":
                first = value
            elif field == "last_name":
                last = value
            else:
                rec.setdefault(field, value)
        if not rec.get("name") and (first or last):
            rec["name"] = f"{first} {last}".strip()
        # Headings repeated down the sheet, totals, class labels, notes.
        subjects = [x for x in subjects if not is_label(x)]
        if rec.get("name") and not is_label(rec["name"]) and _key(rec["name"]) not in (
                _NOT_A_TEACHER if kind == "teachers" else set()):
            raw_rows.append((rec, subjects, grades))

    # What the subject and grade values mean.
    from app.services.bulk_import import _resolve_grades

    subject_items = sorted({s for _, subs, _ in raw_rows for s in subs}
                           | ({r["name"] for r, _, _ in raw_rows} if kind == "subjects" else set()))
    grade_items = sorted({g for _, _, gs in raw_rows for g in gs})
    by_rule_subjects = _rule_subjects(subject_items, school_subjects)
    by_rule_grades = {g: _resolve_grades(g, school_grades)[0] for g in grade_items}
    unsure_grades = [g for g in grade_items if not by_rule_grades[g]]
    answer = ai.values(subject_items, unsure_grades, school_subjects, school_grades) if (
        subject_items or unsure_grades) else None
    if answer:
        used_ai = True
    subject_meaning = {i: (answer["subjects"].get(i, by_rule_subjects[i]) if answer else by_rule_subjects[i])
                       for i in subject_items}
    grade_meaning = {g: by_rule_grades[g] or ((answer or {}).get("grades", {}).get(g) or []) for g in grade_items}

    # A reading only the AI made (the rules didn't reach it) is worth a look
    # before saving: "Comp Sci" -> Computer Science?
    def low(xs):
        return [x.lower() for x in xs]

    doubtful_subjects = {i for i in subject_items if answer and i in answer["subjects"]
                         and subject_meaning[i] and low(subject_meaning[i]) != low(by_rule_subjects[i])}
    doubtful_grades = {g for g in grade_items if not by_rule_grades[g] and grade_meaning[g]}

    matched, doubtful = [], []
    for item, means in subject_meaning.items():
        if means and [m.lower() for m in means] != [item.lower()]:
            matched.append(f"“{item}” as {', '.join(means)}")
            if item in doubtful_subjects:
                doubtful.append(f"“{item}” as {', '.join(means)}")
    for item, means in grade_meaning.items():
        if means and not (len(means) == 1 and means[0].lower() == item.lower()):
            matched.append(f"“{item}” as {', '.join(means)}")
            if item in doubtful_grades:
                doubtful.append(f"“{item}” as {', '.join(means)}")

    out, notes = [], []
    for rec, subjects, grades in raw_rows:
        row_notes = []
        for item in dict.fromkeys(subjects + ([rec["name"]] if kind == "subjects" else [])):
            if item in doubtful_subjects:
                row_notes.append(f"“{item}” → {', '.join(subject_meaning[item])}?")
        for item in dict.fromkeys(grades):
            if item in doubtful_grades:
                row_notes.append(f"“{item}” → {', '.join(grade_meaning[item])}?")
        notes.append(row_notes)
        if kind == "subjects":
            names = subject_meaning.get(rec["name"]) or [rec["name"]]
            rec = {**rec, "name": names[0]}
        else:
            canon = []
            for s in subjects:
                for m in subject_meaning.get(s, []):
                    if m.lower() not in {c.lower() for c in canon}:
                        canon.append(m)
            if canon:
                rec["qualified_subjects"] = ";".join(canon)
            if {"qualified_grades", "grade_mark"} & set(mapping.values()):
                resolved, unknown = [], []
                for g in grades:
                    m = grade_meaning.get(g) or []
                    (resolved.extend(m) if m else unknown.append(g))
                # Unknown ones are left as typed, so the import names them.
                rec["qualified_grades"] = ";".join(dict.fromkeys(resolved + unknown))
        out.append(rec)

    read_as = [f"“{headings[i]}” as {FIELDS[kind][f]}" for i, f in sorted(mapping.items())
               if headings[i] and f not in ("subject_mark", "grade_mark")]
    if class_tables:
        labels = [t["label"] for t in class_tables]
        read_as = [f"a table for each class ({len(labels)}: {', '.join(labels[:8])}{'…' if len(labels) > 8 else ''})",
                   "the subjects in each" + (", and who teaches them" if kind == "teachers" else "")]
    marks = [headings[i] for i, f in sorted(mapping.items()) if f in ("subject_mark", "grade_mark")]
    if marks:
        read_as.append("a mark under " + ", ".join(f"“{m}”" for m in marks) + " as teaching it")
    return out, {"sheet": title, "header_row": idx + 1, "layout": layout, "read_as": read_as,
                 "matched": matched, "doubtful": doubtful, "row_notes": notes, "used_ai": used_ai}


# ------------------------------------------------------- checks before saving

_SUFFIX = re.compile(r"^(?:\d+|i{1,3}|iv|v|vi{0,3}|ix|x|[a-c])$")


def _norm(name: str) -> str:
    return " ".join(name.lower().split())


def _variants(a: str, b: str) -> bool:
    """"Hindi I" and "Hindi II", "Science 1" and "Science 2": meant apart."""
    wa, wb = a.split(), b.split()
    return len(wa) == len(wb) > 1 and wa[:-1] == wb[:-1] and bool(_SUFFIX.match(wa[-1])) and bool(_SUFFIX.match(wb[-1]))


def look_alike_subjects(names: list[str], school_subjects: list[str]) -> list[tuple[str, str]]:
    """Pairs of subject names that look like one subject typed two ways
    ("Chemistry" / "Chemestry"), at least one of them new. The school's own
    subjects are never flagged against each other: it chose those."""
    from difflib import SequenceMatcher

    have = {_norm(s) for s in school_subjects}
    every = list(dict.fromkeys([*school_subjects, *names]))
    pairs = []
    for i, a in enumerate(every):
        for b in every[i + 1:]:
            na, nb = _norm(a), _norm(b)
            if na == nb or (na in have and nb in have) or min(len(na), len(nb)) < 4 or _variants(na, nb):
                continue
            if SequenceMatcher(None, na, nb).ratio() >= 0.85 or _key(a) == _key(b):
                pairs.append((a, b))
    return pairs


def look_alike_people(names: list[str]) -> list[tuple[str, str]]:
    """"Kavita K" and "Kavita Khana", "Shallu" and "Shalu": perhaps one person."""
    from difflib import SequenceMatcher

    names = list(dict.fromkeys(n for n in names if n))
    pairs = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            na, nb = _norm(a), _norm(b)
            if na == nb:
                continue
            wa, wb = na.split(), nb.split()
            initial = (len(wa) == len(wb) == 2 and wa[0] == wb[0]
                       and (wa[1].rstrip(".") == wb[1][:len(wa[1].rstrip("."))] or wb[1].rstrip(".") == wa[1][:len(wb[1].rstrip("."))])
                       and min(len(wa[1].rstrip(".")), len(wb[1].rstrip("."))) <= 2)
            if initial or (min(len(na), len(nb)) >= 4 and SequenceMatcher(None, na, nb).ratio() >= 0.88):
                pairs.append((a, b))
    return pairs


def check_rows(kind: str, rows: list[dict], school_subjects=(), school_grades=()) -> tuple[list[str], list[list[str]]]:
    """What a school should look at before saving: names that appear twice,
    a teacher with no subjects, a grade the school doesn't have, subjects
    that look like typos of each other. Returns the warnings and, for each
    row, its own notes."""
    from collections import Counter

    school_subjects, grades_ok = list(school_subjects), set(school_grades)
    notes: list[list[str]] = [[] for _ in rows]
    checks: list[str] = []
    what = "subject" if kind == "subjects" else "teacher"

    counts = Counter(_norm(r.get("name", "")) for r in rows)
    seen_dupe = []
    for n, r in enumerate(rows):
        name = r.get("name", "")
        if counts[_norm(name)] > 1:
            notes[n].append(f"“{name}” is in the sheet {counts[_norm(name)]} times")
            if _norm(name) not in [_norm(x) for x in seen_dupe]:
                seen_dupe.append(name)
    if seen_dupe:
        checks.append(f"{len(seen_dupe)} {what} name{'s appear' if len(seen_dupe) > 1 else ' appears'} more than once "
                      f"({', '.join(seen_dupe[:6])}{'…' if len(seen_dupe) > 6 else ''}). They'd be saved as one "
                      f"{what} each, with everything from every row.")

    if kind == "teachers":
        none = [r["name"] for r in rows if not r.get("qualified_subjects", "").strip()]
        for n, r in enumerate(rows):
            if not r.get("qualified_subjects", "").strip():
                notes[n].append("No subjects")
        if none:
            checks.append(f"{len(none)} teacher{'s have' if len(none) > 1 else ' has'} no subjects "
                          f"({', '.join(none[:6])}{'…' if len(none) > 6 else ''}). They can't be timetabled "
                          f"until they're given some.")

        unknown: dict[str, list[str]] = {}
        if grades_ok:
            for n, r in enumerate(rows):
                for g in (x.strip() for x in r.get("qualified_grades", "").split(";")):
                    if g and g not in grades_ok:
                        unknown.setdefault(g, []).append(r["name"])
                        notes[n].append(f"“{g}” isn't one of the school's grades")
        for g, who in unknown.items():
            checks.append(f"“{g}” isn't a grade at this school ({', '.join(who[:4])}{'…' if len(who) > 4 else ''}). "
                          f"Its grades are {', '.join(sorted(grades_ok))}.")
        names = [s.strip() for r in rows for s in r.get("qualified_subjects", "").split(";") if s.strip()]
    else:
        names = [r["name"] for r in rows if r.get("name")]

    if kind == "teachers":
        for a, b in look_alike_people([r["name"] for r in rows]):
            checks.append(f"“{a}” and “{b}” may be the same teacher. If so, use one spelling.")
            for n, r in enumerate(rows):
                if r["name"] in (a, b):
                    notes[n].append(f"Same person as “{b if r['name'] == a else a}”?")

    for a, b in look_alike_subjects(list(dict.fromkeys(names)), school_subjects):
        checks.append(f"“{a}” and “{b}” look like the same subject typed two ways.")
        for n, r in enumerate(rows):
            mine = ({_norm(s) for s in r.get("qualified_subjects", "").split(";")} if kind == "teachers"
                    else {_norm(r.get("name", ""))})
            for x in (a, b):
                if _norm(x) in mine and _norm(x) not in {_norm(s) for s in school_subjects}:
                    notes[n].append(f"“{x}” or “{b if x == a else a}”?")
    return checks, notes

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


# ------------------------------------------------------- preview, then save

def school_context(db: Session, school_id: int) -> tuple[list[str], list[str]]:
    from app.models.school import ClassGroup

    subjects = [x.name for x in db.query(Subject).filter(Subject.school_id == school_id)]
    grades = sorted({g for (g,) in db.query(ClassGroup.grade).filter(ClassGroup.school_id == school_id) if g})
    return subjects, grades


def build_preview(db: Session, school_id: int, kind: str, filename: str, content: bytes, ai=None) -> dict:
    """Everything the school sees before anything is saved: how the sheet
    was read, every row as it will be saved, what's doubtful and what to
    check. Nothing is written."""
    from app.models.school import Teacher

    school_subjects, school_grades = school_context(db, school_id)
    rows, info = smart_rows(kind, filename, content, school_subjects=school_subjects,
                            school_grades=school_grades, ai=ai)
    checks, check_notes = check_rows(kind, rows, school_subjects, school_grades)
    model = Subject if kind == "subjects" else Teacher
    have = {_norm(x.name) for x in db.query(model).filter(model.school_id == school_id)}
    known = {_norm(x) for x in school_subjects}
    if kind == "teachers":
        named = list(dict.fromkeys(s.strip() for r in rows for s in r.get("qualified_subjects", "").split(";") if s.strip()))
        new_subjects = [x for x in named if _norm(x) not in known]
    else:
        named = list(dict.fromkeys(r["name"] for r in rows))
        new_subjects = []
    return {
        "kind": kind,
        "total": len(rows),
        "subject_count": len(named),
        "will_update": len({_norm(r["name"]) for r in rows} & have),
        "rows": rows,
        "row_notes": [a + b for a, b in zip(info["row_notes"], check_notes)],
        "sheet": info["sheet"],
        "read_as": info["read_as"],
        "matched": info["matched"],
        "doubtful": info["doubtful"],
        "checks": checks,
        "new_subjects": new_subjects,
    }

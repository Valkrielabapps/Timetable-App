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
            "the school keeps apart apart (English Language and English Literature are two). Every value is a "
            "period on the timetable: never fold one into another subject. A lab, a practical or a skill is its "
            "own subject - \"Physics Lab\" stays Physics Lab, \"Mental Maths\" stays Mental Maths, \"Science "
            "Prac\" is Science Practical, \"Reading\", \"Cursive\", \"Assembly\" and \"Library\" stay "
            "as they are. Only spellings and short forms of the same name are the same subject.\n"
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
    "pe": "pe", "pt": "pe", "physicaleducation": "pe", "games": "pe", "sports": "pe", "ped": "pe",
    "phyedu": "pe", "pted": "pe", "ptgames": "pe", "physicaltraining": "pe",
    "gk": "gk", "generalknowledge": "gk",
    "englit": "englit", "englishlit": "englit", "englishliterature": "englit", "lit": "englit",
    "englang": "englang", "englishlang": "englang", "englishlanguage": "englang",
    "enggram": "enggram", "englishgrammar": "enggram", "grammar": "enggram",
    "lib": "library", "library": "library",
    "hist": "history", "his": "history", "history": "history",
    "geo": "geography", "geog": "geography", "geography": "geography",
    "civ": "civics", "civics": "civics",
    "histciv": "histciv", "historycivics": "histciv", "historyandcivics": "histciv",
    "eco": "economics", "econ": "economics", "economics": "economics",
    "acc": "accounts", "accts": "accounts", "accounts": "accounts", "accountancy": "accounts",
    "bst": "business", "bstudies": "business", "businessstudies": "business",
    # "Com" alone is Computer in a primary table and Commerce in Class 11: not guessed.
    "comm": "commerce", "comstudies": "commerce", "commercestudies": "commerce", "commerce": "commerce",
    "sci": "science", "science": "science",
    "sciprac": "sciprac", "scienceprac": "sciprac", "sciencepractical": "sciprac", "sciencepracticals": "sciprac",
    "lifeskill": "lifeskills", "lifeskills": "lifeskills",
    "writingskill": "writing", "writingskills": "writing",
    "art": "art", "arts": "art", "artandcraft": "art", "artcraft": "art",
    "eng": "english", "engl": "english", "english": "english", "bioscience": "biology", "biosci": "biology",
    "social": "social", "supw": "supw",
    "hin": "hindi", "hindi": "hindi", "tam": "tamil", "tamil": "tamil", "kan": "kannada", "kannada": "kannada",
    "tel": "telugu", "telugu": "telugu", "mal": "malayalam", "malayalam": "malayalam", "skt": "sanskrit",
    "sans": "sanskrit", "sanskrit": "sanskrit", "fre": "french", "french": "french",
    "mat": "math", "mths": "math", "soc": "social", "socsci": "social", "game": "pe",
    "robo": "robotics", "robotics": "robotics", "ai": "ai", "artificialintelligence": "ai",
    "acco": "accounts", "bs": "business", "ip": "ip", "informaticspractices": "ip",
    "2ln": "lang2", "secondlanguage": "lang2", "2ndlanguage": "lang2", "3ln": "lang3", "thirdlanguage": "lang3",
    "3rdlanguage": "lang3", "read": "reading", "reading": "reading", "lis": "listening", "listening": "listening", "speak": "speaking", "speaking": "speaking",
}

# A clean name for a known subject the school doesn't have yet, so "PT",
# "Games" and "P.Ed" all arrive as one "Physical Education".
_CONCEPT_NAMES = {
    "math": "Maths", "biology": "Biology", "physics": "Physics", "chemistry": "Chemistry",
    "computer": "Computer Science", "social": "Social Studies", "evs": "Environmental Studies",
    "pe": "Physical Education", "gk": "General Knowledge", "englit": "English Literature",
    "englang": "English Language", "enggram": "English Grammar", "library": "Library", "history": "History",
    "geography": "Geography", "civics": "Civics", "histciv": "History & Civics", "economics": "Economics",
    "accounts": "Accountancy", "business": "Business Studies", "commerce": "Commerce", "science": "Science",
    "sciprac": "Science Practical", "lifeskills": "Life Skills", "writing": "Writing Skills", "art": "Art",
    "english": "English", "hindi": "Hindi", "tamil": "Tamil", "kannada": "Kannada", "telugu": "Telugu",
    "malayalam": "Malayalam", "sanskrit": "Sanskrit", "french": "French", "robotics": "Robotics",
    "ai": "Artificial Intelligence", "ip": "Informatics Practices", "reading": "Reading", "listening": "Listening",
    "speaking": "Speaking", "lang2": "2nd Language", "lang3": "3rd Language",
}


_FULL_KEY = {}
for _k, _c in _SUBJECT_ALIASES.items():
    if len(_k) > len(_FULL_KEY.get(_c, "")):
        _FULL_KEY[_c] = _k


def _concept(name: str) -> str:
    k = _key(name)
    return _SUBJECT_ALIASES.get(k, k)


def _best_spelling(spellings: list[str]) -> str:
    """"Maths" over "Math", "Art" over "ART", "Computer" over "computer"."""
    return max(spellings, key=lambda x: (not x.isupper() or len(x) <= 3, not x.islower(), len(x), x))


def _rule_subjects(items: list[str], school_subjects: list[str]) -> dict[str, list[str]]:
    by_concept = {_concept(s): s for s in school_subjects}
    out, new_by_concept = {}, {}
    for item in items:
        c = _concept(item)
        if c and c not in by_concept:
            new_by_concept.setdefault(c, []).append(item.strip())
    for item in items:
        c = _concept(item)
        if not c:
            out[item] = []
        elif c in by_concept:
            out[item] = [by_concept[c]]
        else:
            # Two spellings of one new subject become one.
            # The sheet's own full name ("Mathematics") if it has one, else a
            # clean one for the short forms ("PT", "Games" -> Physical Education).
            full = [x for x in new_by_concept[c] if _key(x) == _FULL_KEY.get(c)]
            best = _best_spelling(full) if full else (_CONCEPT_NAMES.get(c) or _best_spelling(new_by_concept[c]))
            # "PHYSICS" typed in capitals arrives as "Physics".
            if best.isupper() and len(best) > 3 and _CONCEPT_NAMES.get(c):
                best = _CONCEPT_NAMES[c]
            out[item] = [best]
    return out


# Words that make a period its own subject: "Physics Lab" is not Physics.
_OWN_PERIOD = ("lab", "prac", "practical", "mental", "reading", "cursive", "writing", "handwriting", "spelling",
               "dictation", "phonics", "activity", "club", "remedial", "project", "assembly", "library", "skill",
               "grammar", "gram", "oral", "speaking", "lit", "lang")
_NOTHING = {"", "-", "--", "na", "nil", "none", "nan", "x"}


def _concepts(text: str) -> set[str]:
    return {_concept(w) for w in re.split(r"[^A-Za-z0-9]+", text) if _concept(w)}


def _checked(item: str, means: list[str], by_rule: list[str]) -> list[str]:
    """The AI's reading of a subject value, unless it folded the value into
    another subject ("Physics Lab" -> Physics, "Mental Maths" -> Maths) or
    dropped a real one. Then the rules' reading stands."""
    if not means:
        return [] if _key(item) in _NOTHING else by_rule
    mine = _concepts(item)
    theirs = set().union(*(_concepts(m) for m in means))
    # Part of the name dropped: the AI's answer is a smaller piece of it.
    if theirs and theirs < mine:
        return by_rule
    words = [w for w in re.split(r"[^a-z]+", item.lower()) if w]
    kept = " ".join(means).lower()
    for w in words:
        if w in _OWN_PERIOD or any(w.startswith(o) and len(o) >= 4 for o in _OWN_PERIOD):
            # "Prac" -> "Practical", "Gram" -> "Grammar" are fine; losing it is not.
            if w not in kept and not any(o in kept for o in _OWN_PERIOD if o.startswith(w) or w.startswith(o)):
                return by_rule
    return means


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
# What a sheet says about itself, above or below the list.
_SHEET_DETAILS = {
    "schoolyear", "academicyear", "year", "session", "academicsession", "term", "schoolterm", "semester",
    "school", "schoolname", "nameofschool", "branch", "campus", "date", "preparedby", "checkedby", "approvedby",
    "principal", "headmistress", "headmaster", "coordinator", "signature", "remarks", "remark", "note", "notes",
    "timetable", "timetableincharge", "effectivefrom", "wef", "updatedon", "version", "page",
}
_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
             "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun", "day"}
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
    # Form fields at the top of a sheet: "School Year:", "Term: 1".
    if t.endswith(":") or re.match(r"^[^:]{2,30}:\s*\S", t) and _key(t.split(":")[0]) in _SHEET_DETAILS:
        return True
    if k in _SHEET_DETAILS:
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
        # A finished timetable - Monday | Tuesday … with Teacher | Subject
        # under each day - repeats the heading across the row. Not a list.
        # Side-by-side lists each have their own Periods column; a timetable
        # has one Period column for the whole row.
        heads = sum(1 for v in row if _key(v) in _SUBJECT_HEADS)
        if heads >= 3 and sum(1 for v in row if _key(v) in _PERIOD_HEADS) < heads / 2:
            continue
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
        if _key(label) in _WEEKDAYS:
            continue
        tables.append({"label": label or f"table {n + 1}", "items": items})
    return [t for t in tables if t["items"]]


def _class_score(tables: list[dict]) -> int:
    """How much a sheet looks like a list per class: rows under tables whose
    label names a class count; a sheet of unlabelled tables counts less."""
    return sum(len(t["items"]) * (2 if _CLASS_LABEL.match(t["label"]) or _grade_of(t["label"]) else 1)
               for t in tables)


# ------------------------------------------- allotment grids and side blocks
#
# Two more ways schools write the same plan, with numbers instead of a
# Periods column:
#
#   a grid      CLASS | ENG | TAMIL | MAT | ... | TOTAL     (classes down,
#               VI    | 3+3 | 4     | 6   | ... | 40         subjects across)
#               - or the other way round, subjects down and classes across;
#   side blocks GRADE XI AND XII                            (a column of
#               NEET     |   | JEE       |   | CUET  |       subjects and a
#               ENGLISH  | 4 | ENGLISH   | 4 | ENG   | 7     column of numbers,
#               PHYSICS  | 9 | PHYSICS   | 9 | ECO   | 8     one pair per class)
#
# Both come out as the same class tables as above (label, then subject,
# periods, teacher - no teacher here), so everything downstream reads them.

_COUNT = re.compile(r"^\s*\d{1,2}(?:\s*\+\s*\d{1,2})*\s*$")
_EMPTY = re.compile(r"^\s*(?:-+|–|—|nil|na|n/a|x)?\s*$", re.I)
_ROMAN_N = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
            "xi": 11, "xii": 12}
_EARLY_N = {"kg", "lkg", "ukg", "nursery", "prekg", "pp1", "pp2", "playgroup", "prep"}


def count_of(cell: str) -> int:
    """"6" -> 6, "3+3" -> 6, "-" -> 0."""
    if not _COUNT.match(cell or ""):
        return 0
    return sum(int(x) for x in re.findall(r"\d+", cell))


def _countish(cell: str) -> bool:
    return bool(_COUNT.match(cell)) or bool(_EMPTY.match(cell))


def _class_token(text: str) -> tuple[str, str] | None:
    """The class a label names, and what else it says: "N/J VIII" -> ("VIII",
    "N/J"); "Class 6" -> ("6", ""); "CUET X" -> ("X", "CUET"); "Maths" -> None."""
    words = re.split(r"\s+", re.sub(r"(?i)\b(class|grade|std\.?|standard)\b", " ", text).strip())
    for i, w in enumerate(words):
        k = w.strip(".-:()").lower()
        if k in _ROMAN_N or (k.isdigit() and 1 <= int(k) <= 12) or k in _EARLY_N:
            rest = " ".join(words[:i] + words[i + 1:]).strip(" -:()")
            return w.strip(".-:()").upper() if not k.isdigit() else k, rest
    return None


def _class_label(text: str) -> str:
    """A grid's row label as a class table label the class plan reads:
    "N/J VIII" -> "Class VIII (N/J)"."""
    tok = _class_token(text)
    if not tok:
        return text.strip()
    grade, rest = tok
    return f"Class {grade} ({rest})" if rest else f"Class {grade}"


def _grid(rows: list[list[str]]) -> list[dict]:
    """A heading row of subjects (or classes) over rows of counts."""
    best: list[dict] = []
    for h, head in enumerate(rows):
        cols = [c for c in range(1, len(head)) if head[c].strip() and not _COUNT.match(head[c])]
        if len(cols) < 3:
            continue
        body = []
        for r in range(h + 1, len(rows)):
            row = rows[r]
            first = row[0].strip() if row else ""
            cells = [row[c].strip() if c < len(row) else "" for c in cols]
            filled = [v for v in cells if v]
            if not first and not filled:
                continue
            numbers = [v for v in cells if _COUNT.match(v)]
            if first and len(numbers) >= 2 and all(_countish(v) for v in cells):
                body.append((first, cells))
            else:
                break
        if len(body) < 2:
            continue
        heads = [head[c].strip() for c in cols]
        # Classes across the top and subjects down the side: the other way round.
        across = sum(1 for x in heads if _class_token(x)) > len(heads) / 2 and \
            sum(1 for f, _ in body if _class_token(f)) < len(body) / 2
        tables = []
        if across:
            for j, cls in enumerate(heads):
                if is_label(cls) and not _class_token(cls):
                    continue
                items = [(subj, cells[j], "") for subj, cells in body
                         if count_of(cells[j]) and not is_label(subj)]
                if items:
                    tables.append({"label": _class_label(cls), "items": items})
        else:
            for cls, cells in body:
                if _key(cls).startswith("total"):
                    continue
                items = [(heads[j], v, "") for j, v in enumerate(cells)
                         if count_of(v) and not is_label(heads[j])]
                if items:
                    tables.append({"label": _class_label(cls), "items": items})
        if sum(len(t["items"]) for t in tables) > sum(len(t["items"]) for t in best):
            best = tables
    return best


def _side_blocks(rows: list[list[str]]) -> list[dict]:
    """Pairs of columns - a subject, then its number - one pair per class or
    stream, with the stream's name above it and the classes in a title."""
    width = max((len(r) for r in rows), default=0)

    def cell(r, c):
        return rows[r][c].strip() if r < len(rows) and c < len(rows[r]) else ""

    pairs = []
    for c in range(width - 1):
        # A class label with a number beside it ("VI | 6") is a grid's row, not a subject.
        hits = [r for r in range(len(rows)) if cell(r, c) and not _COUNT.match(cell(r, c))
                and _COUNT.match(cell(r, c + 1)) and not is_label(cell(r, c))
                and not (_class_token(cell(r, c)) and len(cell(r, c).split()) <= 2)]
        if len(hits) >= 3:
            pairs.append((c, hits))
    if not pairs:
        return []
    # Classes the blocks are for, from a title above them: "GRADE XI AND XII".
    top = min(h[0] for _, h in pairs)
    title_classes: list[str] = []
    for r in range(top):
        for w in re.split(r"[\s,&/–—-]+", " ".join(rows[r])):
            k = w.strip(".:()").lower()
            if (k in _ROMAN_N or (k.isdigit() and 1 <= int(k) <= 12)) and w.upper() not in title_classes:
                title_classes.append(w.strip(".:()").upper())
    tables = []
    first_col = pairs[0][0]
    for c, hits in pairs:
        stream = ""
        for r in range(hits[0] - 1, -1, -1):
            if cell(r, c) and not cell(r, c + 1):
                stream = cell(r, c)
                break
        items = []
        for r in range(hits[0], max(hits) + 2):
            name, n = cell(r, c), cell(r, c + 1)
            if not count_of(n):
                continue
            # A row only the first block names ("AI | 2 |  | 2"): the same subject.
            if not name and c != first_col:
                name = cell(r, first_col)
            if name and not is_label(name):
                items.append((name, n, ""))
        if not items:
            continue
        tok = _class_token(stream) if stream else None
        if tok:
            tables.append({"label": _class_label(stream), "items": items})
        elif title_classes:
            for g in title_classes:
                tables.append({"label": f"Class {g} ({stream})" if stream else f"Class {g}", "items": items})
        else:
            tables.append({"label": stream or f"table {len(tables) + 1}", "items": items})
    return tables


# ----------------------------------------------- a list under each teacher
#
# The other common staff sheet: a department heading, each teacher's name
# across the row, and under each name what they take, one line each:
#
#   HIGHSCHOOL PHY,CHEM
#   MRS.HARINIKA-PHY | MRS.VAHINI-CHEM | MR.MUKESH
#   VI B- 3          | X B- 4          | VIII A-3 PHY
#   VII C- 5 C.T     | XI A,B - 9      | IX-2 3LN
#
# "VIII A-3 PHY" is Class 8 section A, 3 periods of Physics; with no subject
# it's the teacher's own (the "-PHY" after the name) or the heading's.

_TITLE = re.compile(r"^\s*(?:mrs|mr|ms|miss|dr|sr|fr|sis|bro|smt|shri|sri)\b\.?\s*", re.I)
_LEVEL_WORDS = re.compile(r"\b(?:high\s*school|highschool|higher\s*secondary|secondary|primary|middle\s*school|"
                          r"middle|senior|junior|pre\s*primary|dept\.?|department|teachers?|staff)\b", re.I)
_ENTRY = re.compile(
    r"^(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I|1[0-2]|[1-9])(?![0-9])"   # the class
    r"\s*[-–:]?\s*((?:[A-H]\s*[,&/]\s*)*[A-H](?![A-Z])|[A-H]{2,6}(?![A-Z]))?"  # sections
    r"\s*[-–:]?\s*(?:(\d{1,2}(?![0-9])|I(?![A-Z])))?"                     # periods ("I" for 1)
    r"\s*[-–:]?\s*(.*)$")
_LANG = re.compile(r"\b([23])\s*(?:LN|LANG|LANGUAGE|L)\b")


def _teacher_cell(text: str) -> list[tuple[str, str]] | None:
    """"MRS.HARINIKA-PHY" -> [("Harinika", "PHY")]; "MR.A/MR.B" -> both;
    not a name (no Mr / Mrs / Ms) -> None."""
    parts = [p.strip() for p in re.split(r"\s*/\s*(?=(?:mrs|mr|ms|miss|dr)\b)", text.strip(), flags=re.I) if p.strip()]
    if not parts or not all(_TITLE.match(p) for p in parts):
        return None
    out = []
    for p in parts:
        name = _TITLE.sub("", p).strip(" .")
        subj = ""
        m = re.match(r"^(.*?)\s*[-–]\s*([A-Za-z.&, ]{2,30})$", name)
        if m:
            name, subj = m.group(1), m.group(2).strip()
        name = re.sub(r"\s+", " ", name).strip(" .-")
        if name:
            out.append((name.title() if name.isupper() else name, subj))
    return out or None


def _entry(text: str) -> tuple[str, list[str], int, str] | None:
    """"VIII A-3 PHY" -> ("VIII", ["A"], 3, "PHY"); "I A,B,C - 3" -> ("I",
    ["A","B","C"], 3, ""); "IX-2 3LN" -> ("IX", [], 2, "3rd language")."""
    t = re.sub(r"\s+", " ", text.strip().upper())
    if not t or len(t) > 32:
        return None
    lang = ""
    m = _LANG.search(t)
    if m:
        lang = "2nd language" if m.group(1) == "2" else "3rd language"
        t = (t[:m.start()] + " " + t[m.end():]).strip()
    m = _ENTRY.match(t)
    if not m:
        return None
    grade, secs, per, subj = m.group(1), m.group(2) or "", m.group(3), m.group(4).strip(" -–.:")
    if per is None and not subj and not secs and not lang:
        return None
    if subj and (len(subj.split()) > 3 or re.search(r"\d{3,}", subj)):
        return None
    sections = re.findall(r"[A-H]", secs)
    periods = 1 if per == "I" else int(per) if per else 0
    return grade, sections, periods, (lang + (" " + subj if subj else "")).strip() if lang else subj


def _heading_subjects(text: str) -> list[str]:
    """"HIGHSCHOOL PHY,CHEM" -> ["PHY", "CHEM"]; "PRIMARY ,HIGHSCHOOL  HINDI" -> ["HINDI"]."""
    t = _LEVEL_WORDS.sub(" ", text)
    return [p.strip(" -–.:") for p in re.split(r"[,/&]|\band\b", t) if p.strip(" -–.:")]


def _teacher_lists(rows: list[list[str]]) -> list[dict]:
    heading: list[str] = []
    owner: dict[int, list[tuple[str, str]]] = {}
    found: dict[tuple[str, str], dict] = {}
    entries = teachers = 0
    for row in rows:
        cells = [(c, v.strip()) for c, v in enumerate(row) if v and v.strip()]
        if not cells:
            continue
        kinds = []
        for c, v in cells:
            ppl = _teacher_cell(v)
            kinds.append(("teacher", c, ppl) if ppl else ("entry", c, _entry(v)) if _entry(v) else ("text", c, v))
        # A heading: a row of text with no name and no class in it.
        if all(k == "text" for k, _, _ in kinds):
            if len(cells) <= 2 and not is_label(cells[0][1]) or _LEVEL_WORDS.search(cells[0][1]):
                heading, owner = _heading_subjects(cells[0][1]), {}
            continue
        for kind, c, val in kinds:
            if kind == "teacher":
                owner[c] = val
                teachers += len(val)
            elif kind == "entry" and c in owner:
                grade, sections, periods, subj = val
                own = [s for _, s in owner[c] if s]
                if subj in ("2nd language", "3rd language") or not subj:
                    base = own[0] if own else "/".join(heading)
                    base = base.title() if base.isupper() and len(base) > 3 and subj else base
                    subj = f"{base} ({subj})" if subj else base
                if not subj:
                    continue
                who = "/".join(n for n, _ in owner[c])
                entries += 1
                # "1" and "I" are one class: written the way most of the sheet writes it.
                if grade.isdigit():
                    grade = next(r for r, n in _ROMAN_N.items() if n == int(grade)).upper()
                for sec in sections or [""]:
                    label = f"Class {grade} {sec}".strip()
                    rec = found.setdefault((label, _key(subj)), {"label": label, "subj": subj, "per": 0, "who": {}})
                    # Two teachers each with "XI A- 5" Maths share it: 10 in all.
                    # The same teacher's line twice is one.
                    rec["who"][who] = max(rec["who"].get(who, 0), periods)
                    rec["per"] = sum(rec["who"].values())
    if entries < 5 or teachers < 2:
        return []
    tables: dict[str, list] = {}
    for rec in found.values():
        tables.setdefault(rec["label"], []).append((rec["subj"], str(rec["per"]) if rec["per"] else "",
                                                    "/".join(rec["who"])))
    return [{"label": label, "items": items, "by_teacher": True} for label, items in tables.items()]


# ------------------------------------------------- last year's timetable
#
# Each section's week, the way schools print it:
#
#   Tr's Name :  MRS.ROSEE-   XI A               (the class teacher, the class)
#            1             2        3 ...         (period numbers)
#   Mon   BIO-ROS,BHAG   BHAGYA   PHY-KARTHIGAI  (subject-teacher in each cell)
#   Tue   ...
#
# Counting the cells gives each section's periods of each subject, and who
# taught it - the whole plan, ready to be used again. Teachers are written
# short and differently from cell to cell ("KRITHI", "KRITHIKA"; "KAL,JO";
# "V'G" for Vijaya Geetha), so every spelling is matched to one person.

_DAY_PREFIX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_SECTION_OF = re.compile(r"\b(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I|1[0-2]|[1-9])\s*[-–]?\s*([A-H])\b")
_TITLED = re.compile(r"\b(?:mrs|mr|mra|ms|miss|dr|sr)\b\.?\s*([A-Za-z][A-Za-z .']{1,40})", re.I)


def _day_of(cell: str) -> int | None:
    k = re.sub(r"[^a-z]", "", cell.lower())[:3]
    return _DAY_PREFIX.get(k) if len(re.sub(r"[^a-z]", "", cell.lower())) <= 9 else None


def _timetable_blocks(rows: list[list[str]]) -> list[dict]:
    """Each section's grid: {"section": ("XI", "A"), "class_teacher", "cells": {(day, n): text}}."""
    blocks, cur, numbers = [], None, {}
    for row in rows:
        cells = [v.strip() if isinstance(v, str) else str(v or "").strip() for v in row]
        if not any(cells):
            continue
        day = _day_of(cells[0]) if cells[0] else None
        nums = {c: int(float(v)) for c, v in enumerate(cells) if c and re.fullmatch(r"\d{1,2}(\.0)?", v)}
        if day is not None and cur is not None:
            for c, v in enumerate(cells[1:], start=1):
                n = numbers.get(c, c)
                if v:
                    cur["cells"][(day, n)] = v
                cur["days"].add(day)
            continue
        if len(nums) >= 4 and len(nums) >= len([v for v in cells if v]) - 1:
            numbers = nums
            continue
        joined = " ".join(v for v in cells if v)
        found = list(_SECTION_OF.finditer(joined))
        if found and re.search(r"name|class|tr'?s", joined, re.I) or (found and len(joined) < 40):
            m = found[-1]
            teacher = ""
            titled = [t for t in (_TITLED.search(v) for v in cells if v) if t]
            if titled:
                teacher = titled[0].group(1)
            else:
                after = re.split(r"name\s*[-:]*", joined, flags=re.I)
                if len(after) > 1:
                    teacher = _SECTION_OF.sub(" ", after[1])
            teacher = re.sub(r"[-–:]+$", "", _SECTION_OF.sub(" ", teacher)).strip(" .-:")
            teacher = re.sub(r"\s+", " ", teacher)
            cur = {"section": (m.group(1), m.group(2)), "class_teacher": teacher, "cells": {}, "days": set()}
            blocks.append(cur)
            numbers = {}
    return [b for b in blocks if len(b["cells"]) >= 10]


def _split_cell(text: str) -> tuple[str, list[str]]:
    """"BIO-ROS,BHAG" -> ("BIO", ["ROS", "BHAG"]); "BHAGYA" -> ("", ["BHAGYA"])."""
    t = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    # "ENG-2-SOFIA": English 2, taught by Sofia.
    m = re.match(r"^([^-–]+?)\s*[-–]\s*(\d)\s*[-–]\s*(.+)$", t) or re.match(r"^([^-–]+?)\s*[-–]\s*(.+)$", t)
    if not m:
        return "", [t] if t else []
    subj, rest = (f"{m.group(1).strip()} {m.group(2)}", m.group(3)) if m.lastindex == 3 else (m.group(1), m.group(2))
    if re.search(r"[-–]", rest):
        return "?", []  # several subjects run together in one cell: not readable
    who = [w.strip(" .") for w in re.split(r"[,/&]", rest) if w.strip(" .")]
    return subj.strip(" ."), who


def _lk(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _close(a: str, b: str) -> bool:
    import difflib
    return a[:1] == b[:1] and min(len(a), len(b)) >= 4 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


def _ck(code: str) -> str:
    return re.sub(r"[^a-z0-9]", "", code.lower())


def _timetables(rows: list[list[str]]) -> list[dict]:
    return _timetables_from(_timetable_blocks(rows))


def _staff_name(name: str) -> str:
    n = re.sub(r"\s+", " ", _TITLE.sub("", name.strip())).strip(" .,-")
    return " ".join(w[:1].upper() + w[1:].lower() if w.isupper() or w.islower() else w for w in n.split())


def _timetables_from(blocks: list[dict], staff: list[dict] | None = None) -> list[dict]:
    """staff: the school's own list [{"name", "subjects"}], when there is
    one - every short spelling is then matched to a real name on it, using
    the subject to tell two alike apart (SUPW-SUBHA is Subhashini who takes
    SUPW, ACCO-SUBHA is Subha Sri who takes Accountancy)."""
    if len(blocks) < 2:
        return []
    from collections import Counter
    # Who appears as a teacher anywhere ("BIO-BHAGYA"), so a name alone in a
    # cell ("BHAGYA") can be told from a subject alone ("ELECTIVES").
    known = set()
    for b in blocks:
        for text in b["cells"].values():
            subj, who = _split_cell(text)
            if subj:
                known.update(_lk(w) for w in who)

    def is_person(word: str) -> bool:
        k = _lk(word)
        return bool(k) and any(n == k or n.startswith(k) or k.startswith(n) for n in known if len(n) >= 3)

    # Every cell as (section, subject code, teacher spellings).
    raw = []
    for b in blocks:
        last = {}
        for (day, n), text in sorted(b["cells"].items()):
            subj, who = _split_cell(text)
            if subj == "?":
                continue
            if not subj:
                if who and is_person(who[0]) and last.get(day):
                    subj = last[day]  # a name alone continues the period before: a double lab
                else:
                    subj, who = (who[0] if who else ""), []
            last[day] = subj
            if subj:
                raw.append((b, subj, who))
    # Subject codes: rare typos join a common spelling ("BIP" -> "BIO",
    # "EN 2" -> "ENG 2").
    codes = Counter(_ck(s) for _, s, _ in raw)
    spelt = {}
    for _, s, _ in raw:
        spelt.setdefault(_ck(s), s.upper())

    def letters(c):
        return re.sub(r"\d", "", c)

    def digits(c):
        return re.sub(r"\D", "", c)

    code_of = {}
    for c in codes:
        better = [d for d in codes if d != c and digits(c) == digits(d) and (
            (codes[d] >= 3 * codes[c] and (_close(c, d) or (
                len(c) >= 3 and len(d) >= 3 and abs(len(c) - len(d)) == 1 and (c in d or d in c) and c[:1] == d[:1])))
            or (digits(c) and len(letters(d)) > len(letters(c)) and letters(d).startswith(letters(c))
                and codes[d] >= codes[c])
            # One letter slipped: "GANE" for "GAME", "BIP" for "BIO".
            or (codes[d] >= 3 * codes[c] and len(c) == len(d) >= 3 and c[0] == d[0]
                and sum(x != y for x, y in zip(c, d)) == 1))]
        code_of[c] = max(better, key=lambda d: codes[d]) if better else c
    # Teachers: the class teachers' full names, and every spelling in the cells.
    full = {}
    for b in blocks:
        if b["class_teacher"]:
            full[_lk(b["class_teacher"])] = b["class_teacher"]
    count = Counter(_lk(w) for _, _, ws in raw for w in ws if _lk(w))
    by_subject: dict[str, set] = {}
    by_place: dict[tuple, set] = {}
    for b, s, ws in raw:
        for w in ws:
            by_subject.setdefault(code_of[_ck(s)], set()).add(_lk(w))
            by_place.setdefault((b["section"], code_of[_ck(s)]), set()).add(_lk(w))
    names = set(count) | set(full)
    subject_codes = set(codes)

    def initials(k_full: str) -> str:
        return "".join(p[0] for p in full[k_full].lower().split() if p)

    def resolve_once(k: str, sec, code, apostrophe: str = "") -> str:
        if apostrophe:
            # "V'G" is Vijaya Geetha; "R'SUDHA" is R. Sudha (Ragasudha).
            a, b2 = apostrophe
            by_initials = [f for f in full if len(full[f].split()) > 1 and initials(f) == a + b2]
            if len(by_initials) == 1:
                return by_initials[0]
            cand = [n for n in names if n.startswith(a) and n != k and len(b2) >= 2 and b2 in n[len(a):]]
            if len(set(cand)) == 1:
                return cand[0]
        longer = [n for n in names if n != k and n.startswith(k)]
        if not longer or len(k) < 2:
            return k
        for pool in (by_place.get((sec, code), set()), by_subject.get(code, set())):
            cand = [n for n in longer if n in pool]
            if cand:
                return max(cand, key=lambda n: (n in full, count.get(n, 0), len(n)))
        in_full = [n for n in longer if n in full]
        if len(in_full) == 1:
            return in_full[0]
        return longer[0] if len(longer) == 1 else k

    def resolve(w: str, sec, code) -> str:
        k = _lk(w)
        if not k:
            return ""
        parts = re.split(r"['’`]", w.lower())
        apostrophe = (_lk(parts[0]), _lk("".join(parts[1:]))) if len(parts) > 1 and _lk(parts[0]) else ""
        for _ in range(3):
            nk = resolve_once(k, sec, code, apostrophe)
            apostrophe = ""
            if nk == k:
                break
            k = nk
        return k

    resolved = []
    for b, s, ws in raw:
        code = code_of[_ck(s)]
        pairs = [(w, resolve(w, b["section"], code)) for w in ws]
        pairs = [(w, x) for w, x in pairs if x and x not in subject_codes]
        resolved.append((b, code, [x for _, x in pairs], [w for w, _ in pairs]))
    # Spelling slips between whole names: "ISSAC" and "ISAAC", "SWATHI" and "SWATHY".
    tally = Counter(x for _, _, ws, _ in resolved for x in ws)
    same = {}
    for a in tally:
        for c in tally:
            if a != c and _close(a, c) and (c in full or tally[c] > tally[a] or (tally[c] == tally[a] and c > a)) \
                    and a not in full:
                same[a] = c
                break
    # One readable spelling for each person: the class teacher's own, else the longest seen.
    shown: dict[str, str] = {}
    for _, _, ws in raw:
        for w in ws:
            k = _lk(w)
            if k and (k not in shown or len(w) > len(shown[k])):
                shown[k] = w
    shown.update(full)

    def display(k: str) -> str:
        k = same.get(k, k)
        n = shown.get(k, k)
        n = re.sub(r"\s+", " ", n).strip(" .")
        return n.title() if n.isupper() or n.islower() else n

    # The school's staff list: every spelling to a name on it.
    people = []
    for p in staff or []:
        nm = _staff_name(p.get("name") or "")
        if nm:
            people.append((nm, _lk(nm), [_lk(w) for w in nm.split()],
                           {_concept(x) for x in p.get("subjects") or [] if x}))

    def name_score(k: str, key: str, words: list[str]) -> float:
        if not k:
            return 0
        if k == key:
            return 4
        if len(k) >= 3 and (key.startswith(k) or any(w.startswith(k) for w in words)):
            return 3
        if len(key) >= 4 and k.startswith(key):
            return 2.5
        if _close(k, key) or any(_close(k, w) for w in words if len(w) >= 4):
            return 2
        return 0

    votes: dict[str, Counter] = {}

    def staff_match(k: str, code: str | None, use_votes: bool = False) -> str | None:
        if not people:
            return None
        want = _concept(code) if code else ""
        scored = []
        for nm, key, words, subs in people:
            sc = name_score(k, key, words)
            if not sc:
                continue
            if want and want in subs:
                sc += 1.5
            if use_votes and code and votes.get(code):
                top = votes[code].most_common(1)[0][0]
                if top in subs:
                    sc += 0.5
            scored.append((sc, nm))
        if not scored:
            return None
        scored.sort(reverse=True)
        if len(scored) > 1 and scored[0][0] == scored[1][0] and scored[0][1] != scored[1][1]:
            return None
        return scored[0][1]

    def final_names(code, raws, keys, use_votes=False):
        out = []
        for w, k in zip(raws, keys):
            m = staff_match(_lk(w), code, use_votes) or staff_match(same.get(k, k), code, use_votes)
            out.append(m or display(k))
        return out

    if people:
        # What each subject's teachers mostly teach, to break a tie ("2LN-ABI":
        # the other 2LN teachers are Tamil teachers, so Abirami not Abinaya).
        for _, code, keys, raws in resolved:
            for nm in final_names(code, raws, keys):
                subs = next((p[3] for p in people if p[0] == nm), set())
                for c in subs:
                    votes.setdefault(code, Counter())[c] += 1

    tables = []
    days = sorted({d for b in blocks for d in b["days"]})
    periods = max((n for b in blocks for (_, n) in b["cells"]), default=0)
    for b in blocks:
        per: dict[str, Counter] = {}
        n_cells = Counter()
        for bb, code, who, raws in resolved:
            if bb is not b:
                continue
            n_cells[code] += 1
            per.setdefault(code, Counter()).update(final_names(code, raws, who, use_votes=True))
        grade, sec = b["section"]
        if grade.isdigit():
            grade = next(r for r, n in _ROMAN_N.items() if n == int(grade)).upper()
        items = []
        for code, n in n_cells.items():
            teachers = [t for t, _ in per[code].most_common()]
            items.append((spelt.get(code, code.upper()), str(n), "/".join(teachers)))
        tables.append({"label": f"Class {grade} {sec}", "items": items, "by_teacher": False,
                       "timetable": True,
                       "class_teacher": (staff_match(_lk(b["class_teacher"]), None) or display(_lk(b["class_teacher"])))
                       if b["class_teacher"] else "",
                       "week": {"days": days, "periods": periods}})
    return tables


def name_list(sheets: list[tuple[str, list[list[str]]]]) -> list[dict]:
    """A staff list: names with Mr / Mrs / Ms down a column, under the
    department they belong to ("HIGH SCHOOL ENGLISH", "PHY/CHEM").
    [{"name", "subjects"}], one per person however often they're listed."""
    best: list[dict] = []
    for _, rows in sheets:
        width = max((len(r) for r in rows), default=0)
        for c in range(width):
            col = [(r[c].strip() if c < len(r) else "") for r in rows]
            titled = [v for v in col if v and _TITLE.match(v) and len(v.split()) <= 6]
            if len(titled) < 5:
                continue
            people: dict[str, dict] = {}
            heading: list[str] = []
            for v in col:
                if not v or _COUNT.match(v):
                    continue
                if _TITLE.match(v) and len(v.split()) <= 6:
                    nm = _staff_name(v)
                    rec = people.setdefault(_lk(nm), {"name": nm, "subjects": []})
                    rec["subjects"] += [h for h in heading if h not in rec["subjects"]]
                elif not is_label(v) or _LEVEL_WORDS.search(v):
                    heading = [h.replace("-", " ").strip() for h in _heading_subjects(v)]
            if len(people) > len(best):
                best = list(people.values())
    return best


def plan_tables(sheets: list[tuple[str, list[list[str]]]], staff: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Every class table in the file, whichever way it's written: the
    Subjects | Periods | Teacher tables, a grid of counts, side blocks.
    The best sheet's, plus any other sheet nearly as full (a Word document's
    tables are often one class range each)."""
    proper = max(((_class_score(tb), t, tb) for t, rows in sheets for tb in [_class_tables(rows)]),
                 key=lambda x: x[0], default=(0, "", []))
    if len(proper[2]) >= 2:
        return proper[1], proper[2]
    # Last year's timetable, every sheet together: one teacher is written
    # the same short way on the primary sheet and the senior one.
    blocks = [b for _, rows in sheets for b in _timetable_blocks(rows)]
    timetable = _timetables_from(blocks, staff)
    scored = [(_class_score(tb), t, tb) for t, rows in sheets
              for tb in [max([_grid(rows) or _side_blocks(rows), _teacher_lists(rows)], key=_class_score)]]
    if timetable and _class_score(timetable) >= sum(sc for sc, _, _ in scored):
        return ", ".join(t for t, rows in sheets if _timetable_blocks(rows)), timetable
    top = max((s for s, _, _ in scored), default=0)
    if top == 0:
        return proper[1], proper[2]
    keep = [(t, tb) for s, t, tb in scored if s and s >= top * 0.2]
    # The same class on two sheets (primary and high school lists both
    # naming Class 5 A): one table.
    merged: dict[str, dict] = {}
    for _, tb in keep:
        for x in tb:
            k = _key(x["label"])
            if k in merged:
                merged[k]["items"] = merged[k]["items"] + [i for i in x["items"] if i not in merged[k]["items"]]
            else:
                merged[k] = {**x, "items": list(x["items"])}
    return ", ".join(t for t, _ in keep), list(merged.values())


def _split_people(cell: str) -> list[str]:
    out = []
    for p in re.split(r"\s*(?:/|,|&|\band\b|\+)\s*", cell):
        p = p.strip(" .-")
        if p and _key(p) not in _NOT_A_TEACHER and not is_label(p):
            out.append(p)
    return out


def _split_subjects(cell: str) -> list[str]:
    """"Maths/Bio" is two, "English Lit + Lib" two; "Eng (Lang/Lit)" stays
    whole - what's in brackets belongs to the word before it."""
    parts, depth, cur = [], 0, ""
    for ch in cell:
        depth += ch == "("
        depth -= ch == ")" and depth > 0
        if depth == 0 and ch in "/,+&":
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip(" .-") for p in parts if p.strip(" .-")]


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
    # Or a grid of counts per class, or a column of subjects per stream.
    by_class = plan_tables(sheets)
    class_tables = by_class[1] if len(by_class[1]) >= 2 else []
    if class_tables and kind == "teachers" and not any(cell for t in class_tables for _, _, cell in t["items"]):
        raise ValueError(
            "This file has the periods for each class but no teachers' names in it. Upload it under "
            "Subjects to add its subjects, or in Get started step 4 (What each class needs) to fill in "
            "every class's periods. Then upload a staff list here."
        )

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

    if not ({"name", "first_name"} & set(mapping.values())) and kind == "subjects" and not class_tables:
        # No heading anywhere - a bare list of subjects: the column with the
        # most names in it.
        all_rows = [r for r in rows if any(r)]
        width = max((len(r) for r in all_rows), default=0)
        counts = [sum(1 for r in all_rows if i < len(r) and r[i].strip() and not _COUNT.match(r[i])
                      and not is_label(r[i])) for i in range(width)]
        if counts and max(counts) >= 2:
            col = counts.index(max(counts))
            headings, body, mapping, idx = [""] * width, all_rows, {col: "name"}, -1
    if not ({"name", "first_name"} & set(mapping.values())) and kind == "teachers" and not class_tables:
        people = name_list(sheets)
        if people:
            layout = "name_list"
            headings = ["Teacher", "Department"]
            body = [[p["name"], ";".join(p["subjects"])] for p in people]
            mapping, idx = {0: "name", 1: "qualified_subjects"}, -1
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
    subject_meaning = {i: (_checked(i, answer["subjects"][i], by_rule_subjects[i])
                           if answer and i in answer["subjects"] else by_rule_subjects[i])
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

    out, notes, seen_names, row_items = [], [], set(), []
    for rec, subjects, grades in raw_rows:
        row_notes = []
        for item in dict.fromkeys(subjects + ([rec["name"]] if kind == "subjects" else [])):
            if item in doubtful_subjects:
                row_notes.append(f"“{item}” → {', '.join(subject_meaning[item])}?")
        for item in dict.fromkeys(grades):
            if item in doubtful_grades:
                row_notes.append(f"“{item}” → {', '.join(grade_meaning[item])}?")
        notes.append(row_notes)
        raw_name = rec["name"]
        if kind == "subjects":
            names = subject_meaning.get(rec["name"]) or [rec["name"]]
            rec = {**rec, "name": names[0]}
            # The same subject from several class tables, or spelt two ways: once.
            if rec["name"].lower() in seen_names:
                notes.pop()
                # Still remember which typed names became it.
                for prev, items in zip(out, row_items):
                    if prev["name"].lower() == rec["name"].lower():
                        items.append(raw_name)
                continue
            seen_names.add(rec["name"].lower())
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
        row_items.append([raw_name] if kind == "subjects" else list(dict.fromkeys(subjects)))

    read_as = [f"“{headings[i]}” as {FIELDS[kind][f]}" for i, f in sorted(mapping.items())
               if headings[i] and f not in ("subject_mark", "grade_mark")]
    if class_tables:
        labels = [t["label"] for t in class_tables]
        read_as = [
            "a list under each teacher's name of the classes they take and how many periods",
            f"{len(labels)} sections in all",
        ] if any(t.get("by_teacher") for t in class_tables) else [f"a table for each class ({len(labels)}: {', '.join(labels[:8])}{'…' if len(labels) > 8 else ''})",
                   "the subjects in each" + (", and who teaches them" if kind == "teachers" else "")]
    if not read_as and not class_tables:
        read_as = ["the column of subject names (it has no heading)"]
    marks = [headings[i] for i, f in sorted(mapping.items()) if f in ("subject_mark", "grade_mark")]
    if marks:
        read_as.append("a mark under " + ", ".join(f"“{m}”" for m in marks) + " as teaching it")
    return out, {"sheet": title, "header_row": idx + 1, "layout": layout, "read_as": read_as,
                 "matched": matched, "doubtful": doubtful, "row_notes": notes, "used_ai": used_ai,
                 # For the questions before saving: what each row was typed as, and
                 # the readings only the AI made.
                 "row_items": row_items, "doubtful_items": {i: subject_meaning[i] for i in doubtful_subjects}}


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


def check_rows(kind: str, rows: list[dict], school_subjects=(), school_grades=(),
               look_alikes: bool = True) -> tuple[list[str], list[list[str]]]:
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

    if not look_alikes:  # asked as questions instead - see make_questions
        return checks, notes
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

# ------------------------------------------------- questions before saving

def _subjects_of(kind: str, row: dict) -> list[str]:
    if kind == "subjects":
        return [row.get("name", "")]
    return [x.strip() for x in row.get("qualified_subjects", "").split(";") if x.strip()]


def _rename_subject(kind: str, rows: list[dict], old: str, new: str) -> list[dict]:
    field = "name" if kind == "subjects" else "qualified_subjects"
    return [{"row": n, "field": field, "remove": [old], "add": [new]}
            for n, r in enumerate(rows) if _norm(old) in {_norm(x) for x in _subjects_of(kind, r)}]


def _rename_teacher(rows: list[dict], old: str, new: str) -> list[dict]:
    return [{"row": n, "field": "name", "remove": [old], "add": [new]}
            for n, r in enumerate(rows) if _norm(r.get("name", "")) == _norm(old)]


def make_questions(kind: str, rows: list[dict], info: dict, school_subjects=(), school_teachers=()) -> list[dict]:
    """What the school is asked before anything is saved, so nothing is
    guessed: two spellings that may be one teacher or one subject (in the
    sheet, or the sheet and what's already here), and readings only the AI
    made. Each answer is a list of edits to the previewed rows:
    {"row", "field", "remove": [...], "add": [...]}."""
    questions: list[dict] = []
    school_subjects, school_teachers = list(school_subjects), list(school_teachers)

    if kind == "teachers":
        mine = list(dict.fromkeys(r["name"] for r in rows))
        have = {_norm(t) for t in school_teachers}
        mine_new = [m for m in mine if _norm(m) not in have]
        for a, b in look_alike_people(mine_new + [t for t in school_teachers if _norm(t) not in {_norm(m) for m in mine}]):
            a_here, b_here = _norm(a) in have, _norm(b) in have
            if a_here and b_here:
                continue
            if a_here or b_here:
                here, sheet = (a, b) if a_here else (b, a)
                questions.append({
                    "id": f"teacher:{sheet}|{here}",
                    "text": f"Is “{sheet}” in the sheet the same teacher as “{here}”, who is already here?",
                    "options": [
                        {"label": f"Yes, the same person (keep “{here}”)", "edits": _rename_teacher(rows, sheet, here)},
                        {"label": f"No, “{sheet}” is someone new", "edits": []},
                    ],
                })
            else:
                questions.append({
                    "id": f"teacher:{a}|{b}",
                    "text": f"Are “{a}” and “{b}” the same teacher?",
                    "options": [
                        {"label": f"Yes, call them “{b}”", "edits": _rename_teacher(rows, a, b)},
                        {"label": f"Yes, call them “{a}”", "edits": _rename_teacher(rows, b, a)},
                        {"label": "No, two different teachers", "edits": []},
                    ],
                })

    named = list(dict.fromkeys(x for r in rows for x in _subjects_of(kind, r) if x))
    known = {_norm(x) for x in school_subjects}
    for a, b in look_alike_subjects(named, school_subjects):
        if _norm(a) in known or _norm(b) in known:
            here, sheet = (a, b) if _norm(a) in known else (b, a)
            questions.append({
                "id": f"subject:{sheet}|{here}",
                "text": f"Is “{sheet}” in the sheet the same subject as “{here}”, which is already here?",
                "options": [
                    {"label": f"Yes, the same (keep “{here}”)", "edits": _rename_subject(kind, rows, sheet, here)},
                    {"label": f"No, “{sheet}” is a different subject", "edits": []},
                ],
            })
        else:
            questions.append({
                "id": f"subject:{a}|{b}",
                "text": f"Are “{a}” and “{b}” the same subject?",
                "options": [
                    {"label": f"Yes, call it “{b}”", "edits": _rename_subject(kind, rows, a, b)},
                    {"label": f"Yes, call it “{a}”", "edits": _rename_subject(kind, rows, b, a)},
                    {"label": "No, two different subjects", "edits": []},
                ],
            })

    # Readings only the AI made: "Comp Sci" as Computer Science?
    field = "name" if kind == "subjects" else "qualified_subjects"
    for item, means in info.get("doubtful_items", {}).items():
        where = [n for n, items in enumerate(info.get("row_items", [])) if item in items]
        if not where:
            continue
        questions.append({
            "id": f"meaning:{item}",
            "text": f"Is “{item}” {' and '.join(f'“{m}”' for m in means)}?",
            "options": [
                {"label": "Yes", "edits": []},
                {"label": f"No, keep “{item}” as its own subject",
                 "edits": [{"row": n, "field": field, "remove": list(means), "add": [item]} for n in where]},
            ],
        })
    return questions


def apply_edits(rows: list[dict], edits: list[dict]) -> list[dict]:
    """The rows with the chosen answers' edits made (the frontend makes the
    same ones; this is what the tests and any server-side use rely on)."""
    out = [dict(r) for r in rows]
    for e in edits:
        r = out[e["row"]]
        if e["field"] == "name":
            if _norm(r.get("name", "")) in {_norm(x) for x in e["remove"]}:
                r["name"] = e["add"][0]
        else:
            items = [x.strip() for x in r.get(e["field"], "").split(";") if x.strip()]
            gone = {_norm(x) for x in e["remove"]}
            items = [x for x in items if _norm(x) not in gone]
            for a in e["add"]:
                if _norm(a) not in {_norm(x) for x in items}:
                    items.append(a)
            r[e["field"]] = ";".join(items)
    return out


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
    checks, check_notes = check_rows(kind, rows, school_subjects, school_grades, look_alikes=False)
    model = Subject if kind == "subjects" else Teacher
    existing = [x.name for x in db.query(model).filter(model.school_id == school_id)]
    have = {_norm(x) for x in existing}
    questions = make_questions(kind, rows, info, school_subjects, existing if kind == "teachers" else ())
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
        "questions": questions,
        "new_subjects": new_subjects,
    }

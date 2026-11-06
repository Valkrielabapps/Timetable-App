"""
A school's own subjects or teachers sheet, whatever its layout. The AI says
what each column is and what each subject and grade value means; code reads
every row. Without the AI the same happens on rules, less cleverly.
"""
import io

import openpyxl
import pytest

from app.core.database import SessionLocal
from app.models.school import Subject, Teacher
from app.services import smart_import
from app.services.smart_import import smart_rows
from tests.conftest import create_school, signup


def xlsx(*sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class NoAI:
    """No API key: rules only."""
    calls = 0

    def columns(self, *a):
        return None

    def values(self, *a):
        return None


class FakeAI:
    def __init__(self, columns=None, layout="rows", subjects=None, grades=None):
        self._columns, self._layout = columns or {}, layout
        self._subjects, self._grades = subjects or {}, grades or {}
        self.seen = {}

    def columns(self, headings, samples, kind, school_subjects):
        self.seen.setdefault("columns", []).append((list(headings), len(samples)))
        cols = self._columns(headings) if callable(self._columns) else self._columns
        return {"layout": self._layout, "columns": cols}

    def values(self, subject_items, grade_items, school_subjects, school_grades):
        self.seen["values"] = (list(subject_items), list(grade_items))
        return {"subjects": {i: self._subjects[i] for i in subject_items if i in self._subjects},
                "grades": {g: self._grades[g] for g in grade_items if g in self._grades}}


GRADES = ["Grade 6", "Grade 7", "Grade 8", "Grade 9", "Grade 10"]

STAFF = [
    ["Riverside Public School - Staff list 2026-27"],
    [],
    ["S.No", "Name of Teacher", "Subject 1", "Subject 2", "Classes", "Workload"],
    [1, "Priya Sharma", "Maths", "Physics", "6-8", 28],
    [2, "Rahul Mehta", "Eng", None, "IX", None],
]


def test_without_the_ai_known_headings_and_short_forms_still_work():
    rows, info = smart_rows("teachers", "staff.xlsx", xlsx(("Sheet1", STAFF)),
                            school_subjects=["Mathematics", "Physics", "English"], school_grades=GRADES, ai=NoAI())
    assert info["header_row"] == 3 and info["used_ai"] is False
    assert rows[0] == {"name": "Priya Sharma", "qualified_subjects": "Mathematics;Physics",
                       "qualified_grades": "Grade 6;Grade 7;Grade 8", "max_periods_per_week": "28"}
    assert rows[1]["qualified_grades"] == "Grade 9"
    assert "“Maths” as Mathematics" in info["matched"]


def test_the_ai_confirms_every_column_and_can_overrule_a_familiar_heading():
    # "Class" here is the class each teacher is in charge of, not what they teach.
    sheet = [["Teacher", "Class", "Subjects Taught"], ["Anita Rao", "9 A", "Biology"], ["Vivek Nair", "", "Chemistry"]]
    ai = FakeAI(columns={0: "name", 1: "ignore", 2: "qualified_subjects"})
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("S", sheet)), school_grades=GRADES, ai=ai)
    assert ai.seen["columns"]  # asked even though every heading was known
    assert rows[0] == {"name": "Anita Rao", "qualified_subjects": "Biology"}
    assert not any("Class" in r for r in info["read_as"])


def test_the_ai_says_what_messy_values_mean_seeing_only_the_distinct_values():
    many = [["Name", "Subjects", "Classes"]] + [
        [f"Teacher {i}", ["Maths", "Math", "maths & physics"][i % 3], ["Std 9", "Middle school"][i % 2]]
        for i in range(30)
    ]
    ai = FakeAI(
        columns={0: "name", 1: "qualified_subjects", 2: "qualified_grades"},
        subjects={"Maths": ["Mathematics"], "Math": ["Mathematics"], "maths & physics": ["Mathematics", "Physics"]},
        grades={"Middle school": ["Grade 6", "Grade 7", "Grade 8"]},
    )
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("S", many)),
                            school_subjects=["Mathematics"], school_grades=GRADES, ai=ai)
    subjects_sent, grades_sent = ai.seen["values"]
    assert sorted(subjects_sent) == ["Math", "Maths", "maths & physics"]  # 3 values, not 30 rows
    assert grades_sent == ["Middle school"]  # "Std 9" was clear without asking
    assert rows[1]["qualified_subjects"] == "Mathematics"
    assert rows[2]["qualified_subjects"] == "Mathematics;Physics"
    assert rows[0]["qualified_grades"] == "Grade 9" and rows[1]["qualified_grades"] == "Grade 6;Grade 7;Grade 8"
    assert all(n == 5 for _, n in ai.seen["columns"])  # five sample rows only


def test_a_grid_with_a_tick_under_each_subject():
    grid = [["Teacher", "Maths", "Physics", "Chemistry"],
            ["Priya", "✓", "✓", ""], ["Rahul", "", "", "Y"], ["Meena", "x", "no", "-"]]
    ai = FakeAI(columns={0: "name", 1: "subject_mark", 2: "subject_mark", 3: "subject_mark"})
    rows, info = smart_rows("teachers", "g.xlsx", xlsx(("G", grid)), school_subjects=["Maths", "Physics"], ai=ai)
    assert [(r["name"], r.get("qualified_subjects")) for r in rows] == [
        ("Priya", "Maths;Physics"), ("Rahul", "Chemistry"), ("Meena", "Maths")]
    assert any("a mark under" in r for r in info["read_as"])


def test_the_same_grid_is_read_without_the_ai_too():
    grid = [["Teacher", "Maths", "Physics"], ["Priya", "✓", ""], ["Rahul", "", "✓"]]
    rows, _ = smart_rows("teachers", "g.xlsx", xlsx(("G", grid)), school_subjects=["Maths", "Physics"], ai=NoAI())
    assert [r.get("qualified_subjects") for r in rows] == ["Maths", "Physics"]


def test_teachers_across_the_top_are_turned_round():
    sheet = [["Subject", "Priya Sharma", "Rahul Mehta"], ["Maths", "✓", ""], ["English", "", "✓"]]

    def cols(headings):
        # First look: the original sheet. Second: turned round.
        if headings[1] == "Priya Sharma":
            return {0: "ignore"}
        return {0: "name", 1: "subject_mark", 2: "subject_mark"}

    ai = FakeAI(columns=cols, layout="teachers_across")
    rows, info = smart_rows("teachers", "t.xlsx", xlsx(("T", sheet)), school_subjects=["Maths", "English"], ai=ai)
    assert info["layout"] == "teachers_across"
    assert [(r["name"], r.get("qualified_subjects")) for r in rows] == [("Priya Sharma", "Maths"), ("Rahul Mehta", "English")]


def test_a_subjects_list_is_matched_to_the_schools_own_names():
    sheet = [["Subject Name", "Room type"], ["Maths", ""], ["Chem", "lab"]]
    rows, info = smart_rows("subjects", "s.csv", "\n".join(",".join(r) for r in sheet).encode(),
                            school_subjects=["Mathematics"], ai=NoAI())
    assert rows == [{"name": "Mathematics"}, {"name": "Chemistry", "required_room_type": "lab"}]


def test_no_name_column_says_what_to_do():
    with pytest.raises(ValueError, match="column with each teacher's name"):
        smart_rows("teachers", "s.csv", b"Code,Phone\n1,999\n", ai=NoAI())


@pytest.fixture
def school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    for g in ("Grade 6", "Grade 9"):
        client.post("/api/class-groups", json={"school_id": sid, "grade": g, "name": "A"}, headers=h)
    return sid, h


def test_uploading_the_staff_list_adds_teachers_and_their_new_subjects(client, school, monkeypatch):
    sid, h = school
    monkeypatch.setattr(smart_import, "LiveAI", NoAI)
    r = client.post("/api/teachers/bulk-import", data={"school_id": sid},
                    files={"file": ("staff.xlsx", xlsx(("Sheet1", STAFF)), "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 2 and sorted(out["new_subjects"]) == ["Eng", "Maths", "Physics"]
    db = SessionLocal()
    try:
        priya = db.query(Teacher).filter_by(school_id=sid, name="Priya Sharma").one()
        names = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}
        assert sorted(names[i] for i in priya.qualified_subject_ids) == ["Maths", "Physics"]
        assert priya.qualified_grades == ["Grade 6"] and priya.max_periods_per_week == 28
        rahul = db.query(Teacher).filter_by(school_id=sid, name="Rahul Mehta").one()
        assert rahul.qualified_grades == ["Grade 9"]
    finally:
        db.close()


def test_the_old_template_still_imports(client, school, monkeypatch):
    sid, h = school
    monkeypatch.setattr(smart_import, "LiveAI", NoAI)
    r = client.post("/api/subjects/bulk-import", data={"school_id": sid},
                    files={"file": ("s.csv", b"name,required_room_type\nChemistry,lab\n", "text/csv")}, headers=h)
    assert r.status_code == 200 and r.json()["created"] == 1

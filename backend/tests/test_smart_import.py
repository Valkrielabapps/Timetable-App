"""
A school's own subjects or teachers sheet, whatever its layout: a title row
above the headings, its own words for the columns, numbered subject
columns, the list on the second sheet. The AI is only asked about headings
it can't place, and is only shown the headings and five rows.
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
    """sheets: (title, rows)"""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets:
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def no_ai(*_a, **_k):
    raise AssertionError("the AI shouldn't be asked when every heading is known")


STAFF = [
    ["Riverside Public School - Staff list 2026-27"],
    [],
    ["S.No", "Name of Teacher", "Subject 1", "Subject 2", "Classes", "Workload"],
    [1, "Priya Sharma", "Maths", "Physics", "6-8", 28],
    [2, "Rahul Mehta", "English", None, "Grade 9", None],
]


def test_a_title_row_numbered_columns_and_own_words():
    rows, info = smart_rows("teachers", "staff.xlsx", xlsx(("Sheet1", STAFF)),
                            ai=lambda *a: {0: "ignore"} if False else {})
    assert info["header_row"] == 3
    assert rows[0] == {"name": "Priya Sharma", "qualified_subjects": "Maths;Physics",
                       "qualified_grades": "6-8", "max_periods_per_week": "28"}
    assert rows[1]["name"] == "Rahul Mehta" and rows[1]["qualified_subjects"] == "English"
    assert "“Name of Teacher” as teacher's full name" in info["read_as"]


def test_the_ai_is_asked_only_about_unknown_headings_and_sees_only_a_few_rows():
    seen = {}

    def fake_ai(headings, samples, kind):
        seen["headings"], seen["samples"] = headings, samples
        return {1: "name", 2: "qualified_subjects"}

    many = [["Emp code", "Faculty member", "Expertise"]] + [[f"E{i}", f"Teacher {i}", "Chemistry"] for i in range(40)]
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("Sheet1", many)), ai=fake_ai)
    assert len(seen["samples"]) == 5  # never the whole list
    assert len(rows) == 40 and rows[7] == {"name": "Teacher 7", "qualified_subjects": "Chemistry"}
    assert info["used_ai"] is True


def test_first_and_last_name_columns_make_one_name():
    rows, _ = smart_rows("teachers", "s.csv",
                         b"First Name,Surname,Email ID\nAnita,Rao,anita@x.in\n", ai=no_ai)
    assert rows == [{"name": "Anita Rao", "email": "anita@x.in"}]


def test_the_list_on_another_sheet_is_found():
    rows, info = smart_rows("subjects", "s.xlsx", xlsx(
        ("Cover", [["Prepared by the office"]]),
        ("Subjects", [["Subject Name", "Room type"], ["Chemistry", "lab"], ["Maths", None]]),
    ), ai=no_ai)
    assert info["sheet"] == "Subjects"
    assert rows == [{"name": "Chemistry", "required_room_type": "lab"}, {"name": "Maths"}]


def test_no_name_column_says_what_to_do():
    with pytest.raises(ValueError, match="column with each teacher's name"):
        smart_rows("teachers", "s.csv", b"Code,Phone\n1,999\n", ai=lambda *a: None)


@pytest.fixture
def school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 6", "name": "A"}, headers=h)
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 9", "name": "A"}, headers=h)
    return sid, h


def test_uploading_the_staff_list_adds_teachers_and_their_new_subjects(client, school, monkeypatch):
    sid, h = school
    monkeypatch.setattr(smart_import, "_ai_map", lambda *a, **k: None)
    r = client.post("/api/teachers/bulk-import", data={"school_id": sid},
                    files={"file": ("staff.xlsx", xlsx(("Sheet1", STAFF)), "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["created"] == 2 and sorted(out["new_subjects"]) == ["English", "Maths", "Physics"]
    assert out["sheet"] == "Sheet1" and any("Workload" in x for x in out["read_as"])
    db = SessionLocal()
    try:
        priya = db.query(Teacher).filter_by(school_id=sid, name="Priya Sharma").one()
        names = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}
        assert sorted(names[i] for i in priya.qualified_subject_ids) == ["Maths", "Physics"]
        assert priya.qualified_grades == ["Grade 6"] and priya.max_periods_per_week == 28
    finally:
        db.close()


def test_the_old_template_still_imports(client, school):
    sid, h = school
    r = client.post("/api/subjects/bulk-import", data={"school_id": sid},
                    files={"file": ("s.csv", b"name,required_room_type\nChemistry,lab\n", "text/csv")}, headers=h)
    assert r.status_code == 200 and r.json()["created"] == 1

"""
The staff sheet written teacher by teacher: a department heading, the
teachers' names across a row, and under each name the classes they take
("VIII A-3 PHY", "I A,B,C - 3"). Modelled on a real school's file.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, Subject, SubjectRequirement, Teacher
from app.services.smart_import import _entry, _teacher_cell, plan_tables, smart_rows
from tests.conftest import create_school, signup
from tests.test_smart_import import NoAI, xlsx

HIGH = [
    ["", "HIGHSCHOOL MATHS", "", "", "", ""],
    ["", "MRS MARTINA", "", "MRS.ANUPRIYA", "", "MRS.LEKA"],
    ["", "VIII B-10", "", "VII C- 6", "", "VIII C- 10"],
    ["", "VIII A-10", "", "VII A-6", "", "IX A- 10"],
    ["", "", "", "VII C- 5 C.T", "", ""],
    ["", "HIGHSCHOOL PHY,CHEM", "", "", "", ""],
    ["", "MRS.HARINIKA-PHY", "", "MR.MUKESH", "", "MR.ALBERT"],
    ["", "VII C- 3", "", "VIII A-3 PHY", "", "IX C- 3"],
    ["", "VII A- 4", "", "VIII A- 3 CHEM", "", "VIII B- 2 C.T"],
    ["", "SOCIAL", "", "", "", ""],
    ["", "MRS.AKILA", "", "MRS.MARY", "", ""],
    ["", "XI A- 5", "", "XI A- 5", "", ""],
    ["", "GAMES", "", "", "", ""],
    ["", "MR.KALKATH/MR.JOSEPH", "", "", "", ""],
    ["", "VIIA,B,C-8", "", "", "", ""],
]
PRIMARY = [
    ["", "PRIMARY ,HIGHSCHOOL  HINDI", "", "", "", ""],
    ["", "MRS.MALAR", "", "MRS.KAVITHA", "", ""],
    ["", "III A- 3", "", "IX 2LN-5", "", ""],
    ["", "VII-3LN-2", "", "1-A,B,C - 3", "", ""],
    ["", "VC-5 C.T", "", "III B-I LIS", "", ""],
]
FILE = xlsx(("HIGHSCHOOL", HIGH), ("PRIMARY", PRIMARY))


@pytest.mark.parametrize("text,want", [
    ("VIII B-10", ("VIII", ["B"], 10, "")), ("IC -10", ("I", ["C"], 10, "")), ("XIIA-10", ("XII", ["A"], 10, "")),
    ("VIII A-3 PHY", ("VIII", ["A"], 3, "PHY")), ("IX B-1COM", ("IX", ["B"], 1, "COM")),
    ("VB-3C.T", ("V", ["B"], 3, "C.T")), ("III B-I LIS", ("III", ["B"], 1, "LIS")),
    ("IVABCD-8", ("IV", ["A", "B", "C", "D"], 8, "")), ("1-A,B,C - 3", ("1", ["A", "B", "C"], 3, "")),
    ("IX-2 3LN", ("IX", [], 2, "3rd language")), ("VII -3LANG-2", ("VII", [], 2, "3rd language")),
    ("XI A- AI", ("XI", ["A"], 0, "AI")), ("II D- 5-MATHS", ("II", ["D"], 5, "MATHS")),
])
def test_reading_one_line(text, want):
    assert _entry(text) == want


def test_names_and_not_names():
    assert _teacher_cell("MRS.HARINIKA-PHY") == [("Harinika", "PHY")]
    assert _teacher_cell("MR.JOHN - BIOLOGY") == [("John", "BIOLOGY")]
    assert _teacher_cell("MR.KALKATH/MR.JOSEPH") == [("Kalkath", ""), ("Joseph", "")]
    assert _teacher_cell("HIGHSCHOOL MATHS") is None and _teacher_cell("VIII B-10") is None


def test_the_teachers_import_reads_every_teacher():
    rows, info = smart_rows("teachers", "t.xlsx", FILE, ai=NoAI())
    by = {r["name"]: r["qualified_subjects"].split(";") for r in rows}
    assert by["Martina"] == ["Maths"]
    assert set(by["Anupriya"]) == {"Maths", "C.T"}
    assert by["Harinika"] == ["Physics"]  # her own, from "-PHY"
    assert set(by["Mukesh"]) == {"Physics", "Chemistry"}  # said on each line
    assert set(by["Albert"]) == {"Physics", "Chemistry", "C.T"}  # the heading's, both
    assert by["Kalkath"] == by["Joseph"] == ["Physical Education"]
    assert "Hindi (3rd language)" in by["Malar"] and "Hindi (2nd language)" in by["Kavitha"]
    assert "Listening" in by["Kavitha"]
    assert "list under each teacher" in info["read_as"][0]


def test_each_section_gets_its_periods_and_teacher():
    _, tables = plan_tables([("HIGHSCHOOL", HIGH), ("PRIMARY", PRIMARY)])
    by = {t["label"]: {s: (n, w) for s, n, w in t["items"]} for t in tables}
    assert by["Class VIII A"]["MATHS"] == ("10", "Martina")
    assert by["Class VIII A"]["PHY"] == ("3", "Mukesh") and by["Class VIII A"]["CHEM"] == ("3", "Mukesh")
    assert by["Class VII B"]["GAMES"] == ("8", "Kalkath/Joseph")
    assert by["Class XI A"]["SOCIAL"] == ("10", "Akila/Mary")  # two teachers' shares add up
    assert by["Class I B"]["HINDI"] == ("3", "Kavitha")  # "1-A,B,C" is Class I
    assert "Class 1 A" not in by


def test_the_class_plan_fills_every_section_from_it(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        for d in range(5):
            for o in range(9):
                db.add(Period(school_id=sid, day_of_week=d, order=o, label=f"P{o}"))
        db.commit()
    finally:
        db.close()
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": ("t.xlsx", FILE, "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        subs = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}
        names = {t.id: t.name for t in db.query(Teacher).filter_by(school_id=sid)}
        g = db.query(ClassGroup).filter_by(school_id=sid, grade="Grade 8", name="A").one()
        plan = {subs[x.subject_id]: (x.periods_per_week, names.get(x.preferred_teacher_id))
                for x in db.query(SubjectRequirement).filter_by(class_group_id=g.id)}
        assert plan["Maths"] == (10, "Martina")
        assert plan["Physics"] == (3, "Mukesh") and plan["Chemistry"] == (3, "Mukesh")
    finally:
        db.close()

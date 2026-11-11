"""
Allotment sheets written as a grid of counts (classes down, subjects
across - or the other way round) or as a column of subjects per stream,
read the same as a table per class: by the subjects import and by the class
plan. Modelled on a real school's Word document.
"""
from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, Subject, SubjectRequirement
from app.services import smart_import
from app.services.smart_import import plan_tables, smart_rows
from tests.conftest import create_school, signup
from tests.test_import_word import docx, table
from tests.test_smart_import import NoAI, xlsx

GRID = [
    ["ALLOTMENT -2026 -2027"],
    ["CLASS", "ENG", "TAMIL", "MAT", "PHY", "CHEM", "GAME", "C.T", "TOTAL"],
    ["I", "6", "4", "5", "-", "-", "3", "-", "18"],
    ["VI", "3+3", "4", "6", "3", "-", "2", "1", "22"],
    ["N/J VIII", "4", "5", "10", "3", "3", "2", "", "27"],
    ["CUET X", "6", "5", "10", "2", "2", "2", "-", "27"],
]
STREAMS = [
    ["GRADE XI AND XII –ALLOT MENT -2026-2027"],
    ["NEET", "", "JEE", "", "CUET", ""],
    ["ENGLISH", "4", "ENGLISH", "4", "ENGLISH", "7"],
    ["PHYSICS", "9", "PHYSICS", "9", "ECO", "8"],
    ["BIOLOGY", "10", "MATHS", "10", "ACCO", "8"],
    ["AI", "2", "", "2", "", "2"],
    ["TOTAL", "25", "", "25", "", "25"],
]
DOC = docx(table(GRID), table(STREAMS))


def test_a_grid_and_stream_columns_become_a_table_per_class():
    title, tables = plan_tables(smart_import.read_sheets("a.docx", DOC))
    by = {t["label"]: [(s, n) for s, n, _ in t["items"]] for t in tables}
    assert by["Class I"] == [("ENG", "6"), ("TAMIL", "4"), ("MAT", "5"), ("GAME", "3")]
    assert ("ENG", "3+3") in by["Class VI"] and ("C.T", "1") in by["Class VI"]
    assert "Class VIII (N/J)" in by and "Class X (CUET)" in by
    # One column of subjects per stream, for each class in the title.
    assert by["Class XI (NEET)"] == [("ENGLISH", "4"), ("PHYSICS", "9"), ("BIOLOGY", "10"), ("AI", "2")]
    assert by["Class XII (CUET)"][-1] == ("AI", "2")  # "AI" named once, for every stream
    assert not any("TOTAL" in s.upper() for t in tables for s, _, _ in t["items"])
    assert "I" not in {s for t in tables for s, _, _ in t["items"]}  # class labels aren't subjects


def test_the_subjects_import_reads_every_subject_once():
    rows, info = smart_rows("subjects", "a.docx", DOC, ai=NoAI())
    names = [r["name"] for r in rows]
    for want in ("English", "Tamil", "Maths", "Physics", "Chemistry", "Physical Education", "Biology",
                 "Economics", "Accountancy", "Artificial Intelligence", "C.T"):
        assert want in names
    assert len(names) == len({n.lower() for n in names})
    assert not {"TOTAL", "CLASS", "I", "VI", "NEET"} & set(names)


def test_the_teachers_import_says_this_file_has_no_teachers():
    try:
        smart_rows("teachers", "a.docx", DOC, ai=NoAI())
    except ValueError as e:
        assert "no teachers' names" in str(e)
    else:
        raise AssertionError("expected a clear message")


def test_subjects_down_and_classes_across():
    sheet = [["Subject", "Class 6", "Class 7", "Class 8"],
             ["English", "6", "6", "5"], ["Maths", "7", "7", "8"], ["Hindi", "4", "-", "3"]]
    _, tables = plan_tables([("s", sheet)])
    by = {t["label"]: [(s, n) for s, n, _ in t["items"]] for t in tables}
    assert by["Class 7"] == [("English", "6"), ("Maths", "7")]
    assert ("Hindi", "3") in by["Class 8"]


def test_a_bare_list_of_subjects_with_no_heading():
    content = xlsx(("s", [["Mathematics"], ["English"], ["Physics Lab"], ["Tamil"]]))
    rows, _ = smart_rows("subjects", "s.xlsx", content, ai=NoAI())
    assert [r["name"] for r in rows] == ["Mathematics", "English", "Physics Lab", "Tamil"]


def test_the_class_plan_fills_every_class_from_the_grid(client):
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
                    files={"file": ("a.docx", DOC, "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        subs = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}
        groups = {(g.grade, g.name): g for g in db.query(ClassGroup).filter_by(school_id=sid)}

        def plan(grade, name):
            g = groups[(grade, name)]
            return {subs[x.subject_id]: x.periods_per_week for x in db.query(SubjectRequirement).filter_by(class_group_id=g.id)}

        assert plan("Grade 6", "A")["English"] == 6  # "3+3"
        assert plan("Grade 8", "NEET/JEE")["Maths"] == 10
        assert plan("Grade 10", "CUET")["Physics"] == 2
        assert plan("Grade 11", "NEET")["Biology"] == 10
        assert plan("Grade 12", "CUET")["Economics"] == 8
    finally:
        db.close()

"""
Every section's weekly plan from the school's own allotment sheet: sections
made, periods and teachers filled in, and every way the sheet could be read
two ways asked about first.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, ElectiveBlock, Subject, SubjectRequirement, Teacher
from app.services import class_plan
from app.services.class_plan import _grade_and_rest, _sections_from
from tests.conftest import create_school, signup
from tests.test_smart_import import xlsx

SHEET = [
    ["Class 3", "", "", "", "CLASS 6-AB", "", ""],
    ["Subjects", "Periods", "Teacher", "", "Subjects", "Periods", "Teacher"],
    ["Maths", "6", "Anil", "", "Maths", "6", "Muthu/Vivek"],
    ["PT/Games", "2", "Suman", "", "Hist/civ", "3", "Usha"],
    ["Assembly", "0", "Class teacher", "", "English", "5", "Kavita k"],
    ["Total", "8", "", "", "TOTAL", "14", ""],
    [],
    ["CLASS 11 Science", "", "", "", "", "", ""],
    ["Subjects", "Periods", "Teacher", "", "", "", ""],
    ["Physics", "8", "Vivek", "", "", "", ""],
    ["Maths/Bio", "7", "Aman/Deepak", "", "", "", ""],
    ["Total", "15", "", "", "", "", ""],
]


@pytest.mark.parametrize("label,grade,sections", [
    ("CLASS 6-AB", "6", ["A", "B"]), ("Class 9 (Sci)", "9", ["Science"]), ("CLASS 9  (com)", "9", ["Commerce"]),
    ("CLASS 12 Humanities", "12", ["Humanities"]), ("Std IX A & B", "9", ["A", "B"]), ("Class KG", "KG", []),
    ("Class 3", "3", []), ("Grade 10-ABC", "10", ["A", "B", "C"]),
])
def test_reading_class_labels(label, grade, sections):
    g, rest = _grade_and_rest(label)
    assert g == grade and _sections_from(rest) == sections


@pytest.fixture
def school(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        from app.models.school import Period
        for d in range(5):
            for o in range(8):
                db.add(Period(school_id=sid, day_of_week=d, order=o, label=f"P{o}"))
        for name in ("Anil", "Muthu", "Vivek", "Suman", "Usha", "Kavita Khana", "Aman", "Deepak"):
            db.add(Teacher(school_id=sid, name=name, qualified_subject_ids=[], qualified_grades=[]))
        for name in ("Maths", "English", "Physics"):
            db.add(Subject(school_id=sid, name=name))
        db.commit()
    finally:
        db.close()
    return sid, h


def _preview(client, sid, h, sheet=SHEET):
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": ("allotment.xlsx", xlsx(("allotment", sheet)), "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_preview_asks_everything_it_cannot_tell(client, school):
    sid, h = school
    p = _preview(client, sid, h)
    qs = {q["id"]: q for q in p["questions"]}
    assert "Class 3" in qs["sections:all"]["text"]
    assert "Kavita k" in qs["teacher:Kavita k"]["text"]
    assert [o["label"] for o in qs["teacher:Kavita k"]["options"]][0] == "Kavita Khana"
    assert "shared:all" in qs
    combined = [q for q in p["questions"] if q["id"].startswith("combined:")]
    texts = " | ".join(q["text"] for q in combined)
    assert "“Hist/civ” (Usha), 3 periods" in texts and "“Maths/Bio” (Aman/Deepak), 7 periods" in texts
    assert "PT/Games" not in texts  # one subject spelt two ways
    assert p["skipped"] == ["Assembly (Class 3)"]
    # Nothing saved yet.
    db = SessionLocal()
    try:
        assert db.query(ClassGroup).filter_by(school_id=sid).count() == 0
    finally:
        db.close()


def test_commit_makes_sections_and_plans_exactly_as_answered(client, school):
    sid, h = school
    p = _preview(client, sid, h)
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    answers["teacher:Kavita k"] = "is:Kavita Khana"
    hist = next(q for q in p["questions"] if "Hist/civ" in q["text"])
    answers[hist["id"]] = "split:2"
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        names = {t.id: t.name for t in db.query(Teacher).filter_by(school_id=sid)}
        subs = {s.id: s.name for s in db.query(Subject).filter_by(school_id=sid)}

        def plan(grade, sec):
            cg = db.query(ClassGroup).filter_by(school_id=sid, grade=grade, name=sec).one()
            return {subs[r.subject_id]: (r.periods_per_week, names.get(r.preferred_teacher_id),
                                         sorted(names[i] for i in (r.allowed_teacher_ids or [])))
                    for r in db.query(SubjectRequirement).filter_by(class_group_id=cg.id)}, cg

        g3, _ = plan("Grade 3", "A")
        assert g3 == {"Maths": (6, "Anil", []), "Physical Education": (2, "Suman", [])}
        a, _ = plan("Grade 6", "A")
        b, _ = plan("Grade 6", "B")
        assert a["Maths"] == (6, "Muthu", []) and b["Maths"] == (6, "Vivek", [])  # one section each, in order
        assert a["History"] == (2, "Usha", []) and a["Civics"] == (1, "Usha", [])
        assert a["English"] == (5, "Kavita Khana", [])
        s11, cg11 = plan("Grade 11", "Science")
        assert s11 == {"Physics": (8, "Vivek", [])}
        (block,) = db.query(ElectiveBlock).filter_by(class_group_id=cg11.id).all()
        assert block.periods_per_week == 7
        assert sorted((subs[o.subject_id], names[o.preferred_teacher_id]) for o in block.options) == [
            ("Biology", "Deepak"), ("Maths", "Aman")]
        # Everyone named is now qualified for what they were given, for that grade.
        usha = db.query(Teacher).filter_by(school_id=sid, name="Usha").one()
        assert {subs[i] for i in usha.qualified_subject_ids} == {"History", "Civics"}
        assert db.query(Teacher).filter_by(school_id=sid, name="Kavita k").count() == 0
    finally:
        db.close()


def test_every_question_must_be_answered(client, school):
    sid, h = school
    p = _preview(client, sid, h)
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": {}}, headers=h)
    assert r.status_code == 400 and "Answer every question" in r.json()["detail"]
    db = SessionLocal()
    try:
        assert db.query(ClassGroup).filter_by(school_id=sid).count() == 0  # all or nothing
    finally:
        db.close()


def test_an_overfull_week_and_an_overloaded_teacher_are_found_first(client, school):
    sid, h = school
    sheet = [["CLASS 7-AB", "", ""], ["Subjects", "Periods", "Teacher"],
             ["Maths", "30", "Anil"], ["English", "15", "Usha"], ["Total", "45", ""]]
    checks = " | ".join(_preview(client, sid, h, sheet)["checks"])
    assert "CLASS 7-AB has 45 periods planned but your week has 40 lessons" in checks
    assert "Anil is planned for 60 periods a week" in checks


def test_existing_plans_are_replaced_or_kept_as_asked(client, school):
    sid, h = school
    p = _preview(client, sid, h)
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    db = SessionLocal()
    try:
        cg = db.query(ClassGroup).filter_by(school_id=sid, grade="Grade 3", name="A").one()
        extra = Subject(school_id=sid, name="Dance")
        db.add(extra)
        db.flush()
        db.add(SubjectRequirement(class_group_id=cg.id, subject_id=extra.id, periods_per_week=1))
        db.commit()
        cg_id, extra_id = cg.id, extra.id
    finally:
        db.close()
    p = _preview(client, sid, h)
    q = next(q for q in p["questions"] if q["id"] == "existing")
    answers = {x["id"]: x["suggested"] for x in p["questions"]}
    answers["existing"] = "add"
    client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    db = SessionLocal()
    try:
        assert db.query(SubjectRequirement).filter_by(class_group_id=cg_id, subject_id=extra_id).count() == 1
    finally:
        db.close()
    answers["existing"] = "replace"
    client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    db = SessionLocal()
    try:
        assert db.query(SubjectRequirement).filter_by(class_group_id=cg_id, subject_id=extra_id).count() == 0
        assert db.query(ClassGroup).filter_by(school_id=sid, grade="Grade 3").count() == 1  # not duplicated
    finally:
        db.close()
    assert q["options"][0]["key"] == "replace"


def test_a_file_without_class_tables_says_what_to_do(client, school):
    sid, h = school
    r = client.post("/api/class-plan/preview", data={"school_id": sid},
                    files={"file": ("s.csv", b"Name,Subject\nAnil,Maths\n", "text/csv")}, headers=h)
    assert r.status_code == 400 and "table for each class" in r.json()["detail"]

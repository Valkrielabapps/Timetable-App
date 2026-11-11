"""
Check before saving: the school sees its sheet as it will be saved, with
doubtful readings and problems flagged, and nothing is saved until it
clicks Import.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import Subject, Teacher
from app.services import smart_import
from app.services.smart_import import check_rows, look_alike_subjects, smart_rows
from tests.conftest import create_school, signup
from tests.test_smart_import import FakeAI, NoAI, xlsx

GRADES = ["Grade 6", "Grade 7", "Grade 8", "Grade 9"]


def test_only_what_the_ai_alone_read_is_doubtful():
    sheet = [["Name", "Subjects", "Classes"],
             ["Priya", "Maths", "Std 9"], ["Rahul", "Comp Sci", "Middle school"]]
    ai = FakeAI(columns={0: "name", 1: "qualified_subjects", 2: "qualified_grades"},
                subjects={"Maths": ["Mathematics"], "Comp Sci": ["Computer Science"]},
                grades={"Middle school": ["Grade 6", "Grade 7", "Grade 8"]})
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("S", sheet)),
                            school_subjects=["Mathematics", "Computer Science"], school_grades=GRADES, ai=ai)
    # Maths -> Mathematics the rules knew too; Comp Sci and Middle school only the AI.
    assert info["doubtful"] == ["“Comp Sci” as Computer Science", "“Middle school” as Grade 6, Grade 7, Grade 8"]
    assert info["row_notes"][0] == []
    assert info["row_notes"][1] == ["“Comp Sci” → Computer Science?", "“Middle school” → Grade 6, Grade 7, Grade 8?"]


def test_checks_duplicates_no_subjects_unknown_grades_and_typos():
    rows = [
        {"name": "Priya Sharma", "qualified_subjects": "Chemistry", "qualified_grades": "Grade 9"},
        {"name": "priya  sharma", "qualified_subjects": "Chemestry"},
        {"name": "Rahul", "qualified_grades": "Grade 13"},
    ]
    checks, notes = check_rows("teachers", rows, school_subjects=["Chemistry"], school_grades=GRADES)
    text = " | ".join(checks)
    assert "1 teacher name appears more than once (Priya Sharma)" in text
    assert "1 teacher has no subjects (Rahul)" in text
    assert "“Grade 13” isn't a grade at this school (Rahul)" in text
    assert "“Chemistry” and “Chemestry” look like the same subject" in text
    assert "“Chemestry” or “Chemistry”?" in notes[1]
    assert "No subjects" in notes[2]


def test_subjects_meant_apart_are_not_called_typos():
    assert look_alike_subjects(["Hindi I", "Hindi II", "English Language", "English Literature"], []) == []
    assert look_alike_subjects(["Physics", "Phyiscs"], []) == [("Physics", "Phyiscs")]
    # The school's own two subjects: it chose them.
    assert look_alike_subjects([], ["Biology", "Biologi"]) == []


@pytest.fixture
def school(client, monkeypatch):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 9", "name": "A"}, headers=h)
    client.post("/api/teachers", json={"school_id": sid, "name": "Rahul Mehta"}, headers=h)
    monkeypatch.setattr(smart_import, "LiveAI", NoAI)
    return sid, h


SHEET = [["Name of Teacher", "Subject", "Classes"],
         ["Priya Sharma", "Maths", "IX"], ["Rahul Mehta", "Eng", "9"], ["Anil Kumar", "", "9"]]


def test_preview_saves_nothing_and_import_saves_what_was_shown(client, school):
    sid, h = school
    r = client.post("/api/teachers/bulk-import/preview", data={"school_id": sid},
                    files={"file": ("staff.xlsx", xlsx(("Staff", SHEET)), "application/octet-stream")}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["total"], p["subject_count"], p["will_update"]) == (3, 2, 1)
    assert p["new_subjects"] == ["Maths", "English"]
    assert p["rows"][0] == {"name": "Priya Sharma", "qualified_subjects": "Maths", "qualified_grades": "Grade 9"}
    assert p["row_notes"][2] == ["No subjects"]
    assert any("no subjects (Anil Kumar)" in c for c in p["checks"])
    db = SessionLocal()
    try:
        assert db.query(Teacher).filter_by(school_id=sid).count() == 1
        assert db.query(Subject).filter_by(school_id=sid).count() == 0
    finally:
        db.close()

    r = client.post("/api/teachers/bulk-import/commit", json={"school_id": sid, "rows": p["rows"]}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["created"], r.json()["updated"]) == (2, 1)
    assert sorted(r.json()["new_subjects"]) == ["English", "Maths"]
    db = SessionLocal()
    try:
        assert db.query(Teacher).filter_by(school_id=sid).count() == 3
    finally:
        db.close()


def test_subjects_preview_and_commit(client, school):
    sid, h = school
    csv = b"Subject Name,Room type\nChemistry,lab\nChemestry,\n"
    p = client.post("/api/subjects/bulk-import/preview", data={"school_id": sid},
                    files={"file": ("s.csv", csv, "text/csv")}, headers=h).json()
    assert p["total"] == 2 and not any("look like" in c for c in p["checks"])
    q = p["questions"][0]
    assert q["text"] == "Are “Chemistry” and “Chemestry” the same subject?"
    assert [o["label"] for o in q["options"]] == ["Yes, call it “Chemestry”", "Yes, call it “Chemistry”",
                                                  "No, two different subjects"]
    r = client.post("/api/subjects/bulk-import/commit", json={"school_id": sid, "rows": p["rows"][:1]}, headers=h)
    assert r.json()["created"] == 1


def test_a_viewer_cannot_preview_or_commit(client, school):
    sid, _ = school
    _, other = signup(client, email="other@example.com")
    r = client.post("/api/teachers/bulk-import/commit", json={"school_id": sid, "rows": []}, headers=other)
    assert r.status_code in (403, 404)


def test_questions_about_teachers_and_what_each_answer_changes(client, school):
    sid, h = school  # "Rahul Mehta" is already here
    sheet = [["Name", "Subjects"], ["Rahul Meta", "Maths"], ["Kavita K", "Hindi"], ["Kavita Khana", "Hindi, Comp Sci"]]
    ai = FakeAI(columns={0: "name", 1: "qualified_subjects"}, subjects={"Comp Sci": ["Computer Science"]})
    smart_import_live = smart_import.LiveAI
    try:
        smart_import.LiveAI = lambda: ai
        p = client.post("/api/teachers/bulk-import/preview", data={"school_id": sid},
                        files={"file": ("s.xlsx", xlsx(("S", sheet)), "application/octet-stream")}, headers=h).json()
    finally:
        smart_import.LiveAI = smart_import_live
    qs = {q["text"]: q for q in p["questions"]}
    assert set(qs) == {
        "Is “Rahul Meta” in the sheet the same teacher as “Rahul Mehta”, who is already here?",
        "Are “Kavita K” and “Kavita Khana” the same teacher?",
        "Is “Comp Sci” “Computer Science”?",
    }
    # Answers: Rahul is the one already here; the Kavitas are one person; Comp Sci stays as typed.
    edits = (qs["Is “Rahul Meta” in the sheet the same teacher as “Rahul Mehta”, who is already here?"]["options"][0]["edits"]
             + qs["Are “Kavita K” and “Kavita Khana” the same teacher?"]["options"][0]["edits"]
             + qs["Is “Comp Sci” “Computer Science”?"]["options"][1]["edits"])
    rows = smart_import.apply_edits(p["rows"], edits)
    assert rows == [{"name": "Rahul Mehta", "qualified_subjects": "Maths"},
                    {"name": "Kavita Khana", "qualified_subjects": "Hindi"},
                    {"name": "Kavita Khana", "qualified_subjects": "Hindi;Comp Sci"}]
    r = client.post("/api/teachers/bulk-import/commit", json={"school_id": sid, "rows": rows}, headers=h).json()
    assert (r["created"], r["updated"]) == (1, 2)  # Kavita once; Rahul and Kavita's second row update
    db = SessionLocal()
    try:
        assert sorted(t.name for t in db.query(Teacher).filter_by(school_id=sid)) == ["Kavita Khana", "Rahul Mehta"]
    finally:
        db.close()


def test_a_subject_like_one_already_here_is_asked_about(client, school):
    sid, h = school
    client.post("/api/subjects", json={"school_id": sid, "name": "Chemistry"}, headers=h)
    p = client.post("/api/subjects/bulk-import/preview", data={"school_id": sid},
                    files={"file": ("s.csv", b"Subject\nChemestry\nPhysics\n", "text/csv")}, headers=h).json()
    (q,) = p["questions"]
    assert q["text"] == "Is “Chemestry” in the sheet the same subject as “Chemistry”, which is already here?"
    rows = smart_import.apply_edits(p["rows"], q["options"][0]["edits"])
    assert [r["name"] for r in rows] == ["Chemistry", "Physics"]

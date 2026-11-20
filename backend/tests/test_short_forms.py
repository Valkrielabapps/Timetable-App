"""
A school's short forms are asked about once and remembered: "Kavita k" is
Kavita Khana, "WRKSHP" is Workshop. Every importer and the rules page read
them afterwards, so the same question never comes up twice.
"""
from app.core.database import SessionLocal
from app.models.school import SchoolAlias, Subject, Teacher
from app.services import aliases
from app.services.rule_text_hints import sentence_hints, typed_short_forms
from app.services.smart_import import _rule_subjects, make_questions, smart_rows
from tests.conftest import create_school, signup
from tests.test_class_plan import _preview, school  # noqa: F401 - fixture
from tests.test_smart_import import FakeAI, NoAI, xlsx


def test_built_in_short_forms_cover_common_indian_ones():
    got = _rule_subjects(["S. Sc.", "SUPW", "Work Education", "C.T", "VE", "Moral Science", "ROBO", "GAME",
                          "EVS", "2LN", "Gen. Science", "MUS"], [])
    assert got["S. Sc."] == ["Social Studies"]
    assert got["Work Education"] == ["Work Education"] or got["Work Education"] == ["SUPW"]
    assert got["SUPW"] == got["Work Education"]
    assert got["C.T"] == ["Class Teacher Period"]
    assert got["VE"] == got["Moral Science"]
    assert got["ROBO"] == ["Robotics"] and got["GAME"] == ["Physical Education"]
    assert got["2LN"] == ["2nd Language"] and got["MUS"] == ["Music"]
    assert got["Gen. Science"] == ["Science"]


def test_school_short_forms_come_before_the_built_in_reading():
    # "SC" is not guessed by the built-in list; this school said it's Science.
    got = _rule_subjects(["SC", "WRKSHP"], ["General Science"], {"sc": "General Science", "wrkshp": "Workshop"})
    assert got == {"SC": ["General Science"], "WRKSHP": ["Workshop"]}


def test_remember_skips_names_and_what_the_built_in_list_knows(orm_db):
    db = orm_db
    from app.models.school import School
    s = School(name="X")
    db.add(s)
    db.flush()
    assert aliases.remember(db, s.id, "subject", "Maths", "Maths") is None
    assert aliases.remember(db, s.id, "subject", "MAT", "Mathematics") is None  # built in
    assert aliases.remember(db, s.id, "subject", "WRKSHP", "Workshop") is not None
    assert aliases.remember(db, s.id, "teacher", "BEAUL", "Beula") is not None
    # The latest answer wins; one row per short form.
    aliases.remember(db, s.id, "teacher", "beaul", "Beula Rao")
    db.commit()
    assert db.query(SchoolAlias).count() == 2
    assert aliases.lookup(db, s.id, "teacher") == {"beaul": "Beula Rao"}


def test_a_renamed_teacher_is_followed(orm_db):
    db = orm_db
    from app.models.school import School
    s = School(name="X")
    db.add(s)
    db.flush()
    t = Teacher(school_id=s.id, name="Beula", qualified_subject_ids=[], qualified_grades=[])
    db.add(t)
    db.flush()
    aliases.remember_many(db, s.id, [{"kind": "teacher", "text": "BEAUL", "meaning": "Beula"}])
    t.name = "Beula Rao"
    db.commit()
    assert aliases.lookup(db, s.id, "teacher") == {"beaul": "Beula Rao"}


def test_a_confirmed_ai_reading_is_not_put_to_the_ai_or_asked_again():
    sheet = [["Name", "Subjects"], ["Priya", "Info Tech"]]
    ai = FakeAI(columns={0: "name", 1: "qualified_subjects"}, subjects={"Info Tech": ["Information Technology"]})
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("S", sheet)), school_subjects=["Information Technology"], ai=ai)
    qs = make_questions("teachers", rows, info, ["Information Technology"])
    yes = next(q for q in qs if q["id"] == "meaning:Info Tech")["options"][0]
    assert yes["remember"] == [{"kind": "subject", "text": "Info Tech", "meaning": "Information Technology"}]

    ai = FakeAI(columns={0: "name", 1: "qualified_subjects"}, subjects={"Info Tech": ["Something Else"]})
    rows, info = smart_rows("teachers", "s.xlsx", xlsx(("S", sheet)), school_subjects=["Information Technology"], ai=ai,
                            aliases={"subject": {"infotech": "Information Technology"}})
    assert rows[0]["qualified_subjects"] == "Information Technology"
    assert "Info Tech" not in ai.seen.get("values", ([], []))[0]
    assert info["doubtful"] == []
    assert not [q for q in make_questions("teachers", rows, info, ["Information Technology"]) if q["id"].startswith("meaning:")]


def test_a_teacher_short_form_becomes_the_teacher():
    sheet = [["Name", "Subjects"], ["BEAUL", "English"]]
    rows, _ = smart_rows("teachers", "s.xlsx", xlsx(("S", sheet)), school_subjects=["English"], ai=NoAI(),
                         aliases={"teacher": {"beaul": "Beula Rao"}})
    assert rows[0]["name"] == "Beula Rao"


def test_import_commit_keeps_the_confirmed_short_forms(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    r = client.post("/api/subjects/bulk-import/commit", headers=h, json={
        "school_id": sid, "rows": [{"name": "Workshop"}],
        "remember": [{"kind": "subject", "text": "WRKSHP", "meaning": "Workshop"}]})
    assert r.status_code == 200, r.text
    r = client.get(f"/api/schools/{sid}/short-forms", headers=h)
    items = r.json()["items"]
    assert [(x["kind"], x["text"], x["meaning"], x["source"]) for x in items] == [
        ("subject", "WRKSHP", "Workshop", "subjects")]
    db = SessionLocal()
    try:
        sub = db.query(Subject).filter_by(school_id=sid, name="Workshop").one()
        assert db.query(SchoolAlias).one().target_id == sub.id
    finally:
        db.close()
    # Removed from the page, and added by hand.
    assert client.delete(f"/api/schools/{sid}/short-forms/{items[0]['id']}", headers=h).json()["items"] == []
    r = client.post(f"/api/schools/{sid}/short-forms", headers=h,
                    json={"kind": "teacher", "text": "BEAUL", "meaning": "Beula Rao"})
    assert r.status_code == 200 and r.json()["items"][0]["text"] == "BEAUL"
    assert client.post(f"/api/schools/{sid}/short-forms", headers=h,
                       json={"kind": "subject", "text": "Maths", "meaning": "Mathematics"}).status_code == 400


def test_another_school_cannot_see_or_remove_them(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.post(f"/api/schools/{sid}/short-forms", headers=h,
                json={"kind": "teacher", "text": "BEAUL", "meaning": "Beula Rao"})
    _, h2 = signup(client, email="b@b.com")
    assert client.get(f"/api/schools/{sid}/short-forms", headers=h2).status_code in (403, 404)
    aid = client.get(f"/api/schools/{sid}/short-forms", headers=h).json()["items"][0]["id"]
    other = create_school(client, h2)["id"]
    assert client.delete(f"/api/schools/{other}/short-forms/{aid}", headers=h2).status_code == 404


def test_a_teacher_answered_once_in_a_timetable_is_not_asked_again(client, school):  # noqa: F811
    sid, h = school
    p = _preview(client, sid, h)
    assert "teacher:Kavita k" in {q["id"] for q in p["questions"]}
    answers = {q["id"]: q["suggested"] for q in p["questions"]}
    answers["teacher:Kavita k"] = "is:Kavita Khana"
    r = client.post("/api/class-plan/commit", json={"school_id": sid, "plan": p["plan"], "answers": answers}, headers=h)
    assert r.status_code == 200, r.text
    items = client.get(f"/api/schools/{sid}/short-forms", headers=h).json()["items"]
    assert ("teacher", "Kavita k", "Kavita Khana", "timetable") in {
        (x["kind"], x["text"], x["meaning"], x["source"]) for x in items}
    p = _preview(client, sid, h)
    assert "teacher:Kavita k" not in {q["id"] for q in p["questions"]}
    assert p["plan"]["people"]["Kavita k"]["match"] == "Kavita Khana"


def test_rules_read_the_schools_short_forms():
    forms = {"teacher": {"beaul": "Beula Rao"}, "subject": {"ssc": "Social Science"}}
    hints = sentence_hints("BEAUL takes S.Sc only in the morning", ["Beula Rao"], ["Social Science"], [], forms)
    assert "'BEAUL' = Beula Rao (the school's own short form)" in hints
    assert "'S.Sc' = Social Science (the school's own short form)" in hints
    assert typed_short_forms("No S. Sc. for BEAUL on Monday", forms) == {
        "social science": "S. Sc.", "beula rao": "BEAUL"}


def test_a_rule_using_a_known_short_form_is_saved_without_asking():
    from app.routers.constraints import _plainly_read
    from app.services.constraint_ir import rule_from_dict

    rule = rule_from_dict({"form": "count", "scope": [], "relation": "==", "value": 0,
                           "selector": {"teachers": ["Beula Rao"], "days": [4]}})
    forms = {"teacher": {"beaul": "Beula Rao"}}
    assert not _plainly_read(rule, "BEAUL is off on Fridays")
    assert _plainly_read(rule, "BEAUL is off on Fridays", forms)

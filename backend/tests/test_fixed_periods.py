"""A subject held at the same period every day for some grades only - the
class teacher period in period 8 for Grades 1 to 5 - taught and counted like
any other lesson."""
from app.models.school import Period, School, Teacher
from app.services.solver import generate_school_timetable
from app.services.timetable_structure import lesson_numbers
from tests.conftest import create_school, signup
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def test_the_subject_goes_only_in_its_period_and_only_for_those_grades(db):  # noqa: F811
    school = _school(db, days=3, per_day=3)
    ct = _subject(db, school, "Class Teacher Period")
    eng = _subject(db, school, "English")
    persis = _teacher(db, school, "Persis", [ct.id, eng.id])
    _teacher(db, school, "Rao", [eng.id])
    young = _class_group(db, school, grade="Grade 1", name="A")
    old = _class_group(db, school, grade="Grade 6", name="A")
    _require(db, young, ct, 3)
    _require(db, young, eng, 6)
    _require(db, old, eng, 9)
    row = db.get(School, school.id)
    row.fixed_periods = [{"subject_id": ct.id, "grades": ["Grade 1"], "period": 3, "days": None}]
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    numbers = lesson_numbers(db.query(Period).filter(Period.school_id == school.id).all())
    young_ct = {numbers[a["period_id"]] for a in result.assignments
                if a["class_group_id"] == young.id and a["subject_id"] == ct.id}
    young_other = {numbers[a["period_id"]] for a in result.assignments
                   if a["class_group_id"] == young.id and a["subject_id"] != ct.id}
    assert young_ct == {3} and 3 not in young_other
    # Grade 6 has ordinary lessons in period 3.
    assert 3 in {numbers[a["period_id"]] for a in result.assignments if a["class_group_id"] == old.id}
    # Persis teaches the class teacher periods - real lessons, in her week.
    assert sum(1 for a in result.assignments if a["teacher_id"] == persis.id and a["subject_id"] == ct.id) == 3


def test_the_setting_is_validated(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.put(f"/api/schools/{sid}/timetable-structure", headers=h, json={"days": [0, 1], "periods_per_day": 9})
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 1", "name": "A"}, headers=h)
    subject = client.post("/api/subjects", json={"school_id": sid, "name": "C.T"}, headers=h).json()
    url = f"/api/schools/{sid}/fixed-periods"

    bad = client.put(url, headers=h, json={"rules": [{"subject_id": subject["id"], "grades": ["Grade 1"], "period": 12}]})
    assert bad.status_code == 400 and "1 to 9" in bad.json()["detail"]
    bad = client.put(url, headers=h, json={"rules": [{"subject_id": subject["id"], "grades": ["Grade 7"], "period": 8}]})
    assert bad.status_code == 400 and "no Grade 7" in bad.json()["detail"]
    twice = {"subject_id": subject["id"], "grades": ["Grade 1"], "period": 8}
    bad = client.put(url, headers=h, json={"rules": [twice, twice]})
    assert bad.status_code == 400 and "already has something fixed" in bad.json()["detail"]

    ok = client.put(url, headers=h, json={"rules": [twice]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["fixed_periods"] == [{"subject_id": subject["id"], "grades": ["Grade 1"], "period": 8, "days": None}]
    assert client.put(url, headers=h, json={"rules": []}).json()["fixed_periods"] is None


def test_the_setup_check_says_when_the_periods_dont_match(db):  # noqa: F811
    from app.services.setup_check import check_setup
    school = _school(db, days=3, per_day=3)
    ct = _subject(db, school, "C.T")
    _teacher(db, school, "Persis", [ct.id])
    young = _class_group(db, school, grade="Grade 1", name="A")
    _require(db, young, ct, 5)  # fixed to 3 slots a week
    row = db.get(School, school.id)
    row.fixed_periods = [{"subject_id": ct.id, "grades": ["Grade 1"], "period": 2, "days": None}]
    db.commit()
    hit = [i for i in check_setup(db, school.id)["errors"] if i["kind"] == "fixed_period_count"]
    assert hit and "fixed to 3 periods a week" in hit[0]["message"]

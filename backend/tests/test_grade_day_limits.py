"""Some grades have a shorter school day (Grades 1 and 2 home after period 6)."""
from app.models.school import Period, School
from app.services.solver import generate_school_timetable
from app.services.timetable_structure import lesson_numbers
from tests.conftest import create_school, signup
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def _limit(db, school, **rule):  # noqa: F811
    row = db.get(School, school.id)
    row.grade_day_limits = [rule]
    db.commit()


def test_a_short_grade_is_never_timetabled_after_its_last_period(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    eng = _subject(db, school, "English")
    _teacher(db, school, "Rao", [eng.id])
    young = _class_group(db, school, grade="Grade 1", name="A")
    _require(db, young, eng, 4)  # exactly fits 2 days x 2 periods
    _limit(db, school, grades=["Grade 1"], periods_per_day=2)

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    numbers = lesson_numbers(db.query(Period).filter(Period.school_id == school.id).all())
    assert {numbers[a["period_id"]] for a in result.assignments} <= {1, 2}


def test_a_day_off_for_a_grade(db):  # noqa: F811
    school = _school(db, days=2, per_day=3)
    eng = _subject(db, school, "English")
    _teacher(db, school, "Rao", [eng.id])
    young = _class_group(db, school, grade="Grade 1", name="A")
    _require(db, young, eng, 3)
    _limit(db, school, grades=["Grade 1"], periods_per_day=3, by_day={"1": 0})  # no school on day 1

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    days = {db.get(Period, a["period_id"]).day_of_week for a in result.assignments}
    assert days == {0}


def test_too_many_periods_for_the_shorter_week_is_explained(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    eng = _subject(db, school, "English")
    _teacher(db, school, "Rao", [eng.id])
    _require(db, _class_group(db, school, grade="Grade 1", name="A"), eng, 6)
    _limit(db, school, grades=["Grade 1"], periods_per_day=2)

    result = generate_school_timetable(db, school.id)
    assert result.status not in ("optimal", "feasible")
    assert any("only has 4 periods in its week" in e for e in result.errors), result.errors


def test_the_setting_is_validated_and_shown_on_periods(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    client.put(f"/api/schools/{sid}/timetable-structure", headers=h, json={"days": [0, 1], "periods_per_day": 4})
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 1", "name": "A"}, headers=h)
    url = f"/api/schools/{sid}/grade-day-limits"

    bad = client.put(url, headers=h, json={"limits": [{"grades": ["Grade 9"], "periods_per_day": 2}]})
    assert bad.status_code == 400 and "no Grade 9" in bad.json()["detail"]

    ok = client.put(url, headers=h, json={"limits": [{"grades": ["Grade 1"], "periods_per_day": 2}]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["grade_day_limits"] == [{"grades": ["Grade 1"], "periods_per_day": 2, "by_day": {}}]

    periods = client.get(f"/api/periods?school_id={sid}", headers=h).json()
    assert len(periods) == 8, periods
    late = [p for p in periods if p["number"] > 2]
    assert len(late) == 4 and all(p["off_grades"] == ["Grade 1"] for p in late)
    assert all(p["off_grades"] == [] for p in periods if p["number"] <= 2)

    cleared = client.put(url, headers=h, json={"limits": []})
    assert cleared.json()["grade_day_limits"] is None

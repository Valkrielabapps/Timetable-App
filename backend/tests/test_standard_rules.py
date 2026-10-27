"""The tick-box rules on the Constraints page.

  - No teacher over N periods a week (their own limit, if set, wins).
  - No teacher over N periods a day.
  - Spread each teacher's periods over the day and the week.
"""
from collections import Counter

from app.models.school import Period, School
from app.services import standard_rules
from app.services.solver import find_blocking_rules, generate_school_timetable
from tests.conftest import create_school, signup
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def _tick(db, school, **rules):
    row = db.get(School, school.id)
    row.standard_rules = rules
    db.commit()


def _ok(result):
    assert result.status in ("optimal", "feasible"), result.errors


def _per_day(db, result, teacher):
    return Counter(db.get(Period, a["period_id"]).day_of_week for a in result.assignments
                   if a["teacher_id"] == teacher.id)


# --- the setting itself ---------------------------------------------------

def test_defaults_leave_the_caps_off_and_spreading_on():
    rules = standard_rules.for_school(None)
    assert (rules.week_max, rules.day_max, rules.spread) == (None, None, True)
    shown = standard_rules.merged(None)
    assert shown["teacher_week_max"] == {"on": False, "value": 30}
    assert shown["teacher_day_max"] == {"on": False, "value": 6}


def test_only_changes_are_stored():
    assert standard_rules.to_store(standard_rules.merged(None)) is None
    stored = standard_rules.to_store({"teacher_day_max": {"on": True, "value": 6}})
    assert stored == {"teacher_day_max": {"on": True, "value": 6}}


def test_the_api_ticks_and_validates(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    url = f"/api/schools/{sid}/standard-rules"

    bad = client.put(url, headers=h, json={"teacher_day_max": {"on": True, "value": 40}})
    assert bad.status_code == 400 and "between 1 and 16" in bad.json()["detail"]

    ok = client.put(url, headers=h, json={"teacher_week_max": {"on": True}, "teacher_spread": {"on": False}})
    assert ok.status_code == 200, ok.text
    rules = ok.json()["standard_rules"]
    assert rules["teacher_week_max"] == {"on": True, "value": 30}
    assert rules["teacher_spread"] == {"on": False}
    assert rules["teacher_day_max"] == {"on": False, "value": 6}

    again = client.get(f"/api/schools/{sid}", headers=h).json()
    assert again["standard_rules"] == rules


# --- in the solver ----------------------------------------------------------

def test_the_daily_cap_is_kept(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    maths = _subject(db, school, "Maths")
    rao = _teacher(db, school, "Rao", [maths.id])
    for name in "ABCD":
        _require(db, _class_group(db, school, name=name), maths, 1)
    _tick(db, school, teacher_day_max={"on": True, "value": 2}, teacher_spread={"on": False})

    result = generate_school_timetable(db, school.id)
    _ok(result)
    assert max(_per_day(db, result, rao).values()) <= 2


def test_a_daily_cap_that_cant_be_met_is_explained(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, _class_group(db, school), maths, 3)
    _tick(db, school, teacher_day_max={"on": True, "value": 1})

    assert generate_school_timetable(db, school.id).status not in ("optimal", "feasible")
    reasons = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=10)
    assert any("more than 1 periods in a day" in r for r in reasons), reasons


def test_the_weekly_cap_applies_to_everyone_without_their_own(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, _class_group(db, school, name="A"), maths, 3)
    _require(db, _class_group(db, school, name="B"), maths, 3)
    _tick(db, school, teacher_week_max={"on": True, "value": 5})

    result = generate_school_timetable(db, school.id)
    assert result.status not in ("optimal", "feasible")
    assert any("Rao" in e for e in result.errors), result.errors


def test_a_teachers_own_limit_wins_over_the_schools(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    maths = _subject(db, school, "Maths")
    rao = _teacher(db, school, "Rao", [maths.id])
    rao.max_periods_per_week = 6
    db.commit()
    _require(db, _class_group(db, school, name="A"), maths, 3)
    _require(db, _class_group(db, school, name="B"), maths, 3)
    _tick(db, school, teacher_week_max={"on": True, "value": 5})

    _ok(generate_school_timetable(db, school.id))


def test_a_teachers_week_is_spread_evenly(db):  # noqa: F811
    school = _school(db, days=2, per_day=4)
    maths = _subject(db, school, "Maths")
    rao = _teacher(db, school, "Rao", [maths.id])
    for name in "ABCD":
        _require(db, _class_group(db, school, name=name), maths, 1)

    result = generate_school_timetable(db, school.id)
    _ok(result)
    assert sorted(_per_day(db, result, rao).values()) == [2, 2]


def test_a_teachers_day_avoids_back_to_back(db):  # noqa: F811
    school = _school(db, days=1, per_day=4)
    maths = _subject(db, school, "Maths")
    rao = _teacher(db, school, "Rao", [maths.id])
    _require(db, _class_group(db, school, name="A"), maths, 1)
    _require(db, _class_group(db, school, name="B"), maths, 1)

    result = generate_school_timetable(db, school.id)
    _ok(result)
    orders = sorted(db.get(Period, a["period_id"]).order for a in result.assignments if a["teacher_id"] == rao.id)
    assert orders[1] - orders[0] > 1, orders

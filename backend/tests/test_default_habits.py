"""Built-in habits every school gets without typing a rule.

1. A subject's lessons spread across the week rather than bunching.
2. Teachers aren't taught three periods running.

Both are preferences: they shape the answer, never cost the school its
timetable, and give way to any rule the school states.
"""
from collections import Counter

from app.models.school import Period
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _ir, _require, _school, _subject, _teacher, db  # noqa: F401


def _day(db, a):
    return db.get(Period, a["period_id"]).day_of_week


def test_a_subject_is_spread_across_the_week(db):  # noqa: F811
    school = _school(db, days=3, per_day=4)
    maths = _subject(db, school, "Maths")
    eng = _subject(db, school, "English")
    _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [eng.id])
    a = _class_group(db, school)
    _require(db, a, maths, 3)
    _require(db, a, eng, 3)

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    per_day = Counter((x["subject_id"], _day(db, x)) for x in result.assignments)
    assert set(per_day.values()) == {1}, per_day  # one Maths and one English every day


def test_a_teacher_is_not_taught_solid(db):  # noqa: F811
    school = _school(db, days=1, per_day=4)
    maths = _subject(db, school, "Maths")
    eng = _subject(db, school, "English")
    rao = _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [eng.id])
    a = _class_group(db, school)
    _require(db, a, maths, 3)
    _require(db, a, eng, 1)

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    orders = sorted(db.get(Period, x["period_id"]).order for x in result.assignments if x["teacher_id"] == rao.id)
    assert orders not in ([1, 2, 3], [2, 3, 4]), orders


def test_a_stated_rule_wins_over_the_habit(db):  # noqa: F811
    """The school wants all three Maths on Monday: the habit gives way."""
    school = _school(db, days=3, per_day=4)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    a = _class_group(db, school)
    _require(db, a, maths, 3)
    _ir(db, school, {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "days": [0]},
                     "relation": ">=", "value": 3}, description="All Maths on Monday")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert {_day(db, x) for x in result.assignments} == {0}


def test_a_try_to_rule_is_still_applied_after_the_first_timetable(db):  # noqa: F811
    """Preferences now join after a valid timetable is found; they must still count."""
    school = _school(db, days=2, per_day=3)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    a = _class_group(db, school)
    _require(db, a, maths, 2)
    _ir(db, school, {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "days": [1]},
                     "relation": "==", "value": 0, "strength": "preference"}, description="Try to keep Maths off Tuesday")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    # Keeping Maths off Tuesday (worth 10 per lesson) beats spreading it (1).
    assert {_day(db, x) for x in result.assignments} == {0}

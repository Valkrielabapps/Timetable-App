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


def _one_a_day_school(db, maths_per_week):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    maths = _subject(db, school, "Maths")
    fill = _subject(db, school, "Activity")
    _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [fill.id])
    a = _class_group(db, school)
    _require(db, a, maths, maths_per_week)
    _require(db, a, fill, 20 - maths_per_week)
    return school, maths


def _maths_per_day(db, result, maths):
    return Counter(_day(db, x) for x in result.assignments if x["subject_id"] == maths.id)


def test_one_period_of_a_subject_a_day_unless_the_week_needs_more(db):  # noqa: F811
    """The tick box, on by default: 5 Maths over 5 days is one a day, and 6 or
    7 over 5 days gives only the extra ones a second period - not two a day
    on three days, which the old fair-share spreading allowed."""
    for per_week, days_with_two in ((5, 0), (6, 1), (7, 2)):
        db.rollback()
        school, maths = _one_a_day_school(db, per_week)
        result = generate_school_timetable(db, school.id)
        assert result.status in ("optimal", "feasible"), result.errors
        counts = _maths_per_day(db, result, maths)
        assert max(counts.values()) <= 2 and sum(1 for n in counts.values() if n == 2) == days_with_two, counts


def test_one_a_day_can_be_unticked(db):  # noqa: F811
    from app.models.school import School
    from app.services import standard_rules
    school, maths = _one_a_day_school(db, 6)
    db.get(School, school.id).standard_rules = standard_rules.to_store({"subject_spread": {"on": False}})
    db.commit()
    assert standard_rules.for_school(db.get(School, school.id)).subject_spread is False
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors


def test_one_a_day_is_firm_when_the_week_has_room(db):  # noqa: F811
    """With no time to weigh preferences at all, 5 Maths over 5 days is still
    one a day: the tick box is a rule there, not a preference."""
    from app.services import solver
    school, maths = _one_a_day_school(db, 5)
    token = solver._DEFAULT_HABITS.set(False)
    try:
        for _ in range(3):
            result = generate_school_timetable(db, school.id)
            assert result.status in ("optimal", "feasible"), result.errors
            assert max(_maths_per_day(db, result, maths).values()) == 1
    finally:
        solver._DEFAULT_HABITS.reset(token)


def test_a_double_period_rule_for_one_section_leaves_the_others_one_a_day(db):  # noqa: F811
    """Grade 8 - A's Maths as a double: two on one day there, as asked. Grade
    8 - B's Maths isn't named, so it stays one a day."""
    school = _school(db, days=5, per_day=4)
    maths = _subject(db, school, "Maths")
    fill = _subject(db, school, "Activity")
    _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [fill.id])
    _teacher(db, school, "Das", [fill.id])
    a = _class_group(db, school, name="A")
    b = _class_group(db, school, name="B")
    for cg in (a, b):
        _require(db, cg, maths, 4)
        _require(db, cg, fill, 16)
    _ir(db, school, {"form": "run", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "class_groups": ["Grade 8 - A"]},
                     "block_size": 2, "blocks": 1, "blocks_relation": "=="}, description="Grade 8 - A has a double Maths")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    per_day = {cg.id: Counter(_day(db, x) for x in result.assignments
                              if x["subject_id"] == maths.id and x["class_group_id"] == cg.id) for cg in (a, b)}
    assert max(per_day[a.id].values()) == 2, per_day
    assert max(per_day[b.id].values()) == 1, per_day


def test_when_one_a_day_would_make_it_impossible_it_gives_way_and_says_so(db):  # noqa: F811
    """Rao takes Maths in both sections and is free only in period 1 on
    Tuesday, so one section needs two Maths on Monday. Firm, the tick box
    would leave the school with no timetable; instead it gives way there and
    the notes say so."""
    from app.models.school import Teacher
    from app.services.solver import _ONE_A_DAY_GAVE_WAY
    school = _school(db, days=2, per_day=3)
    maths = _subject(db, school, "Maths")
    fill = _subject(db, school, "Activity")
    rao = _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [fill.id])
    _teacher(db, school, "Das", [fill.id])
    a = _class_group(db, school, name="A")
    b = _class_group(db, school, name="B")
    for cg in (a, b):
        _require(db, cg, maths, 2)
        _require(db, cg, fill, 4)
    periods = db.query(Period).filter(Period.school_id == school.id).all()
    db.get(Teacher, rao.id).unavailable_period_ids = [p.id for p in periods if p.day_of_week == 1 and p.order > 1]
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert _ONE_A_DAY_GAVE_WAY in result.warnings
    monday = Counter(x["class_group_id"] for x in result.assignments if x["subject_id"] == maths.id and _day(db, x) == 0)
    assert sorted(monday.values()) == [1, 2]


def test_a_school_that_fits_one_a_day_gets_no_such_note(db):  # noqa: F811
    from app.services.solver import _ONE_A_DAY_GAVE_WAY
    school, _maths = _one_a_day_school(db, 5)
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible") and _ONE_A_DAY_GAVE_WAY not in result.warnings


def test_a_teacher_kept_off_days_by_a_rule_still_gets_a_timetable(db):  # noqa: F811
    """Rao's 3 Maths, and a rule keeping Rao off three of five days: one a day
    can't hold, and the generator knows not to insist - no second solve."""
    from app.services.solver import _ONE_A_DAY_GAVE_WAY
    school, maths = _one_a_day_school(db, 3)
    _ir(db, school, {"form": "count", "scope": [], "selector": {"teachers": ["Rao"], "days": [2, 3, 4]},
                     "relation": "==", "value": 0}, description="Rao has no periods on Wednesday, Thursday or Friday")
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert _ONE_A_DAY_GAVE_WAY not in result.warnings
    assert set(_maths_per_day(db, result, maths)) <= {0, 1}

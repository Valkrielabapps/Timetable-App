"""
The solver and the rule checks against the new day: non-lesson slots, zero
periods kept free per grade, and "period N" meaning the Nth lesson.

Every test pins the timetable down far enough that the only way it can come
out is the way being asserted - a test that passes because the solver
happened to choose well proves nothing.
"""
import pytest

from app.models.school import (
    ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher,
)
from app.routers.timetables import _orders_by_day
from app.schemas.timetable_structure import TimetableStructure
from app.services.solver import generate_school_timetable
from app.services.timetable_structure import apply, lesson_numbers


@pytest.fixture
def world(orm_db):
    school = School(name="Test School")
    orm_db.add(school)
    orm_db.commit()
    six = ClassGroup(school_id=school.id, grade="Grade 6", name="A")
    seven = ClassGroup(school_id=school.id, grade="Grade 7", name="A")
    maths = Subject(school_id=school.id, name="Maths")
    english = Subject(school_id=school.id, name="English")
    orm_db.add_all([six, seven, maths, english])
    orm_db.commit()
    rao = Teacher(school_id=school.id, name="Mrs. Rao", qualified_subject_ids=[maths.id])
    khan = Teacher(school_id=school.id, name="Mr. Khan", qualified_subject_ids=[english.id])
    orm_db.add_all([rao, khan])
    orm_db.commit()
    return {"db": orm_db, "school": school, "six": six, "seven": seven, "maths": maths, "english": english}


def structure(w, **kw):
    apply(w["db"], w["school"].id, TimetableStructure(**{"days": [0], **kw}))


def need(w, section, subject, n):
    w["db"].add(SubjectRequirement(class_group_id=w[section].id, subject_id=w[subject].id, periods_per_week=n))
    w["db"].commit()


def placed(w, result, section):
    """Lesson numbers a section was given, sorted."""
    periods = w["db"].query(Period).filter(Period.school_id == w["school"].id).all()
    numbers = lesson_numbers(periods)
    return sorted(numbers[a["period_id"]] for a in result.assignments if a["class_group_id"] == w[section].id)


def test_nothing_is_placed_in_the_class_teacher_period(world):
    """Three lessons, a class teacher period and three subjects' worth of
    need: every lesson slot is used, and the class teacher period isn't."""
    structure(world, periods_per_day=3, class_teacher_period={"enabled": True})
    need(world, "six", "maths", 3)
    result = generate_school_timetable(world["db"], world["school"].id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert placed(world, result, "six") == [1, 2, 3]
    ct = world["db"].query(Period).filter(Period.kind == "class_teacher").one()
    assert all(a["period_id"] != ct.id for a in result.assignments)


def test_the_class_teacher_period_is_not_extra_room(world):
    structure(world, periods_per_day=3, class_teacher_period={"enabled": True})
    need(world, "six", "maths", 4)
    assert generate_school_timetable(world["db"], world["school"].id).status not in ("optimal", "feasible")


def test_a_grades_zero_period_is_kept_free_for_it_alone(world):
    """Two periods and a zero period for Grade 6 make three numbered slots.
    Grade 6 needs two and must skip the first; Grade 7 needs all three, so
    it is taught in Grade 6's zero period."""
    structure(world, periods_per_day=2, zero_period={
        "enabled": True, "scope": "grade", "placements": [{"grade": "Grade 6", "every_day": 1}]})
    need(world, "six", "maths", 2)
    need(world, "seven", "english", 3)
    result = generate_school_timetable(world["db"], world["school"].id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert placed(world, result, "six") == [2, 3]
    assert placed(world, result, "seven") == [1, 2, 3]


def test_a_grade_cannot_be_given_more_than_its_periods(world):
    structure(world, periods_per_day=2, zero_period={
        "enabled": True, "scope": "grade", "placements": [{"grade": "Grade 6", "every_day": 1}]})
    need(world, "six", "maths", 3)
    assert generate_school_timetable(world["db"], world["school"].id).status not in ("optimal", "feasible")


def test_a_whole_school_zero_period_is_free_for_everyone(world):
    structure(world, periods_per_day=2, zero_period={
        "enabled": True, "scope": "school", "placements": [{"by_day": {0: 2}}]})
    need(world, "six", "maths", 2)
    need(world, "seven", "english", 2)
    result = generate_school_timetable(world["db"], world["school"].id)
    assert placed(world, result, "six") == [1, 3]
    assert placed(world, result, "seven") == [1, 3]


def _rule(w, number):
    w["db"].add(Constraint(school_id=w["school"].id, type="ir", description=f"No Maths in period {number}.",
                           parameters={"form": "count", "scope": ["class_group"],
                                       "selector": {"subjects": ["Maths"], "period_orders": [number]},
                                       "relation": "==", "value": 0, "strength": "required"}))
    w["db"].commit()


def test_period_1_is_the_first_lesson_after_the_class_teacher_period(world):
    """Two lessons after a class teacher period, Maths in one of them and
    banned from period 1: it can only be period 2 - if period 1 meant the
    class teacher row, the ban would bite nothing and either would do."""
    structure(world, periods_per_day=2, class_teacher_period={"enabled": True})
    need(world, "six", "maths", 1)
    need(world, "six", "english", 1)
    _rule(world, 1)
    result = generate_school_timetable(world["db"], world["school"].id)
    maths = [a for a in result.assignments if a["subject_id"] == world["maths"].id]
    periods = {p.id: p for p in world["db"].query(Period).all()}
    assert lesson_numbers(periods.values())[maths[0]["period_id"]] == 2


def test_period_numbers_skip_breaks(world):
    """Lunch after period 1: "period 2" is the lesson after lunch, not lunch."""
    structure(world, periods_per_day=2, breaks=[{"after": 1, "label": "Lunch"}])
    need(world, "six", "maths", 1)
    need(world, "six", "english", 1)
    _rule(world, 2)
    result = generate_school_timetable(world["db"], world["school"].id)
    maths = [a for a in result.assignments if a["subject_id"] == world["maths"].id]
    periods = {p.id: p for p in world["db"].query(Period).all()}
    assert lesson_numbers(periods.values())[maths[0]["period_id"]] == 1


def test_the_rule_check_counts_the_same_way(world):
    """The check that flags manual edits must agree with the solver about
    what "period 5" is, or a move gets flagged for a rule it doesn't break."""
    structure(world, periods_per_day=3, breaks=[{"after": 1}], class_teacher_period={"enabled": True})
    periods = world["db"].query(Period).all()
    lessons = sorted((p for p in periods if p.kind == "lesson"), key=lambda p: p.order)
    assert _orders_by_day(periods) == {0: [p.order for p in lessons]}

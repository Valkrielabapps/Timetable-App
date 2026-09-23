"""
Tests for soft constraints (is_hard=False).

The distinction worth proving: a hard rule makes a timetable that breaks it
infeasible; a soft one makes it *expensive*, so the solver honours it when
it can and produces a timetable anyway when it can't. Before this, is_hard
and weight existed on the model and the solver read neither - every
preference was silently dropped.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import (
    ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher,
)
from app.models.user import User  # noqa: F401 - registers the users table
from app.services.solver import generate_school_timetable


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _school(db, days=1, per_day=4):
    school = School(name="Test School")
    db.add(school)
    db.commit()
    db.refresh(school)
    for day in range(days):
        for order in range(1, per_day + 1):
            db.add(Period(school_id=school.id, day_of_week=day, order=order))
    db.commit()
    return school


def _subject_with_requirement(db, school, name, periods_per_week):
    subject = Subject(school_id=school.id, name=name)
    db.add(subject)
    db.commit()
    db.refresh(subject)

    teacher = Teacher(school_id=school.id, name=f"T-{name}", qualified_subject_ids=[subject.id])
    db.add(teacher)
    cg = db.query(ClassGroup).filter(ClassGroup.school_id == school.id).first()
    if cg is None:
        cg = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
        db.add(cg)
    db.commit()
    db.refresh(cg)

    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subject.id, periods_per_week=periods_per_week))
    db.commit()
    return subject


def _last_period_id(db, school):
    return max(
        db.query(Period).filter(Period.school_id == school.id).all(), key=lambda p: p.order
    ).id


def test_a_soft_preference_is_honoured_when_it_can_be(db):
    """One lesson, four slots, "not the last period" - easily satisfied."""
    school = _school(db, days=1, per_day=4)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=1)
    db.add(Constraint(
        school_id=school.id,
        type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=False,
        weight=5,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert result.assignments[0]["period_id"] != _last_period_id(db, school)


def test_a_soft_preference_yields_rather_than_making_it_infeasible(db):
    """Four lessons into four slots: the last period MUST be used. A hard
    rule would make this unsolvable; a preference must bend instead."""
    school = _school(db, days=1, per_day=4)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=4)
    db.add(Constraint(
        school_id=school.id,
        type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=False,
        weight=5,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 4


def test_the_same_rule_as_hard_is_infeasible(db):
    """The control for the test above - proving the difference is is_hard
    and not something incidental about the setup."""
    school = _school(db, days=1, per_day=4)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=4)
    db.add(Constraint(
        school_id=school.id,
        type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=True,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status == "infeasible"


def test_a_heavier_preference_wins_over_a_lighter_one(db):
    """Two lessons, two slots, both discouraged - the solver should take the
    cheaper violation, which is what makes weight mean anything."""
    school = _school(db, days=1, per_day=2)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=1)
    periods = sorted(
        db.query(Period).filter(Period.school_id == school.id).all(), key=lambda p: p.order
    )
    # Strongly avoid the first period, mildly avoid the last.
    db.add(Constraint(
        school_id=school.id, type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "first"},
        is_hard=False, weight=10,
    ))
    db.add(Constraint(
        school_id=school.id, type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=False, weight=1,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert result.assignments[0]["period_id"] == periods[-1].id, (
        "solver took the heavily-penalised slot over the lightly-penalised one"
    )


def test_a_soft_prefer_pulls_towards_the_wanted_slot(db):
    """"Prefer X in the first period" discourages everything else, which is
    the same statement from the other side."""
    school = _school(db, days=1, per_day=4)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=1)
    first_id = min(
        db.query(Period).filter(Period.school_id == school.id).all(), key=lambda p: p.order
    ).id
    db.add(Constraint(
        school_id=school.id, type="require_subject_period",
        parameters={"subject_id": subject.id, "position": "first"},
        is_hard=False, weight=5,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert result.assignments[0]["period_id"] == first_id


def test_hard_rules_alone_add_no_objective(db):
    """A school with only hard rules must keep the previous behaviour - no
    objective, so the solver stops at the first feasible answer."""
    school = _school(db, days=1, per_day=4)
    subject = _subject_with_requirement(db, school, "PE", periods_per_week=1)
    db.add(Constraint(
        school_id=school.id, type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=True,
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert result.assignments[0]["period_id"] != _last_period_id(db, school)

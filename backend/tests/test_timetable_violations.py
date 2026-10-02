"""
A timetable reports which of its own rules it breaks.

Reported from a real school, as a question: dragging a teacher into a period
her rule excludes double-books nobody, so every physical check passes and the
move is saved - while the Constraints tab goes on calling that rule enforced.
The timetable and the UI disagree and nothing says so.

Two properties matter here and they pull in opposite directions:

  - A manual move that breaks a rule is ALLOWED. Manual editing exists so a
    human can override; blocking would make people delete the rule instead,
    which is worse, because then nothing records what they wanted.
  - And it is REPORTED, with the rule's own sentence and the slots involved.

The third test is the one worth keeping longest: a freshly generated timetable
must break nothing. When it does, the solver and the checker disagree and one
of them is wrong - which has happened three times so far, each time silently.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import (
    ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher,
)
from app.models.user import User  # noqa: F401 - registers the users table
from app.routers.timetables import _to_timetable_out
from app.services.solver import generate_school_timetable
from app.models.school import Timetable, TimetableEntry


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _school_with_a_rule(db, periods_per_day=8, required=4):
    """One teacher barred from the last four periods, with exactly enough room
    in the first four - the shape of the reported case."""
    school = School(name="Test School")
    db.add(school)
    db.commit()
    db.refresh(school)
    # Numbered from zero, as a real school's are, and displayed as 1..8.
    for order in range(periods_per_day):
        db.add(Period(school_id=school.id, day_of_week=0, order=order))
    cg = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(cg)
    hindi = Subject(school_id=school.id, name="Hindi")
    db.add(hindi)
    db.commit()
    db.refresh(cg)
    db.refresh(hindi)
    db.add(Teacher(school_id=school.id, name="Mrs. Kamini Chandra",
                   qualified_subject_ids=[hindi.id]))
    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=hindi.id,
                              periods_per_week=required))
    db.add(Constraint(
        school_id=school.id, type="ir",
        parameters={"form": "count", "scope": [],
                    "selector": {"teachers": ["Mrs. Kamini Chandra"],
                                 "period_orders": [5, 6, 7, 8]},
                    "relation": "==", "value": 0, "strength": "required"},
        description="Mrs. Kamini Chandra has no periods in periods 5, 6, 7 or 8",
    ))
    db.commit()
    return school


def _generate(db, school):
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    timetable = Timetable(school_id=school.id, status="draft", solver_status=result.status)
    db.add(timetable)
    db.commit()
    db.refresh(timetable)
    for a in result.assignments:
        db.add(TimetableEntry(timetable_id=timetable.id, **a))
    db.commit()
    db.refresh(timetable)
    return timetable


def test_a_freshly_generated_timetable_breaks_nothing():
    """The standing cross-check. The solver was given these rules, so if the
    checker disagrees with it about a timetable nobody has touched, one of them
    is wrong - and that is how a min_gap no-op, a whole-day availability block
    and an off-by-one in period numbers each went unnoticed."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        school = _school_with_a_rule(session)
        timetable = _generate(session, school)
        out = _to_timetable_out(session, timetable)
        assert out.violations == [], [v.detail for v in out.violations]
    finally:
        session.close()


def test_moving_a_slot_into_a_barred_period_is_reported(db):
    school = _school_with_a_rule(db)
    timetable = _generate(db, school)
    assert _to_timetable_out(db, timetable).violations == []

    # Displayed Period 5, stored order 4 - the slot from the report.
    target = db.query(Period).filter(Period.school_id == school.id, Period.order == 4).one()
    moved = timetable.entries[0]
    moved.period_id = target.id
    db.commit()

    violations = _to_timetable_out(db, timetable).violations
    assert len(violations) == 1
    assert violations[0].description.startswith("Mrs. Kamini Chandra has no periods")
    assert violations[0].entry_ids == [moved.id]
    assert violations[0].strength == "required"


def test_the_report_says_what_went_wrong_in_numbers(db):
    """"This breaks a rule" without "1 period here, the rule says 0" leaves
    someone hunting for which slot to move."""
    school = _school_with_a_rule(db)
    timetable = _generate(db, school)
    target = db.query(Period).filter(Period.school_id == school.id, Period.order == 4).one()
    timetable.entries[0].period_id = target.id
    db.commit()

    detail = _to_timetable_out(db, timetable).violations[0].detail
    assert "1 period" in detail and "0" in detail


def test_moving_a_slot_somewhere_allowed_reports_nothing(db):
    """The warning has to stay quiet when nothing is wrong, or it becomes
    something people learn to scroll past."""
    school = _school_with_a_rule(db, periods_per_day=8, required=3)
    timetable = _generate(db, school)
    free = db.query(Period).filter(Period.school_id == school.id, Period.order == 3).one()
    timetable.entries[0].period_id = free.id
    db.commit()
    assert _to_timetable_out(db, timetable).violations == []


def test_the_move_itself_is_not_prevented(db):
    """Manual editing exists so a human can override. Blocking would make
    people delete the rule instead, and then nothing records what they
    wanted."""
    school = _school_with_a_rule(db)
    timetable = _generate(db, school)
    target = db.query(Period).filter(Period.school_id == school.id, Period.order == 4).one()
    timetable.entries[0].period_id = target.id
    db.commit()

    out = _to_timetable_out(db, timetable)
    assert any(e.period_id == target.id for e in out.entries), "the move must still stand"
    assert out.violations, "and still be reported"


def test_a_timetable_still_generating_reports_nothing(db):
    """Nothing to check, and the frontend polls this endpoint every 1.5s while
    a solve runs."""
    school = _school_with_a_rule(db)
    timetable = Timetable(school_id=school.id, status="generating")
    db.add(timetable)
    db.commit()
    db.refresh(timetable)
    assert _to_timetable_out(db, timetable).violations == []


def test_legacy_constraints_are_skipped_rather_than_claimed_satisfied(db):
    """The nine named types have no checker. Reporting them as honoured would
    be a claim this cannot make."""
    school = _school_with_a_rule(db)
    pe = Subject(school_id=school.id, name="PE")
    db.add(pe)
    db.commit()
    db.refresh(pe)
    db.add(Constraint(school_id=school.id, type="no_subject_period",
                      parameters={"subject_id": pe.id, "position": "last"},
                      description="No PE in the last period"))
    db.commit()

    timetable = _generate(db, school)
    # No crash, and nothing invented about the legacy rule either way.
    assert _to_timetable_out(db, timetable).violations == []

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher
from app.models.user import User  # noqa: F401 — registers the `users` table that School.owner_id FKs to
from app.services.solver import generate_school_timetable, solve_example


def test_solve_example_is_feasible():
    """The worked example has an obvious valid solution, so the solver
    should always find it — this test mainly catches OR-Tools install
    or API-usage regressions."""
    result = solve_example()
    assert result.status in ("optimal", "feasible")
    assert len(result.assignments) == 2  # Math + English, both scheduled


def test_solve_example_no_double_booking():
    result = solve_example()
    periods_used = [a["period"] for a in result.assignments]
    assert len(periods_used) == len(set(periods_used))


@pytest.fixture
def db_session():
    """A fresh in-memory SQLite DB per test, so these tests don't touch
    dev.db and don't leak state between each other. generate_school_
    timetable() only takes a Session + school_id, so a real (if
    throwaway) database is simpler than mocking the ORM query chain."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_school_with_periods(db, days=5, periods_per_day=2):
    """5 weekdays x periods_per_day periods, ordered 0..periods_per_day-1
    within each day — enough structure to exercise 'unavailable on a
    whole day' and 'last period of the day' constraints."""
    school = School(name="Test School")
    db.add(school)
    db.commit()
    db.refresh(school)
    for day in range(days):
        for order in range(periods_per_day):
            db.add(Period(school_id=school.id, day_of_week=day, order=order, label=f"D{day}P{order}"))
    db.commit()
    return school


def test_availability_constraint_is_respected(db_session):
    """A teacher marked unavailable on Monday (Teacher.unavailable_period_ids,
    set by the 'availability' constraint type — see
    app/routers/constraints.py) should never be scheduled on Monday, even
    though the requirement's periods_per_week leaves the solver free to
    pick from any of the 5 days."""
    db = db_session
    school = _make_school_with_periods(db, days=5, periods_per_day=2)

    subject = Subject(school_id=school.id, name="Math")
    db.add(subject)
    db.commit()
    db.refresh(subject)

    monday_period_ids = [
        p.id for p in db.query(Period).filter(Period.school_id == school.id, Period.day_of_week == 0).all()
    ]

    teacher = Teacher(
        school_id=school.id,
        name="Priya Sharma",
        qualified_subject_ids=[subject.id],
        unavailable_period_ids=monday_period_ids,
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)

    class_group = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(class_group)
    db.commit()
    db.refresh(class_group)

    # 3 periods/week out of 10 available slots — plenty of room to avoid
    # Monday entirely, so if the solver ever lands on Monday it's because
    # unavailable_period_ids was ignored, not because it had no choice.
    db.add(SubjectRequirement(class_group_id=class_group.id, subject_id=subject.id, periods_per_week=3))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 3
    scheduled_period_ids = {a["period_id"] for a in result.assignments}
    assert scheduled_period_ids.isdisjoint(monday_period_ids), (
        "Teacher was scheduled during a period they were marked unavailable for"
    )


def test_no_subject_last_period_constraint_is_respected(db_session):
    """A 'no_subject_period' Constraint row (position='last') should keep
    the subject off the last period of every day, school-wide — see the
    req_restricted_periods handling in app/services/solver.py."""
    db = db_session
    school = _make_school_with_periods(db, days=5, periods_per_day=2)

    subject = Subject(school_id=school.id, name="PE")
    db.add(subject)
    db.commit()
    db.refresh(subject)

    last_period_ids = {
        p.id
        for p in db.query(Period).filter(Period.school_id == school.id).all()
        if p.order == 1  # periods_per_day=2, so order 1 is the last slot of the day
    }

    teacher = Teacher(school_id=school.id, name="Coach Rao", qualified_subject_ids=[subject.id])
    db.add(teacher)
    db.commit()
    db.refresh(teacher)

    class_group = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(class_group)
    db.commit()
    db.refresh(class_group)

    db.add(SubjectRequirement(class_group_id=class_group.id, subject_id=subject.id, periods_per_week=3))
    db.add(Constraint(
        school_id=school.id,
        type="no_subject_period",
        parameters={"subject_id": subject.id, "position": "last"},
        is_hard=True,
        description="PE should not be scheduled in the last period of the day",
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 3
    scheduled_period_ids = {a["period_id"] for a in result.assignments}
    assert scheduled_period_ids.isdisjoint(last_period_ids), (
        "Subject was scheduled in the last period of the day despite a no_subject_period ban"
    )


def test_teacher_qualified_grades_is_respected(db_session):
    """A teacher whose Teacher.qualified_grades is non-empty should only be
    assignable to class groups whose grade is in that list — e.g. a Math
    teacher qualified only for 'Grade 9' should never be assigned to a
    'Grade 8' section's Math requirement, even if they're the only teacher
    qualified for the subject there (the solve should report infeasible /
    an explanatory error instead of silently assigning them anyway)."""
    db = db_session
    school = _make_school_with_periods(db, days=5, periods_per_day=2)

    subject = Subject(school_id=school.id, name="Math")
    db.add(subject)
    db.commit()
    db.refresh(subject)

    # Qualified for Math, but only in Grade 9 — should never be assigned to
    # the Grade 8 section below.
    teacher = Teacher(
        school_id=school.id,
        name="Priya Sharma",
        qualified_subject_ids=[subject.id],
        qualified_grades=["Grade 9"],
    )
    db.add(teacher)
    db.commit()
    db.refresh(teacher)

    grade_8 = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(grade_8)
    db.commit()
    db.refresh(grade_8)

    db.add(SubjectRequirement(class_group_id=grade_8.id, subject_id=subject.id, periods_per_week=2))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status == "infeasible"
    assert any("no qualified teacher" in e.lower() for e in result.errors), result.errors

    # Now add a second class group in Grade 9 — the same teacher should be
    # assignable there, proving the restriction is a match, not a blanket
    # exclusion of this teacher.
    grade_9 = ClassGroup(school_id=school.id, grade="Grade 9", name="A")
    db.add(grade_9)
    db.commit()
    db.refresh(grade_9)

    # Remove the unsatisfiable Grade 8 requirement so this second solve
    # isn't infeasible for the same reason as above.
    db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == grade_8.id).delete()
    db.add(SubjectRequirement(class_group_id=grade_9.id, subject_id=subject.id, periods_per_week=2))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 2
    assert all(a["teacher_id"] == teacher.id for a in result.assignments)


def test_assistant_teacher_is_not_double_booked(db_session):
    """SubjectRequirement.assistant_teacher_id reserves that teacher's time
    wherever the requirement lands — it shouldn't be possible for the
    solver to assign an assistant to co-teach one class while also using
    them as the sole primary teacher of a different class at the same
    period. See the assistant_teacher_id bullet in generate_school_
    timetable's docstring."""
    db = db_session
    # A single period in the whole school: Math (CG1) and English (CG2)
    # both need exactly that one period, so if the assistant reservation
    # isn't enforced, the solver has no reason at all to avoid landing them
    # both there — the conflict is unavoidable, not a matter of bad luck.
    school = _make_school_with_periods(db, days=1, periods_per_day=1)

    math = Subject(school_id=school.id, name="Math")
    english = Subject(school_id=school.id, name="English")
    db.add_all([math, english])
    db.commit()
    db.refresh(math)
    db.refresh(english)

    primary = Teacher(school_id=school.id, name="Mr. Rao", qualified_subject_ids=[math.id])
    assistant = Teacher(school_id=school.id, name="Ms. Iyer", qualified_subject_ids=[english.id])
    db.add_all([primary, assistant])
    db.commit()
    db.refresh(primary)
    db.refresh(assistant)

    cg1 = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    cg2 = ClassGroup(school_id=school.id, grade="Grade 8", name="B")
    db.add_all([cg1, cg2])
    db.commit()
    db.refresh(cg1)
    db.refresh(cg2)

    db.add(SubjectRequirement(
        class_group_id=cg1.id, subject_id=math.id, periods_per_week=1,
        assistant_teacher_id=assistant.id,
    ))
    db.add(SubjectRequirement(class_group_id=cg2.id, subject_id=english.id, periods_per_week=1))
    db.commit()

    # Only one period exists and both requirements need it — Ms. Iyer would
    # have to be in two places at once (assisting Math for CG1, teaching
    # English for CG2), which is genuinely impossible.
    result = generate_school_timetable(db, school.id)
    assert result.status == "infeasible", (
        "Expected the sole shared period to make this infeasible — the assistant "
        "reservation isn't being enforced if this solved anyway"
    )

    # Add a second period so the two requirements *can* be separated —
    # confirm the solver actually does separate them rather than still
    # double-booking Ms. Iyer.
    db.add(Period(school_id=school.id, day_of_week=0, order=1, label="D0P1"))
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 2

    math_entry = next(a for a in result.assignments if a["subject_id"] == math.id)
    english_entry = next(a for a in result.assignments if a["subject_id"] == english.id)
    assert math_entry["period_id"] != english_entry["period_id"], (
        "Ms. Iyer was scheduled to assist Math and teach English at the same period"
    )


def test_multi_constraint_conflict_is_named(db_session):
    """Two different subjects each individually-fine 'require first period'
    rules for the same class group, together impossible (a class group can
    only have one subject per period) — the exact scenario
    docs/ARCHITECTURE.md names as something _diagnose_infeasibility's
    single-cause checks can't see. _diagnose_constraint_conflicts should
    name both constraints specifically instead of falling back to the
    generic 'couldn't automatically identify the cause' message."""
    db = db_session
    school = _make_school_with_periods(db, days=1, periods_per_day=2)

    math = Subject(school_id=school.id, name="Math")
    pe = Subject(school_id=school.id, name="PE")
    db.add_all([math, pe])
    db.commit()
    db.refresh(math)
    db.refresh(pe)

    math_teacher = Teacher(school_id=school.id, name="Mr. Rao", qualified_subject_ids=[math.id])
    pe_teacher = Teacher(school_id=school.id, name="Coach Iyer", qualified_subject_ids=[pe.id])
    db.add_all([math_teacher, pe_teacher])
    db.commit()

    cg = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(cg)
    db.commit()
    db.refresh(cg)

    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=math.id, periods_per_week=1))
    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=pe.id, periods_per_week=1))
    db.add(Constraint(
        school_id=school.id, type="require_subject_period",
        parameters={"subject_id": math.id, "position": "first"}, is_hard=True,
        description="Math must be in the first period",
    ))
    db.add(Constraint(
        school_id=school.id, type="require_subject_period",
        parameters={"subject_id": pe.id, "position": "first"}, is_hard=True,
        description="PE must be in the first period",
    ))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status == "infeasible"
    assert len(result.errors) == 1
    message = result.errors[0]
    assert "Math must be in the first period" in message
    assert "PE must be in the first period" in message
    assert "can't all be satisfied together" in message


def test_break_periods_are_never_scheduled_into(db_session):
    """A period marked is_break exists in the day's ordering - so "the period
    after lunch" resolves - but nothing is ever taught in it."""
    db = db_session
    school = _make_school_with_periods(db, days=5, periods_per_day=4)

    # Make the 2nd period of every day a break.
    break_period_ids = []
    for period in db.query(Period).filter(Period.school_id == school.id, Period.order == 2).all():
        period.is_break = True
        period.label = "Lunch"
        break_period_ids.append(period.id)
    db.commit()

    subject = Subject(school_id=school.id, name="Math")
    db.add(subject)
    db.commit()
    db.refresh(subject)

    teacher = Teacher(school_id=school.id, name="Priya Sharma", qualified_subject_ids=[subject.id])
    db.add(teacher)
    db.commit()

    class_group = ClassGroup(school_id=school.id, grade="Grade 8", name="A")
    db.add(class_group)
    db.commit()
    db.refresh(class_group)

    db.add(SubjectRequirement(class_group_id=class_group.id, subject_id=subject.id, periods_per_week=5))
    db.commit()

    result = generate_school_timetable(db, school.id)

    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.assignments) == 5
    scheduled = {a["period_id"] for a in result.assignments}
    assert scheduled.isdisjoint(break_period_ids), "A lesson was scheduled during a break"


def test_a_school_of_only_breaks_reports_nothing_to_schedule(db_session):
    """Rather than looking like a school with no periods at all, which would
    send the admin to add periods they already have."""
    db = db_session
    school = _make_school_with_periods(db, days=1, periods_per_day=2)
    for period in db.query(Period).filter(Period.school_id == school.id).all():
        period.is_break = True
    db.commit()

    subject = Subject(school_id=school.id, name="Math")
    db.add(subject)
    db.commit()

    result = generate_school_timetable(db, school.id)
    assert result.status == "no_periods"
    assert any("break" in e.lower() for e in result.errors)

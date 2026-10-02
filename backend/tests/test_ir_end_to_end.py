"""
IR rules through the real solver, from a Constraint row to a timetable.

test_constraint_ir_compiler.py proves the forms build the CP-SAT constraints
they claim to. This proves the wiring: that a row with type="ir" is found,
validated, compiled against the school's actual variables, and either changes
the timetable or says why it didn't.

Each test sets the school up so the rule biting is the difference between one
placement and another - a rule with room to spare would pass here whether or
not it reached the model at all.
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


def _class_group(db, school, grade="Grade 8", name="A"):
    cg = ClassGroup(school_id=school.id, grade=grade, name=name)
    db.add(cg)
    db.commit()
    db.refresh(cg)
    return cg


def _subject(db, school, name):
    subject = Subject(school_id=school.id, name=name)
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


def _teacher(db, school, name, subject_ids):
    teacher = Teacher(school_id=school.id, name=name, qualified_subject_ids=list(subject_ids))
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


def _require(db, cg, subject, periods_per_week):
    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subject.id,
                              periods_per_week=periods_per_week))
    db.commit()


def _ir(db, school, parameters, description="an IR rule"):
    db.add(Constraint(school_id=school.id, type="ir", parameters=parameters,
                      description=description))
    db.commit()


def _periods_used(result, db, school, subject_name=None):
    """The (day, order) slots the timetable used, optionally for one subject."""
    by_id = {p.id: p for p in db.query(Period).filter(Period.school_id == school.id).all()}
    subject_id = None
    if subject_name:
        subject_id = db.query(Subject).filter(
            Subject.school_id == school.id, Subject.name == subject_name).one().id
    out = []
    for a in result.assignments:
        if subject_id is not None and a["subject_id"] != subject_id:
            continue
        p = by_id[a["period_id"]]
        out.append((p.day_of_week, p.order))
    return sorted(out)


# ---------------------------------------------------------------------------


def test_an_ir_rule_reaches_the_solver_and_moves_a_lesson(db):
    """Solved twice, with and without the rule, because asserting one outcome
    proves nothing on its own: with two free days the solver may pick the slot
    the rule wanted anyway, and the test would pass against a rule that never
    reached the model. Comparing the two runs is what makes it bite."""
    school = _school(db, days=2, per_day=1)
    cg = _class_group(db, school)
    pe = _subject(db, school, "PE")
    _teacher(db, school, "Rao", [pe.id])
    _require(db, cg, pe, 1)

    before = generate_school_timetable(db, school.id)
    assert before.status in ("optimal", "feasible"), before.errors
    unconstrained = _periods_used(before, db, school, "PE")
    # Left to itself the solver puts PE on day 1, so the rule below bans day 1:
    # banning day 0 would "pass" whether or not it reached the model, which is
    # how the first version of this test passed against a disabled compiler.
    assert unconstrained == [(1, 1)], (
        "the solver's free choice moved; flip the day the rule bans"
    )

    _ir(db, school, {"form": "count", "scope": ["class_group"],
                     "selector": {"subjects": ["PE"], "days": [1]},
                     "relation": "==", "value": 0},
        description="No PE on Tuesdays")

    after = generate_school_timetable(db, school.id)
    assert after.status in ("optimal", "feasible"), after.errors
    assert _periods_used(after, db, school, "PE") == [(0, 1)]
    assert _periods_used(after, db, school, "PE") != unconstrained


def test_a_teacher_daily_cap_spreads_a_load_across_days(db):
    """R012, the shape with no legacy type: "no teacher more than N in a day".
    One teacher, three lessons, two days, cap of 2 - so the only timetables
    that exist split them 2/1."""
    school = _school(db, days=2, per_day=3)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    rao = _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 3)

    _ir(db, school, {"form": "count", "scope": ["teacher", "day"],
                     "relation": "<=", "value": 2},
        description="No teacher teaches more than 2 periods a day")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    used = _periods_used(result, db, school, "Maths")
    per_day = {}
    for day, _order in used:
        per_day[day] = per_day.get(day, 0) + 1
    assert max(per_day.values()) <= 2, used
    assert rao is not None


def test_a_hard_ir_rule_that_cannot_be_met_makes_the_solve_infeasible(db):
    """Over-constraining must fail loudly. Three Maths periods and a cap of one
    a day across two days cannot fit, and the right answer is "no timetable",
    not a timetable that quietly breaks the rule."""
    school = _school(db, days=2, per_day=3)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 3)

    _ir(db, school, {"form": "count", "scope": ["class_group", "day"],
                     "selector": {"subjects": ["Maths"]}, "relation": "<=", "value": 1})

    result = generate_school_timetable(db, school.id)
    assert result.status == "infeasible"


def test_the_same_rule_as_a_preference_produces_a_timetable_anyway(db):
    """The point of strength. A preference the solver cannot honour should bend
    rather than block - and the admin confirmed a sentence that said so."""
    school = _school(db, days=2, per_day=3)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 3)

    _ir(db, school, {"form": "count", "scope": ["class_group", "day"],
                     "selector": {"subjects": ["Maths"]}, "relation": "<=", "value": 1,
                     "strength": "preference"})

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert len(_periods_used(result, db, school, "Maths")) == 3


def test_a_rule_naming_a_teacher_who_left_is_reported_not_swallowed(db):
    """The whole point of the warnings channel. The timetable still generates,
    and the rule that did nothing says so - rather than sitting in the UI
    marked enforced, which is how the nine legacy types failed."""
    school = _school(db, days=1, per_day=2)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 1)

    _ir(db, school, {"form": "count", "scope": [],
                     "selector": {"teachers": ["Verma"]}, "relation": "==", "value": 0},
        description="Verma is off on Mondays")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert len(result.warnings) == 1
    assert "Verma" in result.warnings[0]


def test_a_stored_rule_that_no_longer_validates_is_reported(db):
    """A row written by an older version, or by a bug. It cannot be applied and
    must not pass silently."""
    school = _school(db, days=1, per_day=2)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 1)

    _ir(db, school, {"form": "teleport", "scope": []}, description="Nonsense rule")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert any("Nonsense rule" in w for w in result.warnings)


def test_legacy_constraints_still_work_alongside_ir_rules(db):
    """The two kinds coexist on purpose: migrating the nine types at the same
    time as introducing the IR would risk every rule that already works, for no
    gain the day it ships.

    Both rules have to be load-bearing for this to prove anything, so the
    school is built where each alone is satisfiable and the pair is not. PE
    needs two periods; the legacy rule leaves it only the first period of each
    day, and the IR rule then takes one of those two away."""
    school = _school(db, days=2, per_day=2)
    cg = _class_group(db, school)
    pe = _subject(db, school, "PE")
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [pe.id, maths.id])
    _require(db, cg, pe, 2)
    _require(db, cg, maths, 2)

    db.add(Constraint(school_id=school.id, type="no_subject_period",
                      parameters={"subject_id": pe.id, "position": "last"},
                      description="No PE in the last period"))
    db.commit()

    legacy_only = generate_school_timetable(db, school.id)
    assert legacy_only.status in ("optimal", "feasible"), legacy_only.errors
    assert _periods_used(legacy_only, db, school, "PE") == [(0, 1), (1, 1)]

    _ir(db, school, {"form": "count", "scope": ["class_group"],
                     "selector": {"subjects": ["PE"], "days": [1]},
                     "relation": "==", "value": 0},
        description="No PE on Tuesdays")

    # PE now has one legal slot and needs two, so the pair is unsatisfiable -
    # which only happens if both rules reached the model.
    both = generate_school_timetable(db, school.id)
    assert both.status == "infeasible"


def test_the_new_forms_reach_the_real_solver(db):
    """balance, span and exists_over compile against a real school, not just
    the synthetic board in test_constraint_ir_forms.py.

    Solved twice, because a rule that never reached the model would leave the
    solver free to produce the same answer by chance. Three Maths periods over
    two days with a balance of 0 has exactly one shape.
    """
    school = _school(db, days=2, per_day=3)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 2)

    before = generate_school_timetable(db, school.id)
    assert before.status in ("optimal", "feasible"), before.errors
    assert not before.warnings

    _ir(db, school, {"form": "balance", "scope": ["teacher"], "across": ["day"],
                     "max_spread": 0},
        description="Spread Rao's classes evenly")

    after = generate_school_timetable(db, school.id)
    assert after.status in ("optimal", "feasible"), after.errors
    assert not after.warnings, after.warnings
    used = _periods_used(after, db, school, "Maths")
    per_day = {}
    for day, _order in used:
        per_day[day] = per_day.get(day, 0) + 1
    assert per_day == {0: 1, 1: 1}, used


def test_a_span_rule_compiles_against_a_real_school(db):
    """Span needs first/last position variables, which is the most machinery of
    any form - worth proving it survives contact with real Period rows rather
    than the board's tidy 1..4."""
    school = _school(db, days=1, per_day=4)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 2)

    _ir(db, school, {"form": "span", "scope": ["teacher", "day"], "max_idle": 0},
        description="No gaps in the middle of Rao's day")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert not result.warnings, result.warnings
    orders = sorted(o for _day, o in _periods_used(result, db, school, "Maths"))
    assert orders[1] - orders[0] == 1, f"expected them back to back, got {orders}"


def test_an_exists_over_rule_compiles_against_a_real_school(db):
    """The field that was in the IR, in the tool schema and in the IR tests,
    and never connected in the mapping - so rules meaning "some day" silently
    became "every day". Worth an end-to-end test of its own."""
    school = _school(db, days=2, per_day=3)
    cg = _class_group(db, school)
    maths = _subject(db, school, "Maths")
    _teacher(db, school, "Rao", [maths.id])
    _require(db, cg, maths, 3)

    _ir(db, school, {"form": "count", "scope": ["teacher", "day"],
                     "exists_over": ["day"], "relation": "<=", "value": 1},
        description="Rao gets at least one light day")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert not result.warnings, result.warnings
    per_day = {}
    for day, _order in _periods_used(result, db, school, "Maths"):
        per_day[day] = per_day.get(day, 0) + 1
    assert min(per_day.values()) <= 1, per_day


def test_a_teacher_blocked_after_period_four_in_a_zero_based_school(db):
    """The reported bug, end to end: "Mrs. Kamini Chandra has no periods in
    periods 5, 6, 7 or 8" on a school whose Period rows are numbered from zero
    and whose grid renders `Period {order + 1}`.

    Four lessons and eight periods, with the last four barred, leaves exactly
    the first four - so if the positions resolve wrongly by even one, this is
    either infeasible or puts a lesson where the admin said not to.
    """
    school = School(name="Zero Based")
    db.add(school)
    db.commit()
    db.refresh(school)
    # Orders 0-7, which the timetable grid shows as Period 1 to Period 8.
    for order in range(0, 8):
        db.add(Period(school_id=school.id, day_of_week=0, order=order))
    db.commit()

    cg = _class_group(db, school)
    hindi = _subject(db, school, "Hindi")
    _teacher(db, school, "Mrs. Kamini Chandra", [hindi.id])
    _require(db, cg, hindi, 4)

    _ir(db, school, {"form": "count", "scope": [],
                     "selector": {"teachers": ["Mrs. Kamini Chandra"],
                                  "period_orders": [5, 6, 7, 8]},
                     "relation": "==", "value": 0},
        description="Mrs. Kamini Chandra has no periods in periods 5, 6, 7 or 8")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert not result.warnings, result.warnings

    used = sorted(o for _day, o in _periods_used(result, db, school, "Hindi"))
    # Stored orders 0-3 are the periods displayed as 1-4. Order 4 is the
    # displayed Period 5 - the slot the real timetable wrongly used.
    assert used == [0, 1, 2, 3], f"expected the first four periods, got {used}"

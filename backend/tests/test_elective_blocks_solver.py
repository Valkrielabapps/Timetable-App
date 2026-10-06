"""
Scheduling elective blocks.

A block is one slot with several simultaneous lessons: when it meets, the
section is occupied once and every option needs its own teacher at that
moment. Every property tested here follows from that one sentence, and each
test is set up so the property only holds if the block is genuinely modelled -
a block scheduled as three separate subjects would pass none of them.
"""
from collections import defaultdict

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, ElectiveOption, Period, School, Subject,
    SubjectRequirement, Teacher, Timetable, TimetableEntry,
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


class SchoolBuilder:
    """A school built directly in the database, small enough that each test
    can reason about every slot."""

    def __init__(self, db, days=1, per_day=4):
        self.db = db
        self.school = School(name="Test School")
        db.add(self.school)
        db.commit()
        self.periods = []
        for day in range(days):
            for order in range(per_day):
                period = Period(school_id=self.school.id, day_of_week=day, order=order)
                db.add(period)
                self.periods.append(period)
        self.section = ClassGroup(school_id=self.school.id, grade="Grade 11", name="A")
        db.add(self.section)
        db.commit()
        self.subjects = {}
        self.teachers = {}

    def subject(self, name):
        s = Subject(school_id=self.school.id, name=name)
        self.db.add(s)
        self.db.commit()
        self.subjects[name] = s
        return s

    def teacher(self, name, *subject_names, unavailable=()):
        t = Teacher(
            school_id=self.school.id, name=name,
            qualified_subject_ids=[self.subjects[n].id for n in subject_names],
            unavailable_period_ids=[p.id for p in unavailable],
        )
        self.db.add(t)
        self.db.commit()
        self.teachers[name] = t
        return t

    def common(self, subject_name, periods_per_week, section=None):
        self.db.add(SubjectRequirement(
            class_group_id=(section or self.section).id,
            subject_id=self.subjects[subject_name].id, periods_per_week=periods_per_week,
        ))
        self.db.commit()

    def block(self, name, periods_per_week, *subject_names, section=None, preferred=None):
        preferred = preferred or {}
        block = ElectiveBlock(
            school_id=self.school.id, class_group_id=(section or self.section).id,
            name=name, periods_per_week=periods_per_week,
            options=[
                ElectiveOption(
                    subject_id=self.subjects[n].id,
                    preferred_teacher_id=preferred[n].id if n in preferred else None,
                )
                for n in subject_names
            ],
        )
        self.db.add(block)
        self.db.commit()
        return block

    def rule(self, parameters, description="a rule"):
        self.db.add(Constraint(school_id=self.school.id, type="ir",
                               parameters=parameters, description=description))
        self.db.commit()

    def solve(self):
        return generate_school_timetable(self.db, self.school.id)


def _by(assignments, key):
    out = defaultdict(list)
    for a in assignments:
        out[key(a)].append(a)
    return out


def _standard(db, per_day=4):
    """Physics / Accounts / History in a block, three teachers, one each."""
    s = SchoolBuilder(db, per_day=per_day)
    for name in ("Physics", "Accounts", "History", "English"):
        s.subject(name)
    s.teacher("Mrs. Rao", "Physics")
    s.teacher("Mr. Khan", "Accounts")
    s.teacher("Ms. Das", "History")
    s.teacher("Mr. Iyer", "English")
    return s


# ---------------------------------------------------------------------------
# The shape of a block
# ---------------------------------------------------------------------------


def test_every_option_meets_as_often_as_the_block(db):
    s = _standard(db)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    per_subject = _by(result.assignments, lambda a: a["subject_id"])
    for name in ("Physics", "Accounts", "History"):
        assert len(per_subject[s.subjects[name].id]) == 2, name


def test_every_option_meets_at_the_same_periods(db):
    """The definition of a block. Options that drift apart are just three
    subjects, and a student could not take any combination of them."""
    s = _standard(db)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    periods_of = {
        name: {a["period_id"] for a in result.assignments if a["subject_id"] == s.subjects[name].id}
        for name in ("Physics", "Accounts", "History")
    }
    assert periods_of["Physics"] == periods_of["Accounts"] == periods_of["History"]


def test_each_option_has_its_own_teacher_at_once(db):
    s = _standard(db)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    for _period, rows in _by(result.assignments, lambda a: a["period_id"]).items():
        teachers = [a["teacher_id"] for a in rows]
        assert len(teachers) == len(set(teachers)), "one teacher in two places at once"


def test_assignments_carry_the_block(db):
    """What lets the grid show them as one slot and dragging move them together."""
    s = _standard(db)
    block = s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    assert result.assignments
    assert all(a.get("elective_block_id") == block.id for a in result.assignments)


def test_the_block_occupies_the_section_once(db):
    """Four periods: a 2-period block and 2 periods of English fit exactly -
    but only if the block counts once. Counted per option it would need 6
    plus 2, and this would be infeasible."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    s.common("English", 2)
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors


def test_the_block_and_the_common_subjects_never_share_a_period(db):
    s = _standard(db, per_day=4)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    s.common("English", 2)
    result = s.solve()
    english = {a["period_id"] for a in result.assignments if a["subject_id"] == s.subjects["English"].id}
    block = {a["period_id"] for a in result.assignments if a.get("elective_block_id")}
    assert english and block and not (english & block)


def test_a_section_cannot_fit_more_than_its_periods(db):
    """The other side of counting once: 3 + 2 is still more than 4."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 3, "Physics", "Accounts", "History")
    s.common("English", 2)
    assert s.solve().status == "infeasible"


def test_a_block_teacher_is_not_booked_elsewhere_at_the_same_time(db):
    """Mrs. Rao teaches Physics in 11A's block and Physics to 11B. Two
    periods, two lessons - so they must be in different periods."""
    s = _standard(db, per_day=2)
    other = ClassGroup(school_id=s.school.id, grade="Grade 11", name="B")
    db.add(other)
    db.commit()
    s.block("Block 1", 1, "Physics", "Accounts", "History")
    s.common("Physics", 1, section=other)
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    rao = [a["period_id"] for a in result.assignments if a["teacher_id"] == s.teachers["Mrs. Rao"].id]
    assert len(rao) == 2 and len(set(rao)) == 2


def test_two_blocks_in_one_section_take_different_periods(db):
    s = SchoolBuilder(db, per_day=4)
    for name in ("Physics", "Accounts", "Chemistry", "Economics"):
        s.subject(name)
    s.teacher("A", "Physics")
    s.teacher("B", "Accounts")
    s.teacher("C", "Chemistry")
    s.teacher("D", "Economics")
    one = s.block("Block 1", 2, "Physics", "Accounts")
    two = s.block("Block 2", 2, "Chemistry", "Economics")
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    first = {a["period_id"] for a in result.assignments if a["elective_block_id"] == one.id}
    second = {a["period_id"] for a in result.assignments if a["elective_block_id"] == two.id}
    assert len(first) == 2 and len(second) == 2 and not (first & second)


def test_a_preferred_teacher_on_an_option_is_used(db):
    s = _standard(db)
    s.teacher("Mr. Verma", "Physics")
    s.block("Block 1", 2, "Physics", "Accounts", "History",
            preferred={"Physics": s.teachers["Mr. Verma"]})
    result = s.solve()
    physics = [a for a in result.assignments if a["subject_id"] == s.subjects["Physics"].id]
    assert physics and all(a["teacher_id"] == s.teachers["Mr. Verma"].id for a in physics)


def test_a_school_with_only_blocks_still_generates(db):
    """No common subjects at all is unusual, but it is not "nothing to
    schedule"."""
    s = _standard(db)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors


# ---------------------------------------------------------------------------
# Saying why a block cannot meet
# ---------------------------------------------------------------------------


def test_two_options_sharing_their_only_teacher_are_named(db):
    """The common real failure. Each option has a qualified teacher - the same
    one - so a per-option check passes and only a matching catches it."""
    s = SchoolBuilder(db, per_day=4)
    for name in ("Physics", "Chemistry", "History"):
        s.subject(name)
    s.teacher("Mrs. Rao", "Physics", "Chemistry")
    s.teacher("Ms. Das", "History")
    s.block("Block 1", 2, "Physics", "Chemistry", "History")
    result = s.solve()
    assert result.status == "infeasible"
    message = " ".join(result.errors)
    assert "Physics and Chemistry" in message
    assert "Mrs. Rao" in message
    assert "Block 1" in message


def test_an_option_with_no_qualified_teacher_is_named(db):
    s = _standard(db)
    s.subject("Psychology")
    s.block("Block 1", 2, "Physics", "Accounts", "Psychology")
    result = s.solve()
    assert result.status == "infeasible"
    assert any("Psychology" in e and "Block 1" in e for e in result.errors)


def test_too_few_periods_where_everyone_is_free_is_explained(db):
    """Mr. Khan is away for three of four periods, so the block can meet at
    most once - and it needs two."""
    s = _standard(db, per_day=4)
    khan = s.teachers["Mr. Khan"]
    khan.unavailable_period_ids = [p.id for p in s.periods[1:]]
    db.commit()
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    result = s.solve()
    assert result.status == "infeasible"
    message = " ".join(result.errors)
    assert "needs 2 periods" in message and "in 1" in message


# ---------------------------------------------------------------------------
# Rules about subjects in blocks
# ---------------------------------------------------------------------------


def test_a_rule_about_one_option_keeps_the_whole_block_out(db):
    """"No Physics in period 1" means the block cannot be in period 1 at all,
    because Physics is there whenever the block is."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 3, "Physics", "Accounts", "History")
    s.rule({"form": "count", "scope": ["class_group"],
            "selector": {"subjects": ["Physics"], "period_orders": [1]},
            "relation": "==", "value": 0})
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    first = s.periods[0].id
    assert all(a["period_id"] != first for a in result.assignments)


def test_a_legacy_placement_rule_reaches_a_block_option(db):
    """Rules entered in bulk still arrive as the old named types. They are
    applied per requirement, and a block option has to be one of those."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 3, "Physics", "Accounts", "History")
    db.add(Constraint(school_id=s.school.id, type="no_subject_period",
                      parameters={"subject_id": s.subjects["History"].id, "position": "first"},
                      description="No History in the first period"))
    db.commit()
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    first = s.periods[0].id
    assert all(a["period_id"] != first for a in result.assignments)


def test_a_legacy_per_day_cap_reaches_a_block_option(db):
    s = _standard(db, per_day=4)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    db.add(Constraint(school_id=s.school.id, type="max_subject_periods_per_day",
                      parameters={"subject_id": s.subjects["Physics"].id, "max_per_day": 1},
                      description="Physics at most once a day"))
    db.commit()
    # One day only, two block periods needed, at most one Physics a day.
    assert s.solve().status == "infeasible"


def test_an_unfiltered_daily_cap_counts_the_block_once(db):
    """"At most 3 periods a day" with a 2-period block and 1 of English is
    exactly 3. Counted per option it would be 7."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    s.common("English", 1)
    s.rule({"form": "count", "scope": ["class_group", "day"], "selector": {},
            "relation": "<=", "value": 3})
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors


def test_an_unfiltered_daily_cap_still_bites(db):
    """And the control: 2 + 2 is more than 3."""
    s = _standard(db, per_day=4)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    s.common("English", 2)
    s.rule({"form": "count", "scope": ["class_group", "day"], "selector": {},
            "relation": "<=", "value": 3})
    assert s.solve().status == "infeasible"


def test_a_rule_between_two_options_of_one_block_does_not_block_it(db):
    """No student takes both Physics and Accounts, and they always share a
    period - so "Accounts can't follow Physics" is about nobody. Applying it
    would only stop the block meeting in consecutive periods."""
    s = _standard(db, per_day=2)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    db.add(Constraint(school_id=s.school.id, type="subject_sequence",
                      parameters={"first_subject_id": s.subjects["Physics"].id,
                                  "second_subject_id": s.subjects["Accounts"].id},
                      description="Accounts can't follow Physics"))
    db.commit()
    assert s.solve().status in ("optimal", "feasible")


def test_a_teachers_weekly_cap_counts_their_block_periods(db):
    s = _standard(db, per_day=4)
    rao = s.teachers["Mrs. Rao"]
    rao.max_periods_per_week = 1
    db.commit()
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    assert s.solve().status == "infeasible"


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def _previous(db, s, block, period, rows):
    """A previous draft in which this block slot was locked."""
    tt = Timetable(school_id=s.school.id, status="draft", solver_status="optimal")
    db.add(tt)
    db.commit()
    for subject_name, teacher_name in rows:
        db.add(TimetableEntry(
            timetable_id=tt.id, class_group_id=s.section.id,
            subject_id=s.subjects[subject_name].id, teacher_id=s.teachers[teacher_name].id,
            period_id=period.id, elective_block_id=block.id, locked=True,
        ))
    db.commit()


def test_a_locked_block_slot_stays_where_it_was(db):
    s = _standard(db, per_day=4)
    block = s.block("Block 1", 1, "Physics", "Accounts", "History")
    target = s.periods[3]
    _previous(db, s, block, target,
              [("Physics", "Mrs. Rao"), ("Accounts", "Mr. Khan"), ("History", "Ms. Das")])
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    assert {a["period_id"] for a in result.assignments} == {target.id}


def test_a_locked_block_slot_is_locked_again_in_the_new_timetable(db):
    """Otherwise a lock lasts one regeneration and then quietly lets go."""
    s = _standard(db, per_day=4)
    block = s.block("Block 1", 1, "Physics", "Accounts", "History")
    target = s.periods[2]
    _previous(db, s, block, target,
              [("Physics", "Mrs. Rao"), ("Accounts", "Mr. Khan"), ("History", "Ms. Das")])
    result = s.solve()
    keys = {(a["class_group_id"], a["subject_id"], a["teacher_id"], a["period_id"])
            for a in result.assignments}
    assert keys and keys <= result.locked_keys


def test_a_lock_is_kept_even_where_a_rule_would_now_forbid_it(db):
    """A lock is a deliberate override - the same promise ordinary locks make."""
    s = _standard(db, per_day=4)
    block = s.block("Block 1", 1, "Physics", "Accounts", "History")
    first = s.periods[0]
    _previous(db, s, block, first,
              [("Physics", "Mrs. Rao"), ("Accounts", "Mr. Khan"), ("History", "Ms. Das")])
    db.add(Constraint(school_id=s.school.id, type="no_subject_period",
                      parameters={"subject_id": s.subjects["Physics"].id, "position": "first"},
                      description="No Physics first"))
    db.commit()
    result = s.solve()
    assert {a["period_id"] for a in result.assignments} == {first.id}


def test_an_unlocked_previous_slot_is_free_to_move(db):
    s = _standard(db, per_day=4)
    block = s.block("Block 1", 1, "Physics", "Accounts", "History")
    tt = Timetable(school_id=s.school.id, status="draft", solver_status="optimal")
    db.add(tt)
    db.commit()
    db.add(TimetableEntry(timetable_id=tt.id, class_group_id=s.section.id,
                          subject_id=s.subjects["Physics"].id, teacher_id=s.teachers["Mrs. Rao"].id,
                          period_id=s.periods[3].id, elective_block_id=block.id, locked=False))
    db.commit()
    result = s.solve()
    assert result.status in ("optimal", "feasible")
    assert not result.locked_keys

"""
The rule checker and the solver must agree about elective blocks.

The checker re-reads a finished timetable and reports which rules it breaks. A
freshly generated timetable should break none - the solver was given the same
rules - so any violation on one nobody has touched means the two disagree, and
one of them is wrong.

Blocks are exactly where they could: a block slot is three entries for one
class period. The solver reserves the slot with one variable; a checker
counting entries would see three periods where the solver saw one, and report
"7 periods today" on a timetable that honours "at most 5" - a warning nobody
could act on, because nothing is actually wrong. Split labs had the same
mismatch already, latently; the last test pins that fix too.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.school import Subject, Timetable, TimetableEntry
from app.models.user import User  # noqa: F401 - registers the users table
from app.routers.timetables import _to_timetable_out
from tests.test_elective_blocks_solver import SchoolBuilder


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _generate(db, s):
    result = s.solve()
    assert result.status in ("optimal", "feasible"), result.errors
    tt = Timetable(school_id=s.school.id, status="draft", solver_status=result.status)
    db.add(tt)
    db.commit()
    for a in result.assignments:
        db.add(TimetableEntry(
            timetable_id=tt.id, class_group_id=a["class_group_id"], subject_id=a["subject_id"],
            teacher_id=a["teacher_id"], period_id=a["period_id"],
            lab_batch=a.get("batch"), elective_block_id=a.get("elective_block_id"),
        ))
    db.commit()
    db.refresh(tt)
    return tt


def _school(db, per_day=4):
    s = SchoolBuilder(db, per_day=per_day)
    for name in ("Physics", "Accounts", "History", "English"):
        s.subject(name)
    s.teacher("Mrs. Rao", "Physics")
    s.teacher("Mr. Khan", "Accounts")
    s.teacher("Ms. Das", "History")
    s.teacher("Mr. Iyer", "English")
    return s


def test_a_fresh_timetable_with_a_block_and_a_tight_daily_cap_breaks_nothing(db):
    """2 block periods + 1 English is exactly the cap of 3 - true only if the
    block is counted once. The solver counts it once; so must the checker."""
    s = _school(db)
    s.block("Block 1", 2, "Physics", "Accounts", "History")
    s.common("English", 1)
    s.rule({"form": "count", "scope": ["class_group", "day"], "selector": {},
            "relation": "<=", "value": 3, "strength": "required"},
           description="At most 3 periods a day")
    out = _to_timetable_out(db, _generate(db, s))
    assert out.violations == [], [v.detail for v in out.violations]


def test_a_rule_about_one_option_is_checked_against_that_option_only(db):
    """"At most 1 Physics period a day" over a 1-period block: one Physics
    entry, one period - not three because the slot holds three subjects."""
    s = _school(db)
    s.block("Block 1", 1, "Physics", "Accounts", "History")
    s.rule({"form": "count", "scope": ["class_group", "day"],
            "selector": {"subjects": ["Physics"]}, "relation": "<=", "value": 1,
            "strength": "required"})
    out = _to_timetable_out(db, _generate(db, s))
    assert out.violations == []


def test_a_rule_between_two_options_of_a_slot_does_not_fire(db):
    """Physics and Accounts share every period of the block. "Never on the
    same day" cannot be about them - nobody takes both - and the solver skips
    them; the checker must not report what the solver never constrained."""
    s = _school(db)
    s.block("Block 1", 1, "Physics", "Accounts", "History")
    s.rule({"form": "bucket", "scope": ["class_group"],
            "first": {"subjects": ["Physics"]}, "second": {"subjects": ["Accounts"]},
            "dimension": "day", "relation": "different", "strength": "required"})
    out = _to_timetable_out(db, _generate(db, s))
    assert out.violations == []


def test_moving_the_block_into_a_barred_period_is_still_reported(db):
    """Counting once must not mean counting never: a real violation on a
    block subject still shows."""
    s = _school(db)
    s.block("Block 1", 1, "Physics", "Accounts", "History")
    s.rule({"form": "count", "scope": ["class_group"],
            "selector": {"subjects": ["Physics"], "period_orders": [1]},
            "relation": "==", "value": 0, "strength": "required"},
           description="No Physics in period 1")
    tt = _generate(db, s)
    first = s.periods[0]
    for e in tt.entries:
        e.period_id = first.id  # the whole block, by hand, into period 1
    db.commit()
    out = _to_timetable_out(db, tt)
    assert len(out.violations) == 1
    assert out.violations[0].description == "No Physics in period 1"
    physics = next(e.id for e in tt.entries if e.subject_id == s.subjects["Physics"].id)
    assert out.violations[0].entry_ids == [physics]


def test_a_split_lab_counts_as_one_period_too(db):
    """The same mismatch, already present for lab batches before blocks
    existed: two batch entries in one slot counted as two periods."""
    s = _school(db)
    lab = s.subjects["Physics"]
    lab.lab_batch_count = 2
    db.commit()
    s.teacher("Mr. Verma", "Physics")
    s.common("Physics", 2)
    s.common("English", 1)
    s.rule({"form": "count", "scope": ["class_group", "day"], "selector": {},
            "relation": "<=", "value": 3, "strength": "required"})
    tt = _generate(db, s)
    assert any(e.lab_batch for e in tt.entries), "the lab should have been split"
    out = _to_timetable_out(db, tt)
    assert out.violations == [], [v.detail for v in out.violations]

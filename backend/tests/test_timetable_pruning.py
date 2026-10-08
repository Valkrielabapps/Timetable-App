"""
Old timetables are cleared away after each generation.

Every Generate adds a timetable of about a thousand rows and nothing removed
one, so the entries table grew forever with history the app never shows. The
property under test is the other half: nothing anyone can still reach is ever
deleted - the timetable on screen, the one the next generation reads its locks
from, or anything published.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, School, Subject, Teacher, Timetable, TimetableEntry
from app.routers import timetables as timetables_router
from app.routers.timetables import KEEP_DRAFTS, _prune_old_timetables, _run_generation_job
from app.services.solver import TimetableSolveResult


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def school(db):
    s = School(name="Test School")
    db.add(s)
    db.commit()
    period = Period(school_id=s.id, day_of_week=0, order=0)
    subject = Subject(school_id=s.id, name="Maths")
    teacher = Teacher(school_id=s.id, name="Mrs. Rao", qualified_subject_ids=[])
    section = ClassGroup(school_id=s.id, name="A")
    db.add_all([period, subject, teacher, section])
    db.commit()
    return {"id": s.id, "period": period.id, "subject": subject.id, "teacher": teacher.id,
            "section": section.id}


def add(db, school, status, entries=2):
    """A timetable with a couple of entries, so deleting it has rows to delete."""
    tt = Timetable(school_id=school["id"], status=status)
    db.add(tt)
    db.commit()
    for _ in range(entries):
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=school["section"],
                              subject_id=school["subject"], teacher_id=school["teacher"],
                              period_id=school["period"]))
    db.commit()
    return tt.id


def remaining(db, school_id):
    db.expire_all()
    return [t.id for t in db.query(Timetable).filter(Timetable.school_id == school_id)
            .order_by(Timetable.id).all()]


def test_keeps_only_the_newest_few_drafts(db, school):
    ids = [add(db, school, "draft") for _ in range(KEEP_DRAFTS + 4)]
    _prune_old_timetables(db, school["id"])
    assert remaining(db, school["id"]) == ids[-KEEP_DRAFTS:]


def test_deletes_the_entries_of_what_it_removes(db, school):
    """The entries are the bulk of the growth; removing only the timetable
    rows would leave them behind, or fail on the foreign key."""
    ids = [add(db, school, "draft") for _ in range(KEEP_DRAFTS + 2)]
    _prune_old_timetables(db, school["id"])
    left = {e.timetable_id for e in db.query(TimetableEntry).all()}
    assert left == set(ids[-KEEP_DRAFTS:])


def test_keeps_the_newest_timetable_even_when_it_failed(db, school):
    """The Timetable tab shows the newest one, failure and explanation included."""
    drafts = [add(db, school, "draft") for _ in range(KEEP_DRAFTS + 1)]
    failed = add(db, school, "failed", entries=0)
    _prune_old_timetables(db, school["id"])
    assert remaining(db, school["id"]) == [*drafts[-KEEP_DRAFTS:], failed]


def test_a_failure_does_not_cost_a_draft_its_place(db, school):
    """The newest successful timetable is where the next generation reads its
    locks from, so a failed attempt after it must not push it out."""
    drafts = [add(db, school, "draft") for _ in range(KEEP_DRAFTS)]
    for _ in range(3):
        add(db, school, "failed", entries=0)
    _prune_old_timetables(db, school["id"])
    assert set(drafts) <= set(remaining(db, school["id"]))


def test_removes_older_failures(db, school):
    old_failure = add(db, school, "failed", entries=0)
    newest = add(db, school, "draft")
    _prune_old_timetables(db, school["id"])
    assert remaining(db, school["id"]) == [newest]
    assert old_failure not in remaining(db, school["id"])


def test_never_touches_published_archived_or_generating(db, school):
    kept = [add(db, school, s) for s in ("published", "archived", "generating")]
    for _ in range(KEEP_DRAFTS + 2):
        add(db, school, "draft")
    _prune_old_timetables(db, school["id"])
    assert set(kept) <= set(remaining(db, school["id"]))


def test_leaves_other_schools_alone(db, school):
    other = School(name="Other")
    db.add(other)
    db.commit()
    theirs = [Timetable(school_id=other.id, status="draft") for _ in range(KEEP_DRAFTS + 3)]
    db.add_all(theirs)
    db.commit()
    for _ in range(KEEP_DRAFTS + 3):
        add(db, school, "draft")
    _prune_old_timetables(db, school["id"])
    assert len(remaining(db, other.id)) == KEEP_DRAFTS + 3


def test_a_school_with_nothing_to_prune_is_fine(db, school):
    _prune_old_timetables(db, school["id"])
    only = add(db, school, "draft")
    _prune_old_timetables(db, school["id"])
    assert remaining(db, school["id"]) == [only]


# ---------------------------------------------------------------------------
# Wired into generation
# ---------------------------------------------------------------------------


def _solved(school):
    return TimetableSolveResult(status="optimal", assignments=[{
        "class_group_id": school["section"], "subject_id": school["subject"],
        "teacher_id": school["teacher"], "period_id": school["period"],
    }])


def test_generating_clears_out_old_timetables(db, school, monkeypatch):
    for _ in range(KEEP_DRAFTS + 3):
        add(db, school, "draft")
    monkeypatch.setattr(timetables_router, "generate_school_timetable", lambda _db, _sid: _solved(school))
    new = add(db, school, "generating", entries=0)
    _run_generation_job(new, school["id"])
    left = remaining(db, school["id"])
    assert len(left) == KEEP_DRAFTS
    assert left[-1] == new


def test_a_pruning_failure_does_not_fail_the_generation(db, school, monkeypatch):
    """Housekeeping going wrong is not a reason to tell someone their timetable failed."""
    def broken(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(timetables_router, "generate_school_timetable", lambda _db, _sid: _solved(school))
    monkeypatch.setattr(timetables_router, "_prune_old_timetables", broken)
    new = add(db, school, "generating", entries=0)
    _run_generation_job(new, school["id"])
    db.expire_all()
    timetable = db.get(Timetable, new)
    assert timetable.status == "draft"
    assert len(timetable.entries) == 1

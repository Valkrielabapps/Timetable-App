"""
Moving and locking whole slots.

The drag unit is the slot, not the entry. A slot can hold several entries - an
elective block has one per option, a split lab one per batch - and they always
move together. Every combination a drag can produce goes through one
operation, "exchange two slots", so each is tested here: a lesson into an empty
cell, two lessons swapping, and a block swapping with a lesson, another block,
or nothing.

The refusals matter as much as the moves. A move is all-or-nothing: if any
teacher arriving in a period would be double-booked, nothing moves - a block
half-moved is no longer a block.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Period, Subject, Teacher, Timetable,
    TimetableEntry,
)
from tests.conftest import create_school, signup


@pytest.fixture
def world(client):
    """Two sections over one day of four periods.

    11A: a three-option block in period 1, English in period 2, periods 3-4 free.
    11B: Maths in period 1, taught by Mr. Iyer.
    """
    _, headers = signup(client)
    school = create_school(client, headers)
    db = SessionLocal()
    try:
        sid = school["id"]
        periods = [Period(school_id=sid, day_of_week=0, order=o) for o in range(4)]
        brk = Period(school_id=sid, day_of_week=1, order=0, is_break=True)
        subjects = {n: Subject(school_id=sid, name=n)
                    for n in ("Physics", "Accounts", "History", "English", "Maths",
                              "Chemistry", "Economics")}
        teachers = {n: Teacher(school_id=sid, name=n, qualified_subject_ids=[])
                    for n in ("Rao", "Khan", "Das", "Iyer", "Verma", "Nair")}
        a = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        b = ClassGroup(school_id=sid, grade="Grade 11", name="B")
        db.add_all([*periods, brk, *subjects.values(), *teachers.values(), a, b])
        db.commit()
        block = ElectiveBlock(school_id=sid, class_group_id=a.id, name="Block 1", periods_per_week=1,
                              options=[ElectiveOption(subject_id=subjects[n].id)
                                       for n in ("Physics", "Accounts", "History")])
        db.add(block)
        tt = Timetable(school_id=sid, status="draft", solver_status="optimal")
        db.add(tt)
        db.commit()

        def entry(cg, subject, teacher, period, **kw):
            e = TimetableEntry(timetable_id=tt.id, class_group_id=cg.id,
                               subject_id=subjects[subject].id, teacher_id=teachers[teacher].id,
                               period_id=periods[period].id, **kw)
            db.add(e)
            return e

        blk = [entry(a, "Physics", "Rao", 0, elective_block_id=block.id),
               entry(a, "Accounts", "Khan", 0, elective_block_id=block.id),
               entry(a, "History", "Das", 0, elective_block_id=block.id)]
        english = entry(a, "English", "Verma", 1)
        maths_b = entry(b, "Maths", "Iyer", 0)
        db.commit()
        ids = {
            "tt": tt.id, "a": a.id, "b": b.id, "block": block.id,
            "p": [p.id for p in periods], "break": brk.id,
            "block_entries": [e.id for e in blk], "english": english.id, "maths_b": maths_b.id,
            "subjects": {n: s.id for n, s in subjects.items()},
            "teachers": {n: t.id for n, t in teachers.items()},
        }
    finally:
        db.close()
    return ids, headers


def _move(client, w, headers, cg, frm, to):
    return client.post(f"/api/timetables/{w['tt']}/move-slot", json={
        "class_group_id": cg, "from_period_id": frm, "to_period_id": to,
    }, headers=headers)


def _periods(client, w, headers):
    full = client.get(f"/api/timetables/{w['tt']}", headers=headers).json()
    return {e["id"]: e["period_id"] for e in full["entries"]}


# ---------------------------------------------------------------------------
# Every shape of move
# ---------------------------------------------------------------------------


def test_a_block_moves_into_an_empty_period_as_one(client, world):
    w, h = world
    r = _move(client, w, h, w["a"], w["p"][0], w["p"][2])
    assert r.status_code == 200, r.text
    where = _periods(client, w, h)
    assert {where[i] for i in w["block_entries"]} == {w["p"][2]}


def test_a_block_swaps_with_a_single_lesson(client, world):
    w, h = world
    r = _move(client, w, h, w["a"], w["p"][0], w["p"][1])
    assert r.status_code == 200, r.text
    where = _periods(client, w, h)
    assert {where[i] for i in w["block_entries"]} == {w["p"][1]}
    assert where[w["english"]] == w["p"][0]


def test_a_single_lesson_swaps_with_a_block(client, world):
    """Dragging English onto the block cell is the same exchange from the
    other side, and must give the same result."""
    w, h = world
    r = _move(client, w, h, w["a"], w["p"][1], w["p"][0])
    assert r.status_code == 200, r.text
    where = _periods(client, w, h)
    assert where[w["english"]] == w["p"][0]
    assert {where[i] for i in w["block_entries"]} == {w["p"][1]}


def test_a_single_lesson_moves_into_an_empty_period(client, world):
    w, h = world
    assert _move(client, w, h, w["a"], w["p"][1], w["p"][3]).status_code == 200
    assert _periods(client, w, h)[w["english"]] == w["p"][3]


def test_two_blocks_swap(client, world):
    w, h = world
    db = SessionLocal()
    try:
        block2 = ElectiveBlock(school_id=db.get(Timetable, w["tt"]).school_id,
                               class_group_id=w["a"], name="Block 2", periods_per_week=1,
                               options=[ElectiveOption(subject_id=w["subjects"]["Chemistry"]),
                                        ElectiveOption(subject_id=w["subjects"]["Economics"])])
        db.add(block2)
        db.commit()
        second = [
            TimetableEntry(timetable_id=w["tt"], class_group_id=w["a"],
                           subject_id=w["subjects"][s], teacher_id=w["teachers"][t],
                           period_id=w["p"][3], elective_block_id=block2.id)
            # Nair and Verma are both free in period 1, so Block 2 can land
            # there. (Iyer could not: he teaches 11B then.)
            for s, t in (("Chemistry", "Nair"), ("Economics", "Verma"))
        ]
        db.add_all(second)
        db.commit()
        second_ids = [e.id for e in second]
    finally:
        db.close()
    r = _move(client, w, h, w["a"], w["p"][0], w["p"][3])
    assert r.status_code == 200, r.text
    where = _periods(client, w, h)
    assert {where[i] for i in w["block_entries"]} == {w["p"][3]}
    assert {where[i] for i in second_ids} == {w["p"][0]}


def test_a_split_lab_moves_as_one(client, world):
    """Lab batches were undraggable for exactly the reason blocks would have
    been. Moving the slot moves every batch."""
    w, h = world
    db = SessionLocal()
    try:
        batches = [
            TimetableEntry(timetable_id=w["tt"], class_group_id=w["a"],
                           subject_id=w["subjects"]["Chemistry"], teacher_id=w["teachers"][t],
                           period_id=w["p"][3], lab_batch=n)
            for n, t in ((1, "Iyer"), (2, "Nair"))
        ]
        db.add_all(batches)
        db.commit()
        batch_ids = [e.id for e in batches]
    finally:
        db.close()
    r = _move(client, w, h, w["a"], w["p"][3], w["p"][2])
    assert r.status_code == 200, r.text
    where = _periods(client, w, h)
    assert {where[i] for i in batch_ids} == {w["p"][2]}


def test_the_response_carries_every_moved_row_and_the_violations(client, world):
    """The frontend patches these into its cache instead of re-reading the
    timetable, so they must all come back."""
    w, h = world
    body = _move(client, w, h, w["a"], w["p"][0], w["p"][1]).json()
    assert {e["id"] for e in body["entries"]} == {*w["block_entries"], w["english"]}
    assert "violations" in body
    block_rows = [e for e in body["entries"] if e["elective_block_id"] == w["block"]]
    assert {e["elective_block_name"] for e in block_rows} == {"Block 1"}


# ---------------------------------------------------------------------------
# All or nothing
# ---------------------------------------------------------------------------


def test_a_block_cannot_move_where_one_of_its_teachers_is_busy(client, world):
    """Mr. Iyer teaches 11B in period 1. If he also took an option in 11A's
    block, moving it there would double-book him - and then NOTHING moves,
    not even the options whose teachers are free."""
    w, h = world
    db = SessionLocal()
    try:
        physics = db.get(TimetableEntry, w["block_entries"][0])
        physics.teacher_id = w["teachers"]["Iyer"]
        physics.period_id = w["p"][2]
        for i in w["block_entries"][1:]:
            db.get(TimetableEntry, i).period_id = w["p"][2]
        db.commit()
    finally:
        db.close()
    r = _move(client, w, h, w["a"], w["p"][2], w["p"][0])
    assert r.status_code == 400
    assert "teacher" in r.json()["detail"].lower()
    where = _periods(client, w, h)
    assert {where[i] for i in w["block_entries"]} == {w["p"][2]}, "a half-moved block is no longer a block"


def test_a_locked_slot_does_not_move(client, world):
    w, h = world
    client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][0], "locked": True,
    }, headers=h)
    r = _move(client, w, h, w["a"], w["p"][0], w["p"][2])
    assert r.status_code == 400
    assert "locked" in r.json()["detail"].lower()


def test_nothing_can_be_moved_onto_a_locked_slot(client, world):
    """Swapping into it would move the locked lesson, which is what the lock
    exists to prevent."""
    w, h = world
    client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][1], "locked": True,
    }, headers=h)
    assert _move(client, w, h, w["a"], w["p"][0], w["p"][1]).status_code == 400


def test_moving_an_empty_slot_is_refused(client, world):
    w, h = world
    assert _move(client, w, h, w["a"], w["p"][3], w["p"][2]).status_code == 400


def test_moving_to_the_same_period_is_refused(client, world):
    w, h = world
    assert _move(client, w, h, w["a"], w["p"][0], w["p"][0]).status_code == 400


def test_nothing_moves_into_a_break(client, world):
    w, h = world
    r = _move(client, w, h, w["a"], w["p"][0], w["break"])
    assert r.status_code == 400
    assert "break" in r.json()["detail"].lower()


def test_another_school_cannot_move_slots(client, world):
    w, _ = world
    _, stranger = signup(client, email="stranger@else.com")
    assert _move(client, w, stranger, w["a"], w["p"][0], w["p"][2]).status_code in (403, 404)


# ---------------------------------------------------------------------------
# One option never moves alone
# ---------------------------------------------------------------------------


def test_one_option_of_a_block_cannot_be_moved_on_its_own(client, world):
    """Through the old per-entry endpoint - which the conversational edit
    also uses - moving Physics alone would leave the block's options in
    different periods."""
    w, h = world
    r = client.patch(f"/api/timetables/entries/{w['block_entries'][0]}",
                     json={"period_id": w["p"][2]}, headers=h)
    assert r.status_code == 400
    assert "block" in r.json()["detail"].lower()
    assert _periods(client, w, h)[w["block_entries"][0]] == w["p"][0]


def test_one_option_of_a_block_cannot_be_swapped_on_its_own(client, world):
    w, h = world
    r = client.post(
        f"/api/timetables/entries/{w['block_entries'][0]}/swap-with/{w['english']}", headers=h,
    )
    assert r.status_code == 400


def test_an_option_can_still_change_teacher(client, world):
    """Only the period is shared by the block. Giving Physics a different
    teacher keeps the block whole."""
    w, h = world
    r = client.patch(f"/api/timetables/entries/{w['block_entries'][0]}",
                     json={"teacher_id": w["teachers"]["Nair"]}, headers=h)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Locking a slot
# ---------------------------------------------------------------------------


def test_locking_a_block_locks_every_option(client, world):
    w, h = world
    r = client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][0], "locked": True,
    }, headers=h)
    assert r.status_code == 200, r.text
    assert all(e["locked"] for e in r.json()["entries"])
    assert {e["id"] for e in r.json()["entries"]} == set(w["block_entries"])


def test_unlocking_a_block_unlocks_every_option(client, world):
    w, h = world
    for locked in (True, False):
        r = client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
            "class_group_id": w["a"], "period_id": w["p"][0], "locked": locked,
        }, headers=h)
    assert not any(e["locked"] for e in r.json()["entries"])


def test_locking_only_touches_that_section(client, world):
    """11B's Maths shares the period but is a different slot."""
    w, h = world
    client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][0], "locked": True,
    }, headers=h)
    full = client.get(f"/api/timetables/{w['tt']}", headers=h).json()
    maths = next(e for e in full["entries"] if e["id"] == w["maths_b"])
    assert maths["locked"] is False


def test_locking_an_empty_slot_is_refused(client, world):
    w, h = world
    r = client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][3], "locked": True,
    }, headers=h)
    assert r.status_code == 400


def _add_split_lab(w, locked=False):
    db = SessionLocal()
    try:
        batches = [
            TimetableEntry(timetable_id=w["tt"], class_group_id=w["a"],
                           subject_id=w["subjects"]["Chemistry"], teacher_id=w["teachers"][t],
                           period_id=w["p"][3], lab_batch=n, locked=locked)
            for n, t in ((1, "Iyer"), (2, "Nair"))
        ]
        db.add_all(batches)
        db.commit()
        return [e.id for e in batches]
    finally:
        db.close()


def test_a_split_lab_cannot_be_locked(client, world):
    """The solver re-places every batch on each regeneration, so a lock here
    would promise something the next generate would not keep."""
    w, h = world
    _add_split_lab(w)
    r = client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][3], "locked": True,
    }, headers=h)
    assert r.status_code == 400
    assert "Split labs" in r.json()["detail"]
    full = client.get(f"/api/timetables/{w['tt']}", headers=h).json()
    assert not any(e["locked"] for e in full["entries"] if e["period_id"] == w["p"][3])


def test_an_old_lock_on_a_split_lab_can_still_be_cleared(client, world):
    w, h = world
    ids = _add_split_lab(w, locked=True)
    r = client.post(f"/api/timetables/{w['tt']}/lock-slot", json={
        "class_group_id": w["a"], "period_id": w["p"][3], "locked": False,
    }, headers=h)
    assert r.status_code == 200, r.text
    assert {e["id"] for e in r.json()["entries"] if not e["locked"]} == set(ids)


def test_a_lesson_cannot_be_moved_onto_a_period_its_section_already_uses(client, world):
    """The class double-booking check, isolated. English (Verma) onto period 1,
    where 11A already has its block (Rao, Khan, Das): no teacher clashes, so
    only the section check can refuse it.

    Written after the teacher-change fix, which turns this check off when an
    entry keeps its period. A test that also clashed on a teacher would pass
    with the section check disabled entirely - which is what the first
    mutation run of this file showed.
    """
    w, h = world
    r = client.patch(f"/api/timetables/entries/{w['english']}",
                     json={"period_id": w["p"][0]}, headers=h)
    assert r.status_code == 400
    assert "class group" in r.json()["detail"].lower()
    assert _periods(client, w, h)[w["english"]] == w["p"][1]

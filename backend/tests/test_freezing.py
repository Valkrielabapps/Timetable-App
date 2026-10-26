"""
Freezing a section's timetable while the rest are worked on.

The properties under test:
  - a frozen section comes out of every later generation exactly as it went
    in - same periods, teachers, rooms, locks, assistants, blocks;
  - everyone else is placed around it, with its lessons counted by every
    rule, not skipped;
  - nothing edits it until it is unfrozen;
  - when what it was built from changes, it says so instead of quietly
    regenerating.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import (
    ClassGroup, Constraint, Period, Room, School, Subject, SubjectRequirement, Teacher, Timetable,
    TimetableEntry,
)
from app.routers.timetables import _run_generation_job
from app.schemas.timetable_structure import TimetableStructure
from app.services.timetable_structure import apply
from tests.conftest import create_school, signup


@pytest.fixture
def world(client):
    """One day of four periods. Mrs. Rao teaches Maths to both 11A and 12A,
    two periods each - so once 11A is frozen, 12A can only have the two
    periods 11A doesn't use."""
    _, headers = signup(client)
    school = create_school(client, headers)
    sid = school["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0], periods_per_day=4))
        maths = Subject(school_id=sid, name="Maths")
        db.add(maths)
        db.commit()
        rao = Teacher(school_id=sid, name="Mrs. Rao", qualified_subject_ids=[maths.id])
        eleven = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        twelve = ClassGroup(school_id=sid, grade="Grade 12", name="A")
        room = Room(school_id=sid, name="Room 1")
        db.add_all([rao, eleven, twelve, room])
        db.commit()
        for cg in (eleven, twelve):
            db.add(SubjectRequirement(class_group_id=cg.id, subject_id=maths.id, periods_per_week=2))
        db.commit()
        ids = {"school": sid, "eleven": eleven.id, "twelve": twelve.id, "maths": maths.id, "rao": rao.id,
               "room": room.id}
    finally:
        db.close()
    return ids, headers


def generate(w) -> int:
    db = SessionLocal()
    try:
        tt = Timetable(school_id=w["school"], status="generating")
        db.add(tt)
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    _run_generation_job(tt_id, w["school"])
    return tt_id


def timetable(tt_id):
    db = SessionLocal()
    try:
        tt = db.get(Timetable, tt_id)
        return tt.status, tt.error_message, sorted(
            ((e.class_group_id, e.subject_id, e.teacher_id, e.period_id, e.room_id, e.locked,
              e.assistant_teacher_id) for e in tt.entries),
            # A lesson can have no teacher or room yet; None sorts first.
            key=lambda row: tuple(-1 if v is None else v for v in row),
        )
    finally:
        db.close()


def lessons(tt_id, section):
    return [row for row in timetable(tt_id)[2] if row[0] == section]


def freeze(client, w, h, *sections, frozen=True):
    return client.post("/api/class-groups/freeze", json={
        "school_id": w["school"], "class_group_ids": [w[s] for s in sections], "frozen": frozen,
    }, headers=h)


def status(client, w, h):
    return {s["class_group_id"]: s for s in
            client.get(f"/api/class-groups/frozen-status?school_id={w['school']}", headers=h).json()}


# ---------------------------------------------------------------------------
# Freezing and unfreezing
# ---------------------------------------------------------------------------


def test_a_section_needs_a_timetable_before_it_can_be_frozen(client, world):
    w, h = world
    r = freeze(client, w, h, "eleven")
    assert r.status_code == 400
    assert "Generate a timetable for Grade 11 - A before freezing it" in r.json()["detail"]


def test_freezing_and_unfreezing(client, world):
    w, h = world
    generate(w)
    r = freeze(client, w, h, "eleven")
    assert r.status_code == 200, r.text
    assert status(client, w, h)[w["eleven"]]["frozen"] is True
    assert status(client, w, h)[w["twelve"]]["frozen"] is False
    freeze(client, w, h, "eleven", frozen=False)
    assert status(client, w, h)[w["eleven"]]["frozen"] is False


def test_a_whole_grade_at_once(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven", "twelve")
    assert all(s["frozen"] for s in status(client, w, h).values())


def test_freezing_again_keeps_the_original_moment(client, world):
    """Re-applying "freeze grade" mustn't reset an out-of-date section's
    record of what it was frozen with, or the warning would vanish."""
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    first = status(client, w, h)[w["eleven"]]["frozen_at"]
    freeze(client, w, h, "eleven", "twelve")
    assert status(client, w, h)[w["eleven"]]["frozen_at"] == first


def test_a_viewer_cannot_freeze(client, world):
    w, h = world
    generate(w)
    _, other = signup(client, email="viewer@x.com")
    assert freeze(client, w, other, "eleven").status_code in (403, 404)


# ---------------------------------------------------------------------------
# Generating around a frozen section
# ---------------------------------------------------------------------------


def test_a_frozen_section_comes_through_unchanged_and_the_rest_fits_around_it(client, world):
    w, h = world
    first = generate(w)
    kept = lessons(first, w["eleven"])
    freeze(client, w, h, "eleven")
    second = generate(w)
    assert timetable(second)[0] == "draft"
    assert lessons(second, w["eleven"]) == kept
    # Mrs. Rao is busy in 11A's two periods, so 12A has the other two.
    eleven_periods = {row[3] for row in kept}
    twelve_periods = {row[3] for row in lessons(second, w["twelve"])}
    assert len(twelve_periods) == 2 and not (eleven_periods & twelve_periods)


def test_rooms_locks_and_assistants_are_kept_too(client, world):
    """11A has 40 students and the small room seats 10, so a fresh room
    assignment would never put 11A there - only keeping it can."""
    w, h = world
    first = generate(w)
    db = SessionLocal()
    try:
        helper = Teacher(school_id=w["school"], name="Mr. Khan", qualified_subject_ids=[])
        small = Room(school_id=w["school"], name="Small room", capacity=10)
        db.add_all([helper, small])
        db.get(ClassGroup, w["eleven"]).student_count = 40
        db.commit()
        for e in db.query(TimetableEntry).filter(TimetableEntry.timetable_id == first,
                                                 TimetableEntry.class_group_id == w["eleven"]):
            e.room_id, e.locked, e.assistant_teacher_id = small.id, True, helper.id
        db.commit()
        small_id = small.id
    finally:
        db.close()
    freeze(client, w, h, "eleven")
    second = generate(w)
    for row in lessons(second, w["eleven"]):
        assert row[4] == small_id and row[5] is True and row[6] is not None
    # The room stays 11A's in those periods: no room is ever in two places.
    used = [(row[3], row[4]) for row in timetable(second)[2] if row[4] is not None]
    assert len(used) == len(set(used))


def test_a_frozen_sections_plan_is_not_re_solved(client, world):
    """Freezing promises the timetable won't change - so a new requirement
    waits for an unfreeze, and the section is flagged in the meantime."""
    w, h = world
    first = generate(w)
    kept = lessons(first, w["eleven"])
    freeze(client, w, h, "eleven")
    db = SessionLocal()
    try:
        req = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == w["eleven"]).one()
        req.periods_per_week = 1
        db.commit()
    finally:
        db.close()
    second = generate(w)
    assert lessons(second, w["eleven"]) == kept
    assert "plan has changed" in status(client, w, h)[w["eleven"]]["stale_reason"]


def test_unfreezing_lets_the_section_be_generated_again(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    db = SessionLocal()
    try:
        req = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == w["eleven"]).one()
        req.periods_per_week = 1
        db.commit()
    finally:
        db.close()
    freeze(client, w, h, "eleven", frozen=False)
    assert len(lessons(generate(w), w["eleven"])) == 1


def test_rules_count_frozen_lessons(client, world):
    """"Mrs. Rao at most 3 periods a day": 11A's two frozen lessons count, so
    12A's two more would make four - impossible. Skipping frozen lessons
    would have quietly given her four."""
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    db = SessionLocal()
    try:
        db.add(Constraint(school_id=w["school"], type="ir", is_hard=True, description="Rao at most 3 a day",
                          parameters={"form": "count", "scope": ["teacher", "day"],
                                      "selector": {"teachers": ["Mrs. Rao"]}, "relation": "<=", "value": 3,
                                      "strength": "required"}))
        db.commit()
    finally:
        db.close()
    state, message, _ = timetable(generate(w))
    assert state == "failed"
    assert "frozen section kept its lessons where they were" in message


def test_a_teacher_overloaded_by_frozen_lessons_alone_is_named(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    db = SessionLocal()
    try:
        db.get(Teacher, w["rao"]).max_periods_per_week = 1
        db.commit()
    finally:
        db.close()
    state, message, _ = timetable(generate(w))
    assert state == "failed"
    assert "Mrs. Rao's lessons in frozen sections alone come to 2 periods a week" in message


def test_everything_frozen_keeps_the_whole_timetable(client, world):
    w, h = world
    first = generate(w)
    db = SessionLocal()
    try:
        db.query(TimetableEntry).filter(TimetableEntry.timetable_id == first).first().locked = True
        db.commit()
    finally:
        db.close()
    freeze(client, w, h, "eleven", "twelve")
    second = generate(w)
    assert timetable(second)[0] == "draft"
    assert timetable(second)[2] == timetable(first)[2]


def test_a_frozen_section_with_nothing_to_keep_is_generated_and_said_so(client, world):
    """Frozen with no lessons on screen (set behind the API's back here): it
    can't be kept, so it is generated - with a warning, not silently."""
    w, h = world
    db = SessionLocal()
    try:
        db.get(ClassGroup, w["eleven"]).frozen = True
        db.commit()
    finally:
        db.close()
    tt = generate(w)
    assert timetable(tt)[0] == "draft"
    assert len(lessons(tt, w["eleven"])) == 2


def test_lessons_lost_to_a_structure_change_are_flagged(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    db = SessionLocal()
    try:
        apply(db, w["school"], TimetableStructure(days=[0], periods_per_day=1))
    finally:
        db.close()
    reason = status(client, w, h)[w["eleven"]]["stale_reason"]
    assert reason is not None and "structure changed" in reason


# ---------------------------------------------------------------------------
# Nothing edits it
# ---------------------------------------------------------------------------


def _entries(tt_id, section):
    db = SessionLocal()
    try:
        return db.query(TimetableEntry).filter(TimetableEntry.timetable_id == tt_id,
                                               TimetableEntry.class_group_id == section).all()
    finally:
        db.close()


def _free_period(tt_id, w):
    db = SessionLocal()
    try:
        used = {e.period_id for e in db.query(TimetableEntry).filter(TimetableEntry.timetable_id == tt_id)}
        return next(p.id for p in db.query(Period).filter(Period.school_id == w["school"]) if p.id not in used
                    ) if len(used) < 4 else None
    finally:
        db.close()


def test_a_frozen_section_cannot_be_dragged_locked_or_edited(client, world):
    w, h = world
    tt = generate(w)
    freeze(client, w, h, "eleven")
    entry = _entries(tt, w["eleven"])[0]
    other = _entries(tt, w["twelve"])[0]
    attempts = [
        client.post(f"/api/timetables/{tt}/move-slot", json={
            "class_group_id": w["eleven"], "from_period_id": entry.period_id, "to_period_id": other.period_id},
            headers=h),
        client.post(f"/api/timetables/{tt}/lock-slot", json={
            "class_group_id": w["eleven"], "period_id": entry.period_id, "locked": True}, headers=h),
        client.patch(f"/api/timetables/entries/{entry.id}", json={"locked": True}, headers=h),
        client.post(f"/api/timetables/entries/{other.id}/swap-with/{entry.id}", headers=h),
    ]
    for r in attempts:
        assert r.status_code == 400, r.text
        assert "Grade 11 A is frozen" in r.json()["detail"]


def test_an_unfrozen_section_can_still_be_edited(client, world):
    w, h = world
    tt = generate(w)
    freeze(client, w, h, "eleven")
    other = _entries(tt, w["twelve"])[0]
    r = client.patch(f"/api/timetables/entries/{other.id}", json={"locked": True}, headers=h)
    assert r.status_code == 200, r.text


def test_a_frozen_lesson_with_no_teacher_yet_is_kept(client, world):
    """A lesson can be timetabled before anyone is found to teach it. Frozen,
    it stays where it is - it isn't mistaken for a teacher who has left."""
    w, h = world
    first = generate(w)
    db = SessionLocal()
    try:
        e = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == first,
                                            TimetableEntry.class_group_id == w["eleven"]).first()
        e.teacher_id = None
        db.commit()
    finally:
        db.close()
    kept = lessons(first, w["eleven"])
    freeze(client, w, h, "eleven")
    second = generate(w)
    assert timetable(second)[0] == "draft"
    assert lessons(second, w["eleven"]) == kept



def test_the_timetable_says_which_sections_it_kept_frozen(client, world):
    """A freeze that didn't hold used to look exactly like one that did: the
    solver's notes were logged and thrown away. Now the timetable says which
    sections it kept frozen, and passes the notes on."""
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    second = generate(w)
    body = client.get(f"/api/timetables/{second}", headers=h).json()
    assert body["frozen_kept"] == ["Grade 11 - A"]
    assert body["generation_notes"] == []


def test_a_freeze_that_could_not_hold_is_reported(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h, "eleven")
    # Mrs. Rao leaves: 11A's frozen lessons can't be kept as they were.
    db = SessionLocal()
    try:
        db.add(Teacher(school_id=w["school"], name="Mr. Iyer", qualified_subject_ids=[w["maths"]]))
        db.delete(db.get(Teacher, w["rao"]))
        db.commit()
    finally:
        db.close()
    second = generate(w)
    body = client.get(f"/api/timetables/{second}", headers=h).json()
    assert body["frozen_kept"] == []
    assert any("Grade 11 - A is frozen" in n for n in body["generation_notes"]), body["generation_notes"]

"""
Freezing a subject: its lessons stay exactly where they are - periods,
teachers, rooms - in the sections chosen, while everything else is
regenerated around them.

The properties under test:
  - a frozen subject's lessons come through every later generation
    unchanged, even when the plan would now put them elsewhere, while other
    subjects - and the same subject outside the scope - move freely;
  - the scope is the whole school, some grades or some sections;
  - in an elective block, just the subject (the block's periods with it) or
    the whole block;
  - more periods than when frozen: the frozen lessons are kept and the extra
    placed around them; fewer, a new teacher, the subject gone: out of date,
    and generating says so instead of changing it;
  - frozen lessons can't be edited, and the version they're kept from can't
    be deleted.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Period, Subject, SubjectRequirement, Teacher, Timetable,
    TimetableEntry,
)
from app.schemas.timetable_structure import TimetableStructure
from app.services.subject_freezing import pinned_lessons
from app.services.timetable_structure import apply
from tests.conftest import create_school, signup
from tests.test_access_control import _invite_and_accept
from tests.test_freezing import generate, timetable


@pytest.fixture
def world(client):
    """Monday, six periods. 11A and 12A each have Maths (Mrs. Rao) and
    English (Mr. Khan), two periods each - so each section has two free
    periods and every lesson has somewhere else it could go."""
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0], periods_per_day=6))
        maths, english = Subject(school_id=sid, name="Maths"), Subject(school_id=sid, name="English")
        db.add_all([maths, english])
        db.commit()
        rao = Teacher(school_id=sid, name="Mrs. Rao", qualified_subject_ids=[maths.id])
        khan = Teacher(school_id=sid, name="Mr. Khan", qualified_subject_ids=[english.id])
        eleven = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        twelve = ClassGroup(school_id=sid, grade="Grade 12", name="A")
        db.add_all([rao, khan, eleven, twelve])
        db.commit()
        for cg in (eleven, twelve):
            for subject in (maths, english):
                db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subject.id, periods_per_week=2))
        db.commit()
        w = {"school": sid, "maths": maths.id, "english": english.id, "rao": rao.id, "khan": khan.id,
             "eleven": eleven.id, "twelve": twelve.id}
    finally:
        db.close()
    return w, headers


def rows(tt_id, section=None, subject=None):
    """(section, subject, teacher, period) of each lesson, sorted."""
    return sorted(
        (r[0], r[1], r[2], r[3]) for r in timetable(tt_id)[2]
        if (section is None or r[0] == section) and (subject is None or r[1] == subject)
    )


def periods_of(tt_id, section, subject):
    return {r[3] for r in rows(tt_id, section, subject)}


def freeze(client, w, h, subject="maths", **body):
    return client.post("/api/subject-freezes", json={"school_id": w["school"], "subject_id": w[subject], **body},
                       headers=h)


def statuses(client, w, h):
    r = client.get(f"/api/subject-freezes?school_id={w['school']}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def make_unavailable(teacher_id, period_ids):
    db = SessionLocal()
    try:
        db.get(Teacher, teacher_id).unavailable_period_ids = sorted(period_ids)
        db.commit()
    finally:
        db.close()


def set_requirement(w, section, subject, **fields):
    db = SessionLocal()
    try:
        req = db.query(SubjectRequirement).filter_by(class_group_id=w[section], subject_id=w[subject]).one()
        for k, v in fields.items():
            setattr(req, k, v)
        db.commit()
    finally:
        db.close()


def notes(tt_id):
    db = SessionLocal()
    try:
        return (db.get(Timetable, tt_id).generation_notes or {}).get("notes", [])
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Generating around a frozen subject
# ---------------------------------------------------------------------------


def test_a_frozen_subject_stays_put_while_the_rest_moves(client, world):
    w, h = world
    first = generate(w)
    kept = rows(first, subject=w["maths"])
    english_11 = periods_of(first, w["eleven"], w["english"])
    assert freeze(client, w, h).status_code == 201
    # Now Mrs. Rao "can't" teach one of her Maths periods and Mr. Khan one of
    # his English ones. Maths is frozen, so it stays; English must move.
    make_unavailable(w["rao"], {kept[0][3]})
    make_unavailable(w["khan"], {min(english_11)})
    second = generate(w)
    assert timetable(second)[0] == "draft", timetable(second)[1]
    assert rows(second, subject=w["maths"]) == kept
    assert min(english_11) not in periods_of(second, w["eleven"], w["english"])
    assert len(periods_of(second, w["eleven"], w["english"])) == 2
    assert "Maths kept as frozen in 2 sections, from Version 1." in notes(second)
    # And through every generation after.
    assert rows(generate(w), subject=w["maths"]) == kept


def test_frozen_lessons_are_not_carried_forward_as_locks(client, world):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    second = generate(w)
    assert all(r[5] is False for r in timetable(second)[2])


def test_unfreezing_lets_the_subject_move_again(client, world):
    w, h = world
    first = generate(w)
    kept = rows(first, subject=w["maths"])
    freeze(client, w, h)
    [f] = statuses(client, w, h)
    r = client.delete(f"/api/subject-freezes/{f['id']}?school_id={w['school']}", headers=h)
    assert r.status_code == 200 and r.json() == []
    make_unavailable(w["rao"], {kept[0][3]})
    second = generate(w)
    assert kept[0][3] not in {r[3] for r in rows(second, subject=w["maths"])}


def test_scope_some_sections(client, world):
    w, h = world
    first = generate(w)
    r = freeze(client, w, h, scope="sections", class_group_ids=[w["eleven"]])
    assert r.status_code == 201, r.text
    assert r.json()[0]["scope_label"] == "Grade 11 - A"
    # A period where 12A has Maths: unfrozen there, so it moves; 11A's stays.
    twelve_maths = periods_of(first, w["twelve"], w["maths"])
    make_unavailable(w["rao"], {min(twelve_maths)})
    second = generate(w)
    assert rows(second, w["eleven"], w["maths"]) == rows(first, w["eleven"], w["maths"])
    assert min(twelve_maths) not in periods_of(second, w["twelve"], w["maths"])
    assert "Maths kept as frozen in 1 section, from Version 1." in notes(second)


def test_scope_some_grades(client, world):
    w, h = world
    first = generate(w)
    r = freeze(client, w, h, scope="grades", grades=["Grade 12"])
    assert r.status_code == 201, r.text
    [f] = r.json()
    assert (f["scope_label"], f["section_count"], f["class_group_ids"]) == ("Grade 12", 1, [w["twelve"]])
    eleven_maths = periods_of(first, w["eleven"], w["maths"])
    make_unavailable(w["rao"], {min(eleven_maths)})
    second = generate(w)
    assert rows(second, w["twelve"], w["maths"]) == rows(first, w["twelve"], w["maths"])
    assert min(eleven_maths) not in periods_of(second, w["eleven"], w["maths"])


def test_a_section_added_later_gets_the_subject_placed_normally(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h)
    db = SessionLocal()
    try:
        ten = ClassGroup(school_id=w["school"], grade="Grade 10", name="A")
        db.add(ten)
        db.commit()
        db.add(SubjectRequirement(class_group_id=ten.id, subject_id=w["maths"], periods_per_week=1))
        db.commit()
        ten_id = ten.id
    finally:
        db.close()
    assert statuses(client, w, h)[0]["stale_reasons"] == []
    second = generate(w)
    assert timetable(second)[0] == "draft"
    assert len(rows(second, ten_id, w["maths"])) == 1


def test_a_frozen_section_is_kept_whole(client, world):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    client.post("/api/class-groups/freeze", json={
        "school_id": w["school"], "class_group_ids": [w["eleven"]], "frozen": True}, headers=h)
    second = generate(w)
    assert timetable(second)[0] == "draft"
    assert rows(second, w["eleven"]) == rows(first, w["eleven"])
    assert "Maths kept as frozen in 1 section, from Version 1." in notes(second)


# ---------------------------------------------------------------------------
# When the plan changes after freezing
# ---------------------------------------------------------------------------


def test_more_periods_keeps_the_frozen_ones_and_places_the_extra(client, world):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    set_requirement(w, "eleven", "maths", periods_per_week=3)
    [f] = statuses(client, w, h)
    assert f["stale_reasons"] == []
    assert f["notes"] == ["Grade 11 - A now has 1 more period of Maths a week than when it was frozen; "
                          "it is placed around the frozen ones."]
    second = generate(w)
    assert timetable(second)[0] == "draft", timetable(second)[1]
    assert periods_of(first, w["eleven"], w["maths"]) < periods_of(second, w["eleven"], w["maths"])
    assert len(rows(second, w["eleven"], w["maths"])) == 3
    assert f["notes"][0] in notes(second)


@pytest.mark.parametrize("change,reason", [
    (lambda w: set_requirement(w, "eleven", "maths", periods_per_week=1),
     "Grade 11 - A's Maths went from 2 to 1 periods a week."),
    (lambda w: set_requirement(w, "eleven", "maths", preferred_teacher_id=w["rao"]),
     "Grade 11 - A's Maths teacher was changed."),
    (lambda w: _delete_requirement(w, "eleven", "maths"),
     "Grade 11 - A no longer has Maths."),
    (lambda w: _delete_a_lesson(w, "eleven", "maths"),
     "Some of Grade 11 - A's Maths lessons were removed when the week's structure changed."),
])
def test_out_of_date_freezes_stop_the_generation(client, world, change, reason):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    change(w)
    [f] = statuses(client, w, h)
    assert f["stale_reasons"] == [reason]
    second = generate(w)
    status, error, _ = timetable(second)
    assert status == "failed"
    assert f"Maths is frozen, but it has changed since: {reason} Unfreeze Maths to regenerate it" in error


def _delete_requirement(w, section, subject):
    db = SessionLocal()
    try:
        db.query(SubjectRequirement).filter_by(class_group_id=w[section], subject_id=w[subject]).delete()
        db.commit()
    finally:
        db.close()


def _delete_a_lesson(w, section, subject):
    db = SessionLocal()
    try:
        e = db.query(TimetableEntry).filter_by(class_group_id=w[section], subject_id=w[subject]).first()
        db.delete(e)
        db.commit()
    finally:
        db.close()


def test_a_removed_teacher_makes_it_out_of_date(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h)
    db = SessionLocal()
    try:
        db.delete(db.get(Teacher, w["rao"]))
        db.commit()
    finally:
        db.close()
    reasons = statuses(client, w, h)[0]["stale_reasons"]
    assert "A teacher of Grade 11 - A's frozen Maths lessons has been removed." in reasons


# ---------------------------------------------------------------------------
# Freezing: what's allowed
# ---------------------------------------------------------------------------


def test_needs_a_timetable_first(client, world):
    w, h = world
    r = freeze(client, w, h)
    assert r.status_code == 400
    assert "Generate a timetable before freezing" in r.json()["detail"]


def test_refuses_a_scope_without_the_subject_or_without_lessons(client, world):
    w, h = world
    generate(w)
    db = SessionLocal()
    try:
        art = Subject(school_id=w["school"], name="Art")
        db.add(art)
        db.commit()
        db.add(SubjectRequirement(class_group_id=w["twelve"], subject_id=art.id, periods_per_week=1))
        db.commit()
        w["art"] = art.id
    finally:
        db.close()
    r = freeze(client, w, h, subject="art", scope="sections", class_group_ids=[w["eleven"]])
    assert r.status_code == 400 and r.json()["detail"] == "None of the sections chosen have Art."
    # 12A has Art now, but the version on screen was made before it.
    r = freeze(client, w, h, subject="art")
    assert r.status_code == 400
    assert "Art has no lessons yet for Grade 12 - A in this version" in r.json()["detail"]
    assert freeze(client, w, h, scope="grades", grades=[]).status_code == 400
    assert freeze(client, w, h, scope="sections", class_group_ids=[999999]).status_code == 404


def test_refuses_freezing_the_same_lessons_twice(client, world):
    w, h = world
    generate(w)
    assert freeze(client, w, h, scope="sections", class_group_ids=[w["eleven"]]).status_code == 201
    r = freeze(client, w, h)
    assert r.status_code == 400
    assert r.json()["detail"] == ("Maths is already frozen for Grade 11 - A. "
                                  "Unfreeze it there first to freeze it again.")
    # Another section is fine.
    assert freeze(client, w, h, scope="sections", class_group_ids=[w["twelve"]]).status_code == 201
    assert len(statuses(client, w, h)) == 2


def test_status_names_the_version_and_scope(client, world):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    [f] = statuses(client, w, h)
    assert f["subject"] == "Maths"
    assert (f["scope"], f["scope_label"], f["section_count"]) == ("school", "Whole school", 2)
    assert (f["frozen_from"], f["frozen_from_timetable_id"]) == ("Version 1", first)
    assert f["in_blocks"] is False


def test_viewers_can_see_but_not_freeze(client, world):
    w, h = world
    generate(w)
    _, viewer = _invite_and_accept(client, h, w["school"], "viewer@a.com", "viewer")
    assert freeze(client, w, viewer).status_code == 403
    freeze(client, w, h)
    assert len(statuses(client, w, viewer)) == 1
    f = statuses(client, w, h)[0]
    assert client.delete(f"/api/subject-freezes/{f['id']}?school_id={w['school']}",
                         headers=viewer).status_code == 403
    _, stranger = signup(client, email="b@b.com")
    assert client.get(f"/api/subject-freezes?school_id={w['school']}", headers=stranger).status_code == 404


def test_deleting_the_subject_removes_its_freeze(client, world):
    w, h = world
    generate(w)
    freeze(client, w, h)
    assert client.delete(f"/api/subjects/{w['maths']}", headers=h).status_code in (200, 204)
    assert statuses(client, w, h) == []


# ---------------------------------------------------------------------------
# Frozen lessons on the timetable
# ---------------------------------------------------------------------------


def _timetable_json(client, h, tt_id):
    r = client.get(f"/api/timetables/{tt_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_frozen_lessons_are_marked_and_cannot_be_edited(client, world):
    w, h = world
    tt = generate(w)
    freeze(client, w, h, scope="sections", class_group_ids=[w["eleven"]])
    entries = _timetable_json(client, h, tt)["entries"]
    frozen = {(e["class_group_id"], e["subject_id"]) for e in entries if e["subject_frozen"]}
    assert frozen == {(w["eleven"], w["maths"])}

    maths = next(e for e in entries if e["class_group_id"] == w["eleven"] and e["subject_id"] == w["maths"])
    message = "Maths is frozen, so this lesson stays where it is. Unfreeze Maths to change it."
    used = {e["period_id"] for e in entries if e["class_group_id"] == w["eleven"]}
    db = SessionLocal()
    try:
        free = next(p.id for p in db.query(Period).filter_by(school_id=w["school"]) if p.id not in used)
    finally:
        db.close()
    r = client.post(f"/api/timetables/{tt}/move-slot", headers=h, json={
        "class_group_id": w["eleven"], "from_period_id": maths["period_id"], "to_period_id": free})
    assert (r.status_code, r.json()["detail"]) == (400, message)
    r = client.post(f"/api/timetables/{tt}/lock-slot", headers=h, json={
        "class_group_id": w["eleven"], "period_id": maths["period_id"], "locked": True})
    assert (r.status_code, r.json()["detail"]) == (400, message)
    r = client.patch(f"/api/timetables/entries/{maths['id']}", headers=h, json={"period_id": free})
    assert (r.status_code, r.json()["detail"]) == (400, message)
    english = next(e for e in entries if e["class_group_id"] == w["eleven"] and e["subject_id"] == w["english"])
    r = client.post(f"/api/timetables/entries/{english['id']}/swap-with/{maths['id']}", headers=h)
    assert (r.status_code, r.json()["detail"]) == (400, message)
    # English isn't frozen: it moves.
    r = client.post(f"/api/timetables/{tt}/move-slot", headers=h, json={
        "class_group_id": w["eleven"], "from_period_id": english["period_id"], "to_period_id": free})
    assert r.status_code == 200, r.text
    assert all(e["subject_frozen"] is False for e in r.json()["entries"])


def test_the_version_a_subject_is_frozen_from_is_kept(client, world):
    w, h = world
    first = generate(w)
    freeze(client, w, h)
    for _ in range(6):
        generate(w)
    db = SessionLocal()
    try:
        assert db.get(Timetable, first) is not None
    finally:
        db.close()
    r = client.delete(f"/api/timetables/{first}", headers=h)
    assert r.status_code == 409
    assert "Maths is frozen from this version" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Elective blocks
# ---------------------------------------------------------------------------


@pytest.fixture
def block_world(client):
    """11A, one day of five periods: a block of Physics (Ms. Sen) / Accounts
    (Mr. Khan or Ms. Iyer), two periods, and English (Mr. Bose), two."""
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0], periods_per_day=5))
        physics, accounts, english = (Subject(school_id=sid, name=n) for n in ("Physics", "Accounts", "English"))
        db.add_all([physics, accounts, english])
        db.commit()
        sen = Teacher(school_id=sid, name="Ms. Sen", qualified_subject_ids=[physics.id])
        khan = Teacher(school_id=sid, name="Mr. Khan", qualified_subject_ids=[accounts.id])
        iyer = Teacher(school_id=sid, name="Ms. Iyer", qualified_subject_ids=[accounts.id])
        bose = Teacher(school_id=sid, name="Mr. Bose", qualified_subject_ids=[english.id])
        eleven = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        db.add_all([sen, khan, iyer, bose, eleven])
        db.commit()
        db.add(SubjectRequirement(class_group_id=eleven.id, subject_id=english.id, periods_per_week=2))
        db.add(ElectiveBlock(school_id=sid, class_group_id=eleven.id, name="Block 1", periods_per_week=2,
                             options=[ElectiveOption(subject_id=physics.id), ElectiveOption(subject_id=accounts.id)]))
        db.commit()
        w = {"school": sid, "physics": physics.id, "accounts": accounts.id, "english": english.id,
             "sen": sen.id, "khan": khan.id, "iyer": iyer.id, "eleven": eleven.id}
    finally:
        db.close()
    return w, headers


def test_freezing_just_the_subject_keeps_the_blocks_periods(client, block_world):
    w, h = block_world
    first = generate(w)
    physics = rows(first, subject=w["physics"])
    accounts = rows(first, subject=w["accounts"])
    accounts_teacher = accounts[0][2]
    r = freeze(client, w, h, subject="physics")
    assert r.status_code == 201, r.text
    assert r.json()[0]["in_blocks"] is True
    entries = _timetable_json(client, h, first)["entries"]
    assert {e["subject_id"] for e in entries if e["subject_frozen"]} == {w["physics"]}
    # The Accounts teacher can't make one of the block's periods any more.
    make_unavailable(accounts_teacher, {physics[0][3]})
    second = generate(w)
    assert timetable(second)[0] == "draft", timetable(second)[1]
    assert rows(second, subject=w["physics"]) == physics
    # Accounts still runs alongside Physics - it's a block - but with the
    # other teacher, which only freezing the whole block would have stopped.
    assert periods_of(second, w["eleven"], w["accounts"]) == {r[3] for r in physics}
    assert {r[2] for r in rows(second, subject=w["accounts"])} == {w["iyer"] if accounts_teacher == w["khan"] else w["khan"]}


def test_freezing_the_whole_block(client, block_world):
    w, h = block_world
    first = generate(w)
    r = freeze(client, w, h, subject="physics", block_mode="block")
    assert r.status_code == 201, r.text
    assert r.json()[0]["block_mode"] == "block"
    db = SessionLocal()
    try:
        pinned = {(e.subject_id, e.teacher_id, e.period_id) for e in pinned_lessons(db, w["school"]).entries}
    finally:
        db.close()
    assert pinned == {(r[1], r[2], r[3]) for r in rows(first) if r[1] in (w["physics"], w["accounts"])}
    entries = _timetable_json(client, h, first)["entries"]
    assert {e["subject_id"] for e in entries if e["subject_frozen"]} == {w["physics"], w["accounts"]}
    # English moves when it has to; the block doesn't.
    english = periods_of(first, w["eleven"], w["english"])
    db = SessionLocal()
    try:
        bose = db.query(Teacher).filter_by(school_id=w["school"], name="Mr. Bose").one().id
    finally:
        db.close()
    make_unavailable(bose, {min(english)})
    second = generate(w)
    assert timetable(second)[0] == "draft", timetable(second)[1]
    assert rows(second, subject=w["physics"]) + rows(second, subject=w["accounts"]) == \
        rows(first, subject=w["physics"]) + rows(first, subject=w["accounts"])
    assert min(english) not in periods_of(second, w["eleven"], w["english"])


def test_block_subjects_changing_makes_a_whole_block_freeze_out_of_date(client, block_world):
    w, h = block_world
    generate(w)
    freeze(client, w, h, subject="physics", block_mode="block")
    db = SessionLocal()
    try:
        option = db.query(ElectiveOption).filter_by(subject_id=w["accounts"]).one()
        option.preferred_teacher_id = w["iyer"]
        db.commit()
    finally:
        db.close()
    assert statuses(client, w, h)[0]["stale_reasons"] == [
        "The subjects or teachers in Grade 11 - A's elective block with Physics changed."
    ]


# ---------------------------------------------------------------------------
# Split labs
# ---------------------------------------------------------------------------


def test_a_frozen_split_lab_keeps_its_session_and_each_batchs_teacher(client):
    """Chemistry once a week in two batches. A soft rule against its day
    would move it - frozen, it stays, batches and teachers and all."""
    from app.models.school import Constraint

    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0, 1], periods_per_day=2))
        chem = Subject(school_id=sid, name="Chemistry", lab_batch_count=2)
        db.add(chem)
        db.commit()
        db.add_all([Teacher(school_id=sid, name=n, qualified_subject_ids=[chem.id]) for n in ("A", "B", "C")])
        cg = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        db.add(cg)
        db.commit()
        db.add(SubjectRequirement(class_group_id=cg.id, subject_id=chem.id, periods_per_week=1))
        db.commit()
        w = {"school": sid, "chem": chem.id, "cg": cg.id}
    finally:
        db.close()

    def lab(tt_id):
        db = SessionLocal()
        try:
            return sorted((e.lab_batch, e.teacher_id, e.period_id)
                          for e in db.query(TimetableEntry).filter_by(timetable_id=tt_id))
        finally:
            db.close()

    first = generate(w)
    kept = lab(first)
    assert [b for b, _, _ in kept] == [1, 2]
    db = SessionLocal()
    try:
        day = db.get(Period, kept[0][2]).day_of_week
        db.add(Constraint(school_id=sid, type="ir", is_hard=False, weight=50, description="Not that day",
                          parameters={"form": "count", "scope": ["class_group"],
                                      "selector": {"subjects": ["Chemistry"], "days": [day]},
                                      "relation": "==", "value": 0, "strength": "strong_preference"}))
        db.commit()
    finally:
        db.close()
    assert freeze(client, w, h, subject="chem").status_code == 201
    second = generate(w)
    assert timetable(second)[0] == "draft", timetable(second)[1]
    assert lab(second) == kept
    # Unfrozen, the rule moves it - so it was the freeze that kept it.
    f = statuses(client, w, h)[0]
    client.delete(f"/api/subject-freezes/{f['id']}?school_id={sid}", headers=h)
    third = generate(w)
    db = SessionLocal()
    try:
        assert {db.get(Period, p).day_of_week for _, _, p in lab(third)} == {1 - day}
    finally:
        db.close()


def test_a_freeze_wins_over_a_lock_on_the_same_lessons(client, world):
    """Locked Maths in one version, Maths frozen from another: the freeze is
    what's kept - pinning both would ask for Maths four times."""
    from app.models.school import School

    w, h = world
    first = generate(w)
    kept = rows(first, subject=w["maths"])
    make_unavailable(w["rao"], {kept[0][3]})
    second = generate(w)
    assert rows(second, subject=w["maths"]) != kept
    db = SessionLocal()
    try:
        for e in db.query(TimetableEntry).filter_by(timetable_id=second, subject_id=w["maths"]):
            e.locked = True
        db.get(School, w["school"]).current_timetable_id = first
        db.commit()
    finally:
        db.close()
    assert freeze(client, w, h).status_code == 201
    db = SessionLocal()
    try:
        db.get(School, w["school"]).current_timetable_id = second
        db.commit()
    finally:
        db.close()
    third = generate(w)
    assert timetable(third)[0] == "draft", timetable(third)[1]
    assert rows(third, subject=w["maths"]) == kept

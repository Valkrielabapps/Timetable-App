"""
Small changes without rebuilding: every lesson that's still right stays
where it is, and only what changed is placed.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Subject, SubjectRequirement, Teacher, Timetable, TimetableEntry
from app.routers.timetable_updates import _run_update_job
from app.routers.timetables import _run_generation_job
from app.schemas.timetable_structure import TimetableStructure
from app.services.timetable_structure import apply
from tests.conftest import create_school, signup


@pytest.fixture
def world(client):
    """Two days of five periods; 6A and 6B each have Maths 3, English 3,
    Science 2. Ravi teaches Maths too but has nothing yet."""
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        apply(db, sid, TimetableStructure(days=[0, 1], periods_per_day=5))
        subj = {n: Subject(school_id=sid, name=n) for n in ("Maths", "English", "Science")}
        db.add_all(subj.values())
        db.commit()
        t = {
            "rao": Teacher(school_id=sid, name="Rao", qualified_subject_ids=[subj["Maths"].id]),
            "ravi": Teacher(school_id=sid, name="Ravi", qualified_subject_ids=[subj["Maths"].id]),
            "iyer": Teacher(school_id=sid, name="Iyer", qualified_subject_ids=[subj["English"].id]),
            "das": Teacher(school_id=sid, name="Das", qualified_subject_ids=[subj["Science"].id]),
        }
        a, b = ClassGroup(school_id=sid, grade="Grade 6", name="A"), ClassGroup(school_id=sid, grade="Grade 6", name="B")
        db.add_all([*t.values(), a, b])
        db.commit()
        for cg in (a, b):
            for name, n, who in (("Maths", 3, "rao"), ("English", 3, "iyer"), ("Science", 2, "das")):
                db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subj[name].id, periods_per_week=n,
                                          preferred_teacher_id=t[who].id))
        db.commit()
        w = {"school": sid, "a": a.id, "b": b.id, **{k: v.id for k, v in t.items()},
             **{k.lower(): v.id for k, v in subj.items()}}
    finally:
        db.close()
    w["first"] = _job(w, _run_generation_job)
    return w, h


def _job(w, run) -> int:
    db = SessionLocal()
    try:
        tt = Timetable(school_id=w["school"], status="generating")
        db.add(tt)
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    run(tt_id, w["school"])
    return tt_id


def _lessons(tt_id):
    db = SessionLocal()
    try:
        tt = db.get(Timetable, tt_id)
        return tt.status, sorted((e.class_group_id, e.subject_id, e.teacher_id, e.period_id) for e in tt.entries), \
            (tt.generation_notes or {}).get("update")
    finally:
        db.close()


def test_nothing_changed_says_so(client, world):
    w, h = world
    r = client.get(f"/api/timetable-updates/changes?school_id={w['school']}", headers=h).json()
    assert r["changes"] == [] and r["timetable_id"] == w["first"]


def test_one_more_period_keeps_every_other_lesson(client, world):
    w, h = world
    db = SessionLocal()
    try:
        db.query(SubjectRequirement).filter_by(class_group_id=w["a"], subject_id=w["maths"]).update({"periods_per_week": 4})
        db.commit()
    finally:
        db.close()
    r = client.get(f"/api/timetable-updates/changes?school_id={w['school']}", headers=h).json()
    assert [c["text"] for c in r["changes"]] == ["Grade 6 A: Maths 3 → 4 periods a week"]

    _, before, _ = _lessons(w["first"])
    second = _job(w, _run_update_job)
    status, after, note = _lessons(second)
    assert status == "draft"
    assert set(before) <= set(after)  # every lesson where it was
    assert len(after) == len(before) + 1
    assert note["stage"] == 1 and note["placed"] == 1 and note["unchanged"] == len(before)
    assert client.get(f"/api/timetable-updates/changes?school_id={w['school']}", headers=h).json()["changes"] == []


def test_replacing_a_teacher_who_is_free_changes_nothing_else(client, world):
    w, h = world
    _, before, _ = _lessons(w["first"])
    r = client.post("/api/timetable-updates/replace-teacher", json={
        "school_id": w["school"], "from_teacher_id": w["rao"], "to_teacher_id": w["ravi"]}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["swapped"], r.json()["left"], r.json()["plan"]) == (6, 0, 2)
    assert r.json()["changes"] == []
    _, after, _ = _lessons(w["first"])  # the same version, edited in place
    assert after == sorted((cg, s, w["ravi"] if t == w["rao"] else t, p) for cg, s, t, p in before)
    db = SessionLocal()
    try:
        assert {r.preferred_teacher_id for r in db.query(SubjectRequirement).filter_by(subject_id=w["maths"])} == {w["ravi"]}
    finally:
        db.close()


def test_replacing_with_a_busy_teacher_leaves_only_the_clashes_to_place(client, world):
    w, h = world
    db = SessionLocal()
    try:
        # Das can teach English too, but already teaches Science.
        das = db.get(Teacher, w["das"])
        das.qualified_subject_ids = [w["science"], w["english"]]
        db.commit()
    finally:
        db.close()
    r = client.post("/api/timetable-updates/replace-teacher", json={
        "school_id": w["school"], "from_teacher_id": w["iyer"], "to_teacher_id": w["das"],
        "class_group_ids": [w["a"]]}, headers=h).json()
    assert r["swapped"] + r["left"] == 3
    if r["left"]:
        assert any("now taught by Das (was Iyer)" in c["text"] for c in r["changes"])
    _, before, _ = _lessons(w["first"])
    second = _job(w, _run_update_job)
    status, after, note = _lessons(second)
    assert status == "draft"
    english_a = [row for row in after if row[0] == w["a"] and row[1] == w["english"]]
    assert len(english_a) == 3 and {row[2] for row in english_a} == {w["das"]}
    das_periods = [row[3] for row in after if row[2] == w["das"]]
    assert len(das_periods) == len(set(das_periods))  # never two places at once
    # 6B is untouched.
    assert [x for x in after if x[0] == w["b"]] == [x for x in before if x[0] == w["b"]]
    assert note["unchanged"] >= len(before) - 2 * r["left"] - 2


def test_a_viewer_can_look_but_not_change(client, world):
    w, _ = world
    _, other = signup(client, email="v@x.com")
    assert client.post(f"/api/timetable-updates/update?school_id={w['school']}", headers=other).status_code in (403, 404)
    assert client.post("/api/timetable-updates/replace-teacher", json={
        "school_id": w["school"], "from_teacher_id": w["rao"], "to_teacher_id": w["ravi"]}, headers=other).status_code in (403, 404)

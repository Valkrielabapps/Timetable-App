"""A group in an elective block given to two or more named teachers shares its
block periods between them, like a shared subject outside a block."""
from collections import Counter

from app.models.school import ElectiveBlock, ElectiveOption
from app.services.solver import generate_school_timetable
from tests.conftest import create_school, signup
from tests.test_ir_end_to_end import _class_group, _school, _subject, _teacher, db  # noqa: F401


def _block(db, school, periods, shared=True):  # noqa: F811
    bio = _subject(db, school, "Biology")
    cs = _subject(db, school, "Computer Science")
    anu = _teacher(db, school, "Anu", [bio.id])
    ravi = _teacher(db, school, "Ravi", [bio.id])
    meena = _teacher(db, school, "Meena", [cs.id])
    cg = _class_group(db, school, grade="Grade 11", name="A")
    db.add(ElectiveBlock(
        school_id=school.id, class_group_id=cg.id, name="Bio / CS", periods_per_week=periods,
        options=[
            ElectiveOption(subject_id=bio.id, allowed_teacher_ids=[anu.id, ravi.id] if shared else None),
            ElectiveOption(subject_id=cs.id),
        ],
    ))
    db.commit()
    return bio, anu, ravi, meena


def test_a_shared_group_splits_its_block_periods_between_its_teachers(db):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    bio, anu, ravi, meena = _block(db, school, 6)
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    bio_counts = Counter(a["teacher_id"] for a in result.assignments if a["subject_id"] == bio.id)
    assert bio_counts[anu.id] == 3 and bio_counts[ravi.id] == 3
    assert Counter(a["teacher_id"] for a in result.assignments)[meena.id] == 6


def test_without_a_list_one_teacher_takes_the_whole_group(db):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    bio, anu, ravi, _ = _block(db, school, 6, shared=False)
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    bio_teachers = {a["teacher_id"] for a in result.assignments if a["subject_id"] == bio.id}
    assert len(bio_teachers) == 1


def test_the_api_keeps_two_or_more_teachers_and_drops_a_single_one(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    cg = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 11", "name": "A"}, headers=h).json()
    bio = client.post("/api/subjects", json={"school_id": sid, "name": "Biology"}, headers=h).json()
    cs = client.post("/api/subjects", json={"school_id": sid, "name": "CS"}, headers=h).json()
    t1 = client.post("/api/teachers", json={"school_id": sid, "name": "Anu"}, headers=h).json()
    t2 = client.post("/api/teachers", json={"school_id": sid, "name": "Ravi"}, headers=h).json()
    r = client.post("/api/elective-blocks", headers=h, json={
        "school_id": sid, "class_group_id": cg["id"], "name": "Bio / CS", "periods_per_week": 4,
        "options": [
            {"subject_id": bio["id"], "allowed_teacher_ids": [t1["id"], t2["id"], t1["id"]]},
            {"subject_id": cs["id"], "allowed_teacher_ids": [t1["id"]]},
        ],
    })
    assert r.status_code == 201, r.text
    opts = {o["subject_id"]: o for o in r.json()["options"]}
    assert opts[bio["id"]]["allowed_teacher_ids"] == [t1["id"], t2["id"]]
    assert opts[cs["id"]]["allowed_teacher_ids"] is None

    # Deleting a shared teacher leaves the other one pinned.
    assert client.delete(f"/api/teachers/{t2['id']}", headers=h).status_code in (200, 204)
    block = client.get(f"/api/elective-blocks?school_id={sid}", headers=h).json()[0]
    bio_opt = next(o for o in block["options"] if o["subject_id"] == bio["id"])
    assert bio_opt["allowed_teacher_ids"] is None and bio_opt["preferred_teacher_id"] == t1["id"]

"""Copying one section's periods/week to other sections in one request."""
from tests.conftest import create_school, signup


def _setup(client):
    _, h = signup(client)
    school = create_school(client, h)
    sid = school["id"]
    cgs = [client.post("/api/class-groups", json={"school_id": sid, "grade": "8", "name": n}, headers=h).json() for n in "ABCD"]
    subs = [client.post("/api/subjects", json={"school_id": sid, "name": n}, headers=h).json() for n in ("Maths", "Science", "Art")]
    return h, sid, cgs, subs


def _req(client, h, cg, sub, n):
    r = client.post(f"/api/class-groups/{cg['id']}/requirements", headers=h,
                    json={"class_group_id": cg["id"], "subject_id": sub["id"], "periods_per_week": n})
    assert r.status_code == 201, r.text
    return r.json()


def _plan(client, h, cg):
    return {r["subject_id"]: r for r in client.get(f"/api/class-groups/{cg['id']}/requirements", headers=h).json()}


def test_copies_to_many_sections_in_one_request(client):
    h, _, (a, b, c, d), (maths, sci, art) = _setup(client)
    _req(client, h, a, maths, 8)
    _req(client, h, a, sci, 6)
    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h,
                    json={"target_ids": [b["id"], c["id"], d["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 6
    for cg in (b, c, d):
        plan = _plan(client, h, cg)
        assert plan[maths["id"]]["periods_per_week"] == 8 and plan[sci["id"]]["periods_per_week"] == 6


def test_only_selected_subjects_and_keeps_existing_teacher(client):
    h, sid, (a, b, *_), (maths, sci, _art) = _setup(client)
    teacher = client.post("/api/teachers", headers=h, json={"school_id": sid, "name": "Rao", "qualified_subject_ids": [maths["id"]]}).json()
    _req(client, h, a, maths, 8)
    _req(client, h, a, sci, 6)
    existing = _req(client, h, b, maths, 3)
    client.put(f"/api/class-groups/requirements/{existing['id']}", headers=h, json={"preferred_teacher_id": teacher["id"]})

    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h,
                    json={"target_ids": [b["id"]], "subject_ids": [maths["id"]]})
    assert r.json()["updated"] == 1 and r.json()["created"] == 0
    plan = _plan(client, h, b)
    assert plan[maths["id"]]["periods_per_week"] == 8
    assert plan[maths["id"]]["preferred_teacher_id"] == teacher["id"]
    assert sci["id"] not in plan


def test_other_schools_sections_are_ignored(client):
    h, _, (a, *_), (maths, *_rest) = _setup(client)
    _req(client, h, a, maths, 8)
    _, h2 = signup(client, email="other@x.com")
    other = create_school(client, h2)
    foreign = client.post("/api/class-groups", json={"school_id": other["id"], "name": "Z"}, headers=h2).json()
    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [foreign["id"]]})
    assert r.status_code == 400
    assert _plan(client, h2, foreign) == {}

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


# ---------------------------------------------------------------------------
# Elective blocks come along
# ---------------------------------------------------------------------------


def _subject(client, h, sid, name):
    return client.post("/api/subjects", json={"school_id": sid, "name": name}, headers=h).json()


def _block(client, h, sid, cg, name, subjects, ppw=3, teachers=None):
    teachers = teachers or {}
    r = client.post("/api/elective-blocks", headers=h, json={
        "school_id": sid, "class_group_id": cg["id"], "name": name, "periods_per_week": ppw,
        "options": [{"subject_id": s["id"], "preferred_teacher_id": teachers.get(s["id"])} for s in subjects],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _blocks(client, h, sid, cg):
    return [b for b in client.get(f"/api/elective-blocks?school_id={sid}", headers=h).json() if b["class_group_id"] == cg["id"]]


def test_elective_blocks_are_copied_with_the_subjects(client):
    h, sid, (a, b, c, _d), (maths, *_rest) = _setup(client)
    french, sanskrit = _subject(client, h, sid, "French"), _subject(client, h, sid, "Sanskrit")
    _req(client, h, a, maths, 8)
    _block(client, h, sid, a, "Third language", [french, sanskrit], ppw=3)

    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [b["id"], c["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["blocks_created"] == 2 and r.json()["skipped"] == []
    for cg in (b, c):
        (block,) = _blocks(client, h, sid, cg)
        assert block["name"] == "Third language" and block["periods_per_week"] == 3
        assert sorted(o["subject_id"] for o in block["options"]) == sorted([french["id"], sanskrit["id"]])
        assert _plan(client, h, cg)[maths["id"]]["periods_per_week"] == 8


def test_a_section_with_only_blocks_can_be_copied(client):
    h, sid, (a, b, *_), _subs = _setup(client)
    x, y = _subject(client, h, sid, "Biology"), _subject(client, h, sid, "Computer Science")
    _block(client, h, sid, a, "Science elective", [x, y], ppw=7)
    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [b["id"]]})
    assert r.status_code == 200, r.text
    assert len(_blocks(client, h, sid, b)) == 1


def test_a_same_named_block_is_updated_and_keeps_its_teachers(client):
    h, sid, (a, b, *_), _subs = _setup(client)
    french, sanskrit, malayalam = (_subject(client, h, sid, n) for n in ("French", "Sanskrit", "Malayalam"))
    claire = client.post("/api/teachers", headers=h, json={"school_id": sid, "name": "Claire", "qualified_subject_ids": [french["id"]]}).json()
    _block(client, h, sid, a, "Third language", [french, sanskrit, malayalam], ppw=4)
    _block(client, h, sid, b, "third language", [french, sanskrit], ppw=2, teachers={french["id"]: claire["id"]})

    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [b["id"]]})
    assert r.json()["blocks_updated"] == 1 and r.json()["blocks_created"] == 0
    (block,) = _blocks(client, h, sid, b)
    assert block["periods_per_week"] == 4
    by_subject = {o["subject_id"]: o for o in block["options"]}
    assert set(by_subject) == {french["id"], sanskrit["id"], malayalam["id"]}
    assert by_subject[french["id"]]["preferred_teacher_id"] == claire["id"]


def test_a_block_that_would_clash_is_skipped_and_reported(client):
    h, sid, (a, b, *_), (maths, *_rest) = _setup(client)
    french = _subject(client, h, sid, "French")
    _block(client, h, sid, a, "Options", [maths, french])
    _req(client, h, b, maths, 5)  # Maths is a common subject in B

    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [b["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["blocks_created"] == 0
    assert any("Options" in s and "Maths" in s for s in r.json()["skipped"])
    assert _blocks(client, h, sid, b) == []


def test_blocks_can_be_left_out(client):
    h, sid, (a, b, *_), (maths, *_rest) = _setup(client)
    x, y = _subject(client, h, sid, "French"), _subject(client, h, sid, "Sanskrit")
    _req(client, h, a, maths, 8)
    _block(client, h, sid, a, "Third language", [x, y])
    client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h, json={"target_ids": [b["id"]], "include_blocks": False})
    assert _blocks(client, h, sid, b) == []


def test_only_the_ticked_block_and_no_subjects(client):
    h, sid, (a, b, *_), (maths, *_rest) = _setup(client)
    x, y, z, w = (_subject(client, h, sid, n) for n in ("French", "Sanskrit", "Biology", "Computer Science"))
    _req(client, h, a, maths, 8)
    _block(client, h, sid, a, "Third language", [x, y])
    second = _block(client, h, sid, a, "Science elective", [z, w])
    r = client.post(f"/api/class-groups/{a['id']}/requirements/copy", headers=h,
                    json={"target_ids": [b["id"]], "subject_ids": [], "block_ids": [second["id"]]})
    assert r.status_code == 200, r.text
    assert [blk["name"] for blk in _blocks(client, h, sid, b)] == ["Science elective"]
    assert _plan(client, h, b) == {}

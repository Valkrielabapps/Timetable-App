"""A teacher whose list still names a deleted subject can still be edited."""
from app.models.school import Subject
from tests.conftest import create_school, signup


def _setup(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    eng = client.post("/api/subjects", json={"school_id": sid, "name": "English"}, headers=h).json()
    old = client.post("/api/subjects", json={"school_id": sid, "name": "Old"}, headers=h).json()
    eng2 = client.post("/api/subjects", json={"school_id": sid, "name": "ENG2"}, headers=h).json()
    t = client.post("/api/teachers", json={"school_id": sid, "name": "Joseph",
                                           "qualified_subject_ids": [eng["id"], old["id"]]}, headers=h).json()
    return h, sid, eng, old, eng2, t


def test_deleting_a_subject_takes_it_off_teachers(client):
    h, sid, eng, old, _, t = _setup(client)
    assert client.delete(f"/api/subjects/{old['id']}", headers=h).status_code == 204
    me = next(x for x in client.get(f"/api/teachers?school_id={sid}", headers=h).json() if x["id"] == t["id"])
    assert me["qualified_subject_ids"] == [eng["id"]]


def test_a_stale_subject_id_is_dropped_not_refused(client):
    from app.core.database import SessionLocal
    h, sid, eng, old, eng2, t = _setup(client)
    # A list left over from before deletion cleaned up teachers: the id of a
    # subject that is gone is still on Joseph.
    db = SessionLocal()
    db.query(Subject).filter(Subject.id == old["id"]).delete()
    db.commit()
    db.close()
    r = client.put(f"/api/teachers/{t['id']}", headers=h,
                   json={"qualified_subject_ids": [eng["id"], old["id"], eng2["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["qualified_subject_ids"] == [eng["id"], eng2["id"]]


def test_another_schools_subject_is_not_added(client):
    h, sid, eng, _, _, t = _setup(client)
    _, h2 = signup(client, email="other@example.com")
    sid2 = create_school(client, h2)["id"]
    theirs = client.post("/api/subjects", json={"school_id": sid2, "name": "Secret"}, headers=h2).json()
    r = client.put(f"/api/teachers/{t['id']}", headers=h, json={"qualified_subject_ids": [eng["id"], theirs["id"]]})
    assert r.status_code == 404

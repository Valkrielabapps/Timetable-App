"""Deleting several rules at once (Select mode on the Constraints tab)."""
from app.core.database import SessionLocal
from app.models.school import Constraint, Teacher
from tests.conftest import create_school, signup


def _rule(sid, **kw):
    db = SessionLocal()
    try:
        c = Constraint(school_id=sid, type=kw.pop("type", "ir"), parameters=kw.pop("parameters", {}),
                       description=kw.pop("description", "a rule"))
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def test_deletes_the_chosen_rules_only(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    a, b, keep = (_rule(sid, description=n) for n in ("A", "B", "Keep"))
    r = client.post("/api/constraints/delete-many", headers=h, json={"school_id": sid, "ids": [a, b]})
    assert r.status_code == 200 and r.json()["deleted"] == 2
    left = [c["id"] for c in client.get(f"/api/constraints?school_id={sid}", headers=h).json()]
    assert left == [keep]


def test_rules_from_another_school_are_untouched(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    _, h2 = signup(client, email="other@x.com")
    other = create_school(client, h2)["id"]
    theirs = _rule(other)
    r = client.post("/api/constraints/delete-many", headers=h, json={"school_id": sid, "ids": [theirs]})
    assert r.json()["deleted"] == 0
    assert len(client.get(f"/api/constraints?school_id={other}", headers=h2).json()) == 1


def test_deleting_both_copies_of_a_workload_rule_clears_the_cap(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    t = client.post("/api/teachers", headers=h, json={"school_id": sid, "name": "Rao", "max_periods_per_week": 12}).json()
    ids = [_rule(sid, type="workload_limit", parameters={"teacher_id": t["id"], "max_periods_per_week": 12}) for _ in range(2)]
    client.post("/api/constraints/delete-many", headers=h, json={"school_id": sid, "ids": ids})
    db = SessionLocal()
    try:
        assert db.get(Teacher, t["id"]).max_periods_per_week is None
    finally:
        db.close()


def test_viewers_cannot_delete(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    rid = _rule(sid)
    token = client.post(f"/api/schools/{sid}/invites", json={"email": "v@a.com", "role": "viewer"}, headers=h).json()["token"]
    v = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"}).json()
    vh = {"Authorization": f"Bearer {v['access_token']}"}
    assert client.post("/api/constraints/delete-many", headers=vh, json={"school_id": sid, "ids": [rid]}).status_code == 403

"""Plan catalogue, lifecycle (active / grace / expired) and enforcement."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.school import School
from app.services import plans
from tests.conftest import create_school, signup


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "plan_limits_enabled", True)


def _set_plan(school_id, plan, valid_until):
    db = SessionLocal()
    try:
        s = db.get(School, school_id)
        s.plan = plan
        s.plan_valid_until = valid_until
        db.commit()
    finally:
        db.close()


def _add_section(client, h, school_id, name):
    return client.post("/api/class-groups", json={"school_id": school_id, "name": name, "grade": "8"}, headers=h)


def test_catalogue_is_public_and_uses_sections(client):
    r = client.get("/api/plans")
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()["plans"]}
    assert by_id["free"]["max_sections"] == 5
    assert by_id["pro"]["max_sections"] == 60 and by_id["pro"]["price_inr"] == 4999
    assert by_id["business"]["sold_online"] is False
    assert r.json()["grace_days"] == 15


@pytest.mark.parametrize("offset_days,status,plan", [
    (30, "active", "pro"),
    (-5, "grace", "pro"),
    (-16, "locked", "free"),
])
def test_lifecycle(offset_days, status, plan):
    s = School(name="x", plan="pro", plan_valid_until=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=offset_days))
    effective, got_status, _ = plans.effective_plan(s)
    assert (effective.id, got_status) == (plan, status)


def test_business_without_end_date_never_expires():
    effective, status, _ = plans.effective_plan(School(name="x", plan="business", plan_valid_until=None))
    assert (effective.id, status) == ("business", "active")


def test_free_school_stops_at_five_sections(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    for i in range(5):
        assert _add_section(client, h, school["id"], f"S{i}").status_code == 201
    r = _add_section(client, h, school["id"], "S5")
    assert r.status_code == 402
    assert "5 sections" in r.json()["detail"] and "Pro" in r.json()["detail"]


def test_pro_school_can_add_more(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _set_plan(school["id"], "pro", datetime.utcnow() + timedelta(days=100))
    for i in range(7):
        assert _add_section(client, h, school["id"], f"S{i}").status_code == 201


def test_grace_keeps_pro_limits_and_expiry_drops_to_free(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _set_plan(school["id"], "pro", datetime.utcnow() - timedelta(days=3))
    for i in range(6):
        assert _add_section(client, h, school["id"], f"S{i}").status_code == 201
    ent = client.get(f"/api/schools/{school['id']}/entitlements", headers=h).json()
    assert ent["status"] == "grace" and ent["plan"] == "pro"

    _set_plan(school["id"], "pro", datetime.utcnow() - timedelta(days=20))
    ent = client.get(f"/api/schools/{school['id']}/entitlements", headers=h).json()
    assert ent["status"] == "locked"
    # Locked: nothing is taken away and it can still be read, but nothing changes.
    assert ent["usage"]["sections"] == 6
    r = _add_section(client, h, school["id"], "S6")
    assert r.status_code == 402 and "free period has ended" in r.json()["detail"]
    assert len(client.get(f"/api/class-groups?school_id={school['id']}", headers=h).json()) == 6


def test_bulk_import_stops_at_the_limit_and_says_so(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    csv = "name,grade\n" + "\n".join(f"S{i},8" for i in range(8))
    r = client.post("/api/class-groups/bulk-import", data={"school_id": school["id"]},
                    files={"file": ("s.csv", csv, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 5
    assert any("3 sections not added" in e for e in r.json()["errors"])


def test_free_plan_cannot_invite(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    r = client.post(f"/api/schools/{school['id']}/invites", json={"email": "x@y.com", "role": "viewer"}, headers=h)
    assert r.status_code == 402


def test_pro_plan_allows_invites_up_to_five_people(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _set_plan(school["id"], "pro", datetime.utcnow() + timedelta(days=100))
    for i in range(4):
        r = client.post(f"/api/schools/{school['id']}/invites", json={"email": f"p{i}@y.com", "role": "viewer"}, headers=h)
        assert r.status_code == 201, r.text
    r = client.post(f"/api/schools/{school['id']}/invites", json={"email": "p5@y.com", "role": "viewer"}, headers=h)
    assert r.status_code == 402


def test_one_school_per_account(client, limits_on):
    _, h = signup(client)
    create_school(client, h)
    r = client.post("/api/schools", json={"name": "Second"}, headers=h)
    assert r.status_code == 402


def test_business_owner_can_add_schools(client, limits_on):
    _, h = signup(client)
    first = create_school(client, h)
    _set_plan(first["id"], "business", None)
    assert client.post("/api/schools", json={"name": "Second"}, headers=h).status_code == 201


def test_ai_allowance_counts_and_resets_monthly(limits_on, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    db = SessionLocal()
    try:
        s = School(name="ai")
        db.add(s)
        db.commit()
        assert all(plans.use_ai(db, s) for _ in range(10))
        assert plans.use_ai(db, s) is False
        s.ai_usage_month = "2000-01"  # a past month: allowance starts again
        db.commit()
        assert plans.use_ai(db, s) is True
        s.plan, s.plan_valid_until = "pro", datetime.utcnow() + timedelta(days=10)
        db.commit()
        assert all(plans.use_ai(db, s) for _ in range(50))  # unlimited on Pro
    finally:
        db.close()


def test_payment_price_comes_from_the_catalogue(monkeypatch):
    from app.routers.payments import _price_rupees
    monkeypatch.setattr(settings, "pro_plan_price_inr", 1)
    assert _price_rupees("pro") == 1
    with pytest.raises(Exception):
        _price_rupees("business")


def _set_trial_end(school_id, when):
    db = SessionLocal()
    try:
        db.get(School, school_id).free_trial_ends_at = when
        db.commit()
    finally:
        db.close()


def test_new_school_gets_fourteen_free_days(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    ent = client.get(f"/api/schools/{school['id']}/entitlements", headers=h).json()
    assert ent["status"] == "free"
    assert ent["free_days_left"] == 14


def test_after_fourteen_days_an_unpaid_school_is_locked(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _add_section(client, h, school["id"], "A")
    _set_trial_end(school["id"], datetime.utcnow() - timedelta(minutes=1))

    ent = client.get(f"/api/schools/{school['id']}/entitlements", headers=h).json()
    assert ent["status"] == "locked"
    assert _add_section(client, h, school["id"], "B").status_code == 402
    assert client.put(f"/api/schools/{school['id']}/name", json={"name": "New"}, headers=h).status_code == 402
    # Reading still works, so the school can see what it has.
    assert len(client.get(f"/api/class-groups?school_id={school['id']}", headers=h).json()) == 1
    # Paying is never blocked by the lock (503 here = past the lock, payments not configured).
    r = client.post("/api/payments/create-order", json={"school_id": school["id"], "phone": "9876543210"}, headers=h)
    assert r.status_code == 503


def test_paying_unlocks(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _set_trial_end(school["id"], datetime.utcnow() - timedelta(days=1))
    assert _add_section(client, h, school["id"], "A").status_code == 402
    _set_plan(school["id"], "pro", datetime.utcnow() + timedelta(days=365))
    assert _add_section(client, h, school["id"], "A").status_code == 201

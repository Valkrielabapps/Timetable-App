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
    # The 14-day trial has everything unlocked.
    assert by_id["free"]["max_sections"] is None and by_id["free"]["listed"] is False
    assert (by_id["starter"]["max_sections"], by_id["starter"]["price_inr"], by_id["starter"]["done_for_you_inr"]) == (30, 9999, 17999)
    assert (by_id["standard"]["max_sections"], by_id["standard"]["price_inr"], by_id["standard"]["done_for_you_inr"]) == (50, 14999, 26999)
    assert (by_id["plus"]["max_sections"], by_id["plus"]["price_inr"], by_id["plus"]["done_for_you_inr"]) == (80, 19999, 34999)
    assert by_id["business"]["name"] == "Large / Group" and by_id["business"]["sold_online"] is False
    assert by_id["pro"]["listed"] is False and by_id["pro"]["sold_online"] is False  # kept for earlier buyers
    for pid in ("starter", "standard", "plus"):
        assert by_id[pid]["max_members"] is None and by_id[pid]["ai_actions_per_month"] is None
    assert r.json()["grace_days"] == 15


def test_large_price_and_the_plan_a_school_fits():
    assert plans.large_price(80) == 19999 and plans.large_price(100) == 24999
    assert plans.plan_for_sections(30).id == "starter"
    assert plans.plan_for_sections(31).id == "standard"
    assert plans.plan_for_sections(80).id == "plus"
    assert plans.plan_for_sections(81) is None


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


def test_starter_stops_at_thirty_sections_and_names_the_next_plan(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    _set_plan(school["id"], "starter", datetime.utcnow() + timedelta(days=100))
    for i in range(30):
        assert _add_section(client, h, school["id"], f"S{i}").status_code == 201
    r = _add_section(client, h, school["id"], "S30")
    assert r.status_code == 402
    assert "30 sections" in r.json()["detail"] and "Standard (₹14,999 a year" in r.json()["detail"]


def test_the_trial_has_no_section_limit(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    for i in range(35):
        assert _add_section(client, h, school["id"], f"S{i}").status_code == 201


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
    _set_plan(school["id"], "starter", datetime.utcnow() + timedelta(days=100))
    csv = "name,grade\n" + "\n".join(f"S{i},8" for i in range(33))
    r = client.post("/api/class-groups/bulk-import", data={"school_id": school["id"]},
                    files={"file": ("s.csv", csv, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 30
    assert any("3 sections not added" in e for e in r.json()["errors"])


def test_trial_and_new_plans_can_invite_anyone(client, limits_on):
    _, h = signup(client)
    school = create_school(client, h)
    for i in range(7):
        r = client.post(f"/api/schools/{school['id']}/invites", json={"email": f"x{i}@y.com", "role": "viewer"}, headers=h)
        assert r.status_code == 201, r.text


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


def test_ai_is_unlimited_on_the_trial_and_every_plan(limits_on, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    db = SessionLocal()
    try:
        s = School(name="ai")
        db.add(s)
        db.commit()
        assert all(plans.use_ai(db, s) for _ in range(50))
        s.plan, s.plan_valid_until = "starter", datetime.utcnow() + timedelta(days=10)
        db.commit()
        assert all(plans.use_ai(db, s) for _ in range(50))
    finally:
        db.close()


def test_payment_price_comes_from_the_catalogue():
    from app.routers.payments import _price_rupees
    assert _price_rupees("starter") == 9999 and _price_rupees("starter", "done_for_you") == 17999
    assert _price_rupees("plus", "done_for_you") == 34999
    for gone in ("pro", "business", "free"):
        with pytest.raises(Exception):
            _price_rupees(gone)


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

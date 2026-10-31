"""Custom offers, the admin page's actions, and invoices."""
import base64
import hashlib
import hmac
import json

import pytest

from app.core.config import settings
from app.services import cashfree_service
from tests.conftest import verify_email, create_school, signup

ADMIN = "staff@timetablz.com"


@pytest.fixture
def staff(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", ADMIN)
    monkeypatch.setattr(settings, "plan_limits_enabled", True)
    _, h = signup(client, email=ADMIN)
    verify_email(ADMIN)
    return h


def _school(client, email="head@school.in"):
    _, h = signup(client, email=email)
    return create_school(client, h, name="Sunrise School"), h


def _ent(client, h, sid):
    return client.get(f"/api/schools/{sid}/entitlements", headers=h).json()


def test_admin_api_is_hidden_from_everyone_else(client, staff):
    _, h = _school(client)
    assert client.get("/api/admin/schools", headers=h).status_code == 404
    assert client.get("/api/auth/me", headers=h).json()["is_platform_admin"] is False
    assert client.get("/api/auth/me", headers=staff).json()["is_platform_admin"] is True


def test_admin_lists_schools_with_status(client, staff):
    school, _ = _school(client)
    rows = client.get("/api/admin/schools", headers=staff).json()
    row = next(r for r in rows if r["id"] == school["id"])
    assert row["owner_email"] == "head@school.in"
    assert row["status"] == "free" and row["free_days_left"] == 14


def test_school_sees_the_offer_and_mark_paid_applies_it(client, staff):
    school, h = _school(client)
    r = client.post(f"/api/admin/schools/{school['id']}/offers", headers=staff, json={
        "name": "Sunrise Business", "price_inr": 18000, "period_days": 365, "max_sections": 150, "max_members": 15,
    })
    assert r.status_code == 201, r.text
    ent = _ent(client, h, school["id"])
    assert ent["offer"]["price_inr"] == 18000 and ent["offer"]["max_sections"] == 150

    r = client.post(f"/api/admin/schools/{school['id']}/mark-paid", headers=staff,
                    json={"kind": "offer", "amount_inr": 18000, "reference": "UTR123"})
    assert r.status_code == 200, r.text
    assert r.json()["invoice"]["number"].startswith("TZ-")

    ent = _ent(client, h, school["id"])
    assert ent["status"] == "active" and ent["plan"] == "business"
    assert ent["plan_name"] == "Sunrise Business"
    assert ent["limits"]["max_sections"] == 150 and ent["limits"]["max_members"] == 15
    assert ent["offer"] is None  # paid, no longer open

    invoices = client.get(f"/api/schools/{school['id']}/invoices", headers=h).json()
    assert len(invoices) == 1 and invoices[0]["amount"] == 18000 and invoices[0]["method"] == "bank_transfer"
    pdf = client.get(f"/api/invoices/{invoices[0]['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_invoice_numbers_are_sequential_and_private(client, staff):
    a, ha = _school(client, "a@a.in")
    b, hb = _school(client, "b@b.in")
    for sid in (a["id"], b["id"]):
        client.post(f"/api/admin/schools/{sid}/mark-paid", headers=staff, json={"kind": "pro", "amount_inr": 4999})
    numbers = [i["number"] for i in client.get("/api/admin/invoices", headers=staff).json()]
    assert sorted(numbers)[1].endswith("0002")
    inv_a = client.get(f"/api/schools/{a['id']}/invoices", headers=ha).json()[0]
    assert client.get(f"/api/invoices/{inv_a['id']}/pdf", headers=hb).status_code == 404


def test_new_offer_replaces_the_old_one(client, staff):
    school, h = _school(client)
    first = client.post(f"/api/admin/schools/{school['id']}/offers", headers=staff, json={"name": "One", "price_inr": 10000}).json()
    client.post(f"/api/admin/schools/{school['id']}/offers", headers=staff, json={"name": "Two", "price_inr": 12000})
    assert _ent(client, h, school["id"])["offer"]["name"] == "Two"
    assert client.delete(f"/api/admin/offers/{first['id']}", headers=staff).status_code == 409


def test_extend_free_unlocks_and_downgrade_ends_the_plan(client, staff):
    from datetime import datetime, timedelta
    from app.core.database import SessionLocal
    from app.models.school import School

    school, h = _school(client)
    db = SessionLocal()
    db.get(School, school["id"]).free_trial_ends_at = datetime.utcnow() - timedelta(days=1)
    db.commit()
    db.close()
    assert _ent(client, h, school["id"])["status"] == "locked"

    client.post(f"/api/admin/schools/{school['id']}/extend-free", headers=staff, json={"days": 7})
    ent = _ent(client, h, school["id"])
    assert ent["status"] == "free" and ent["free_days_left"] == 7

    client.post(f"/api/admin/schools/{school['id']}/mark-paid", headers=staff, json={"kind": "pro", "amount_inr": 4999})
    assert _ent(client, h, school["id"])["plan"] == "pro"
    client.post(f"/api/admin/schools/{school['id']}/downgrade", headers=staff)
    assert _ent(client, h, school["id"])["status"] == "free"  # 7 free days still left


def test_paying_an_offer_online_uses_the_offer_price(client, staff, monkeypatch):
    monkeypatch.setattr(settings, "cashfree_app_id", "x")
    monkeypatch.setattr(settings, "cashfree_secret_key", "secret")
    sent = {}

    def fake_create(**kw):
        sent.update(kw)
        return cashfree_service.CreatedOrder(cf_order_id="cf", payment_session_id="s")

    monkeypatch.setattr(cashfree_service, "create_order", fake_create)
    monkeypatch.setattr(cashfree_service, "fetch_order",
                        lambda oid: cashfree_service.FetchedOrder(order_status="PAID", order_amount=18000.0, order_currency="INR"))
    school, h = _school(client)
    offer = client.post(f"/api/admin/schools/{school['id']}/offers", headers=staff,
                        json={"name": "Sunrise Business", "price_inr": 18000, "max_sections": 150}).json()
    r = client.post("/api/payments/create-order", headers=h,
                    json={"school_id": school["id"], "phone": "9876543210", "offer_id": offer["id"]})
    assert r.status_code == 201, r.text
    assert sent["amount_rupees"] == 18000
    status = client.get(f"/api/payments/orders/{r.json()['order_id']}", headers=h).json()
    assert status["status"] == "PAID"
    ent = _ent(client, h, school["id"])
    assert ent["plan"] == "business" and ent["limits"]["max_sections"] == 150
    assert len(client.get(f"/api/schools/{school['id']}/invoices", headers=h).json()) == 1


def test_cannot_pay_another_schools_offer(client, staff, monkeypatch):
    monkeypatch.setattr(settings, "cashfree_app_id", "x")
    monkeypatch.setattr(settings, "cashfree_secret_key", "secret")
    a, _ = _school(client, "a@a.in")
    b, hb = _school(client, "b@b.in")
    offer = client.post(f"/api/admin/schools/{a['id']}/offers", headers=staff, json={"name": "A deal", "price_inr": 100}).json()
    r = client.post("/api/payments/create-order", headers=hb,
                    json={"school_id": b["id"], "phone": "9876543210", "offer_id": offer["id"]})
    assert r.status_code == 404


def test_admin_is_only_valkyrie_by_default(client, monkeypatch):
    from app.core.config import Settings
    assert Settings().platform_admin_emails == "valkyrielabapps@gmail.com"


def test_stats_and_accounts(client, staff):
    school, _ = _school(client)
    client.post(f"/api/admin/schools/{school['id']}/mark-paid", headers=staff, json={"kind": "pro", "amount_inr": 4999})
    st = client.get("/api/admin/stats", headers=staff).json()
    assert st["schools"] == 1 and st["by_status"]["active"] == 1 and st["paying"]["pro"] == 1
    assert st["revenue_total_inr"] == 4999 and st["revenue_this_month_inr"] == 4999
    accts = client.get("/api/admin/accounts", headers=staff).json()
    head = next(a for a in accts if a["email"] == "head@school.in")
    assert head["owns"] == ["Sunrise School"]

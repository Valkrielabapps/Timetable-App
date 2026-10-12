"""
Cashfree checkout: create order, verify, webhook.

Cashfree itself is never called: the three functions in
app/services/cashfree_service.py that touch the network (create_order,
fetch_order, and the SDK client used by verify_webhook) are replaced. The
webhook tests still run the real signature check through the official SDK,
with a known test secret, so a broken HMAC would fail here.
"""
import base64
import hashlib
import hmac
import json

import pytest

from app.core.config import settings
from app.services import cashfree_service
from tests.conftest import create_school, signup

SECRET = "test_secret_key"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "cashfree_app_id", "TEST_APP_ID")
    monkeypatch.setattr(settings, "cashfree_secret_key", SECRET)
    monkeypatch.setattr(settings, "cashfree_env", "sandbox")
    monkeypatch.setattr(settings, "frontend_base_url", "https://www.timetablz.com")
    calls = {"create": [], "status": "ACTIVE", "amount": 4999.0}

    def fake_create(**kwargs):
        calls["create"].append(kwargs)
        return cashfree_service.CreatedOrder(cf_order_id="cf_1", payment_session_id="session_abc")

    def fake_fetch(order_id):
        return cashfree_service.FetchedOrder(order_status=calls["status"], order_amount=calls["amount"], order_currency="INR")

    monkeypatch.setattr(cashfree_service, "create_order", fake_create)
    monkeypatch.setattr(cashfree_service, "fetch_order", fake_fetch)
    return calls


def _start(client, headers, school_id, phone="98765 43210"):
    return client.post("/api/payments/create-order", json={"school_id": school_id, "phone": phone}, headers=headers)


def _signed(body: dict, timestamp="1700000000000"):
    raw = json.dumps(body)
    sig = base64.b64encode(hmac.new(SECRET.encode(), (timestamp + raw).encode(), hashlib.sha256).digest()).decode()
    return raw, {"x-webhook-signature": sig, "x-webhook-timestamp": timestamp, "content-type": "application/json"}


def _school(client, headers, school_id):
    return next(s for s in client.get("/api/schools", headers=headers).json() if s["id"] == school_id)


def test_not_configured_is_a_clear_503(client):
    _, h = signup(client)
    school = create_school(client, h)
    r = _start(client, h, school["id"])
    assert r.status_code == 503
    assert "support@timetablz.com" in r.json()["detail"]


def test_create_order_returns_only_session_and_order_id(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    r = _start(client, h, school["id"])
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"order_id", "payment_session_id"}
    assert r.json()["payment_session_id"] == "session_abc"

    sent = configured["create"][0]
    assert sent["amount_rupees"] == 4999  # server-side price, not the client's
    assert sent["customer_phone"] == "9876543210"
    assert sent["return_url"] == "https://www.timetablz.com/?page=payment-status&order_id={order_id}"


def test_client_cannot_set_the_amount(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    r = client.post("/api/payments/create-order",
                    json={"school_id": school["id"], "phone": "9876543210", "amount": 1}, headers=h)
    assert r.status_code == 201
    assert configured["create"][0]["amount_rupees"] == 4999


@pytest.mark.parametrize("phone", ["12345", "1234567890", "98765432101", "abcdefghij"])
def test_bad_phone_is_rejected(client, configured, phone):
    _, h = signup(client)
    school = create_school(client, h)
    assert _start(client, h, school["id"], phone).status_code == 422


def test_only_an_admin_can_buy(client, configured):
    _, owner = signup(client, email="owner@a.com")
    school = create_school(client, owner)
    _, stranger = signup(client, email="stranger@a.com")
    assert _start(client, stranger, school["id"]).status_code == 404


def test_pending_until_cashfree_says_paid(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]

    r = client.get(f"/api/payments/orders/{order_id}", headers=h)
    assert r.json()["status"] == "PENDING"
    assert _school(client, h, school["id"])["plan"] is None

    configured["status"] = "PAID"
    r = client.get(f"/api/payments/orders/{order_id}", headers=h)
    assert r.json()["status"] == "PAID"
    s = _school(client, h, school["id"])
    assert s["plan"] == "pro" and s["plan_valid_until"]


def test_verifying_twice_grants_the_year_once(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    configured["status"] = "PAID"
    client.get(f"/api/payments/orders/{order_id}", headers=h)
    first = _school(client, h, school["id"])["plan_valid_until"]
    client.get(f"/api/payments/orders/{order_id}", headers=h)
    assert _school(client, h, school["id"])["plan_valid_until"] == first


def test_amount_mismatch_never_grants(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    configured.update(status="PAID", amount=1.0)
    assert client.get(f"/api/payments/orders/{order_id}", headers=h).json()["status"] == "FAILED"
    assert _school(client, h, school["id"])["plan"] is None


def test_expired_order(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    configured["status"] = "EXPIRED"
    assert client.get(f"/api/payments/orders/{order_id}", headers=h).json()["status"] == "EXPIRED"


def test_other_schools_cannot_see_an_order(client, configured):
    _, h = signup(client, email="one@a.com")
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    _, other = signup(client, email="two@a.com")
    assert client.get(f"/api/payments/orders/{order_id}", headers=other).status_code == 404


def test_webhook_with_valid_signature_grants_the_plan(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    configured["status"] = "PAID"

    raw, headers = _signed({"type": "PAYMENT_SUCCESS", "data": {"order": {"order_id": order_id}}})
    r = client.post("/api/payments/webhook", content=raw, headers=headers)
    assert r.status_code == 200
    assert _school(client, h, school["id"])["plan"] == "pro"

    # Delivered again: still fine, still one year.
    until = _school(client, h, school["id"])["plan_valid_until"]
    assert client.post("/api/payments/webhook", content=raw, headers=headers).status_code == 200
    assert _school(client, h, school["id"])["plan_valid_until"] == until


def test_webhook_payload_alone_cannot_mark_paid(client, configured):
    """A validly signed PAYMENT_SUCCESS is re-checked with Cashfree; if
    Cashfree still says ACTIVE, nothing is granted."""
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    raw, headers = _signed({"type": "PAYMENT_SUCCESS", "data": {"order": {"order_id": order_id}}})
    assert client.post("/api/payments/webhook", content=raw, headers=headers).status_code == 200
    assert _school(client, h, school["id"])["plan"] is None


def test_webhook_with_bad_signature_is_rejected(client, configured):
    _, h = signup(client)
    school = create_school(client, h)
    order_id = _start(client, h, school["id"]).json()["order_id"]
    configured["status"] = "PAID"
    raw, headers = _signed({"type": "PAYMENT_SUCCESS", "data": {"order": {"order_id": order_id}}})
    headers["x-webhook-signature"] = "forged"
    assert client.post("/api/payments/webhook", content=raw, headers=headers).status_code == 400
    assert _school(client, h, school["id"])["plan"] is None


def test_webhook_for_unknown_order_is_acknowledged(client, configured):
    raw, headers = _signed({"type": "PAYMENT_SUCCESS", "data": {"order": {"order_id": "tz_9_nope"}}})
    assert client.post("/api/payments/webhook", content=raw, headers=headers).status_code == 200

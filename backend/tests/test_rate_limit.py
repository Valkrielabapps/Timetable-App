"""
Tests for rate limiting.

The per-email quotas are the ones worth asserting hardest on: the IP limit
is defeated by anything that can set X-Forwarded-For (see client_ip's
docstring), so the email quota is what actually stops credential stuffing.
"""
import time

import pytest
from fastapi import HTTPException, Request

from app.core.rate_limit import GENERAL_LIMIT_PER_MINUTE, ai_budget_left, caller_key, check_ai_quota, check_quota, client_ip, reset_quotas


@pytest.fixture(autouse=True)
def _limiting_on(monkeypatch):
    """conftest.py disables limiting for the rest of the suite; this module is
    the one that has to exercise it, so it turns it back on per test."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    reset_quotas()
    yield
    reset_quotas()


def _request(headers: dict[str, str], client_host: str = "10.0.0.1") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 1234),
    })


# --- client identification -------------------------------------------------

def test_uses_forwarded_client_not_the_proxy():
    """In production every request arrives from a Vercel edge IP; limiting on
    that would put every user in one bucket."""
    req = _request({"x-forwarded-for": "203.0.113.9, 70.41.3.18"}, client_host="76.76.21.21")
    assert client_ip(req) == "203.0.113.9"


def test_falls_back_to_socket_address_without_the_header():
    assert client_ip(_request({}, client_host="10.0.0.7")) == "10.0.0.7"


def test_ignores_an_empty_forwarded_header():
    req = _request({"x-forwarded-for": "  "}, client_host="10.0.0.7")
    assert client_ip(req) == "10.0.0.7"


# --- quotas ----------------------------------------------------------------

def test_allows_up_to_the_limit_then_blocks():
    for _ in range(3):
        check_quota("k", limit=3, window_seconds=60)
    with pytest.raises(Exception) as exc:
        check_quota("k", limit=3, window_seconds=60)
    assert exc.value.status_code == 429


def test_keys_are_independent():
    for _ in range(3):
        check_quota("a", limit=3, window_seconds=60)
    check_quota("b", limit=3, window_seconds=60)  # must not raise


def test_429_carries_retry_after():
    check_quota("k", limit=1, window_seconds=60)
    with pytest.raises(Exception) as exc:
        check_quota("k", limit=1, window_seconds=60)
    retry_after = int(exc.value.headers["Retry-After"])
    assert 0 < retry_after <= 60


def test_hits_outside_the_window_do_not_count():
    check_quota("k", limit=2, window_seconds=0)
    check_quota("k", limit=2, window_seconds=0)
    # window of 0 means every earlier hit has already aged out
    check_quota("k", limit=2, window_seconds=0)


def test_email_quota_holds_across_rotating_ips():
    """The point of the per-email limit: an attacker who rotates IPs (or
    forges X-Forwarded-For) defeats the IP limit, and must still be stopped."""
    email = "victim@school.example"
    for _ in range(10):
        check_quota(f"login:{email}", limit=10, window_seconds=3600)
    with pytest.raises(Exception) as exc:
        check_quota(f"login:{email}", limit=10, window_seconds=3600)
    assert exc.value.status_code == 429


def test_blocked_attempts_do_not_extend_the_block():
    """A rejected call must not count as a hit, or hammering a blocked key
    would keep pushing the window forward and lock it out indefinitely."""
    check_quota("k", limit=1, window_seconds=60)
    for _ in range(5):
        with pytest.raises(Exception):
            check_quota("k", limit=1, window_seconds=60)
    with pytest.raises(Exception) as exc:
        check_quota("k", limit=1, window_seconds=60)
    assert int(exc.value.headers["Retry-After"]) <= 60


# --- through the actual HTTP stack -----------------------------------------

def test_login_is_throttled_per_email_over_http(client, monkeypatch):
    """End-to-end: the decorator/middleware wiring in main.py actually fires,
    and the 429 carries the `detail` shape frontend/src/api.js reads."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True)
    reset_quotas()

    body = {"email": "nobody@school.example", "password": "wrong-password"}
    for _ in range(10):
        assert client.post("/api/auth/login", json=body).status_code == 401

    blocked = client.post("/api/auth/login", json=body)
    assert blocked.status_code == 429
    assert "detail" in blocked.json()
    assert blocked.headers.get("Retry-After")

    # A different account is unaffected - the block is per email, not global.
    other = client.post(
        "/api/auth/login",
        json={"email": "someone-else@school.example", "password": "wrong-password"},
    )
    assert other.status_code == 401


# --- the general ceiling, per user -----------------------------------------

@pytest.fixture
def limiter_on(monkeypatch):
    """slowapi's switch is read when the limiter is made; turn it on and start
    from empty counters."""
    from app.core.rate_limit import limiter

    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    yield limiter
    limiter.reset()


def _hammer(client, n, **kwargs):
    return [client.get("/api/auth/me", **kwargs).status_code for _ in range(n)]


def test_every_route_has_a_ceiling_per_user(client, limiter_on):
    from tests.conftest import signup

    _, alice = signup(client, email="alice@example.com")
    _, bob = signup(client, email="bob@example.com")
    limit = GENERAL_LIMIT_PER_MINUTE
    codes = _hammer(client, limit, headers=alice)
    assert set(codes) == {200}
    blocked = client.get("/api/auth/me", headers=alice)
    assert blocked.status_code == 429 and "detail" in blocked.json()
    # Same machine, same IP: someone else signed in isn't held up.
    assert client.get("/api/auth/me", headers=bob).status_code == 200


def test_a_forged_forwarded_header_doesnt_reset_a_users_count(client, limiter_on):
    from tests.conftest import signup

    _, alice = signup(client, email="alice@example.com")
    limit = GENERAL_LIMIT_PER_MINUTE
    _hammer(client, limit, headers=alice)
    forged = {**alice, "X-Forwarded-For": "198.51.100.77"}
    assert client.get("/api/auth/me", headers=forged).status_code == 429


def test_the_payment_webhook_is_never_rate_limited(client, limiter_on):
    limit = GENERAL_LIMIT_PER_MINUTE
    codes = {client.post("/api/payments/webhook", content=b"{}").status_code for _ in range(limit + 5)}
    assert 429 not in codes


def test_caller_key_uses_the_user_then_the_ip():
    from app.core.auth import create_access_token

    token = create_access_token(type("U", (), {"id": 42, "token_version": 0})())
    assert caller_key(_request({"authorization": f"Bearer {token}"})) == "user:42"
    assert caller_key(_request({"authorization": "Bearer not-a-token"}, client_host="10.0.0.9")) == "ip:10.0.0.9"
    assert caller_key(_request({}, client_host="10.0.0.9")) == "ip:10.0.0.9"


# --- paid services ---------------------------------------------------------

def test_the_whole_site_has_one_ai_allowance(monkeypatch):
    """However many accounts call the AI, together they stop at the site's
    ceiling."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "ai_calls_per_hour", 3)
    for user in (1, 2, 3):
        check_ai_quota("llm", user, per_hour=60)
    with pytest.raises(HTTPException) as exc:
        check_ai_quota("llm", 4, per_hour=60)
    assert exc.value.status_code == 429
    assert ai_budget_left() is False


def test_a_daily_quota_survives_a_sweep():
    """Clearing out old hourly entries mustn't wipe a daily count."""
    from app.core import rate_limit

    check_quota("daily", limit=2, window_seconds=86400)
    check_quota("daily", limit=2, window_seconds=86400)
    with rate_limit._lock:
        rate_limit._prune(time.monotonic() + 7200)
    with pytest.raises(HTTPException):
        check_quota("daily", limit=2, window_seconds=86400)


def test_spreadsheet_imports_are_limited_per_user(client):
    from tests.conftest import create_school, signup

    _, headers = signup(client, email="importer@example.com")
    school = create_school(client, headers)["id"]
    sheet = {"file": ("teachers.csv", b"name\nSusan\n", "text/csv")}
    url, form = "/api/teachers/bulk-import/preview", {"school_id": str(school)}
    codes = [client.post(url, headers=headers, files=sheet, data=form).status_code for _ in range(31)]
    assert 200 in codes and 429 not in codes[:30], codes
    assert codes[30] == 429


def test_cover_emails_are_limited(client, monkeypatch):
    from app.services import substitution_notify
    from tests.conftest import create_school, signup

    monkeypatch.setattr(substitution_notify, "notify", lambda *a, **k: {"sent": 0})
    _, headers = signup(client, email="coordinator@example.com")
    school = create_school(client, headers)["id"]
    body = {"date": "2026-11-11", "category": None, "everyone": False}
    url = f"/api/schools/{school}/substitutions/notify"
    codes = [client.post(url, headers=headers, json=body).status_code for _ in range(31)]
    assert 200 in codes and 429 not in codes[:30], codes
    assert codes[30] == 429


def test_generating_is_limited_per_school(client, monkeypatch):
    from app.routers import timetables
    from tests.conftest import create_school, signup

    monkeypatch.setattr(timetables, "_refuse_if_generating", lambda db, school_id: None)
    monkeypatch.setattr(timetables.threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    _, headers = signup(client, email="generator@example.com")
    school = create_school(client, headers)["id"]
    codes = [client.post(f"/api/timetables/generate?school_id={school}", headers=headers).status_code for _ in range(31)]
    assert 201 in codes and 429 not in codes[:30], codes
    assert codes[30] == 429


def test_signups_are_limited_per_ip(client, limiter_on):
    """The per-route limits are applied by their decorators, not the middleware
    - check one really fires."""
    codes = [client.post("/api/auth/signup", json={"email": f"new{i}@example.com", "password": "password123"}).status_code
             for i in range(6)]
    assert codes[:5] == [201] * 5 and codes[5] == 429, codes

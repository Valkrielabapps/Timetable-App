"""
Tests for rate limiting.

The per-email quotas are the ones worth asserting hardest on: the IP limit
is defeated by anything that can set X-Forwarded-For (see client_ip's
docstring), so the email quota is what actually stops credential stuffing.
"""
import pytest
from fastapi import Request

from app.core.rate_limit import check_quota, client_ip, reset_quotas


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

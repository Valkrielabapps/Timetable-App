"""
Accepting the Terms of Service: asked at first sign-in and again whenever
the terms change, and every acceptance recorded.
"""
from app.core import terms
from app.core.database import SessionLocal
from app.models.user import TermsAcceptance
from tests.conftest import signup


def test_a_new_account_must_accept_and_the_acceptance_is_recorded(client):
    user, h = signup(client)
    assert user["needs_terms"] is True and user["terms_version"] == terms.CURRENT_TERMS_VERSION
    assert client.get("/api/auth/me", headers=h).json()["needs_terms"] is True

    r = client.post("/api/auth/accept-terms", json={"version": terms.CURRENT_TERMS_VERSION},
                    headers={**h, "X-Forwarded-For": "203.0.113.7", "User-Agent": "Firefox test"})
    assert r.status_code == 200 and r.json()["needs_terms"] is False
    assert client.get("/api/auth/me", headers=h).json()["needs_terms"] is False
    # Accepting again doesn't add a second record.
    client.post("/api/auth/accept-terms", json={"version": terms.CURRENT_TERMS_VERSION}, headers=h)
    db = SessionLocal()
    try:
        (a,) = db.query(TermsAcceptance).all()
        assert (a.email, a.version, a.ip_address, a.user_agent) == (
            "a@a.com", terms.CURRENT_TERMS_VERSION, "203.0.113.7", "Firefox test")
        assert a.accepted_at is not None
    finally:
        db.close()


def test_an_old_page_cannot_accept_newer_terms(client):
    _, h = signup(client)
    r = client.post("/api/auth/accept-terms", json={"version": "2020-01-01"}, headers=h)
    assert r.status_code == 409


def test_new_terms_are_asked_for_again(client, monkeypatch):
    _, h = signup(client)
    client.post("/api/auth/accept-terms", json={"version": terms.CURRENT_TERMS_VERSION}, headers=h)
    monkeypatch.setattr(terms, "CURRENT_TERMS_VERSION", "2099-01-01")
    me = client.get("/api/auth/me", headers=h).json()
    assert me["needs_terms"] is True and me["terms_version"] == "2099-01-01" and me["has_accepted_before"] is True


def test_signing_in_again_does_not_ask_again(client):
    _, h = signup(client)
    client.post("/api/auth/accept-terms", json={"version": terms.CURRENT_TERMS_VERSION}, headers=h)
    r = client.post("/api/auth/login", json={"email": "a@a.com", "password": "password123"})
    assert r.json()["user"]["needs_terms"] is False


def test_accepting_needs_a_signed_in_user(client):
    assert client.post("/api/auth/accept-terms", json={"version": terms.CURRENT_TERMS_VERSION}).status_code == 401

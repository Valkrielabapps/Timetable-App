"""
Tests for the forgot-password/reset-password flow added to
app/routers/auth.py. Covers the two security properties called out in
that router's docstrings: forgot-password must not leak which emails
have accounts (same response either way), and a reset token must be
single-use and reject once expired.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import PasswordResetToken, User
import pytest

from app.core.auth import hash_token
from tests.conftest import signup

# The link each address was emailed: the database keeps only its hash.
_SENT: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _capture_reset_emails(monkeypatch):
    from app.routers import auth

    _SENT.clear()
    real = auth.send_password_reset_email

    def record(to_email, reset_token):
        _SENT[to_email] = reset_token
        return real(to_email=to_email, reset_token=reset_token)

    monkeypatch.setattr(auth, "send_password_reset_email", record)


def _get_reset_token_for(email):
    """Pulls the token straight out of the DB via the app's own session
    factory (the same database `client` talks to — NOT the `orm_db`
    fixture, which is a separate throwaway in-memory DB for service-level
    tests, see conftest.py) — the API response never includes the token
    itself (see forgot_password's docstring), same as how a real user
    would only get it via the emailed link."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        row = (
            db.query(PasswordResetToken)
            .filter(PasswordResetToken.user_id == user.id)
            .order_by(PasswordResetToken.id.desc())
            .first()
        )
    finally:
        db.close()
    if row is not None:
        # Stored hashed, never as the emailed token itself.
        assert row.token == hash_token(_SENT[email]) != _SENT[email]
        row.token = _SENT[email]  # detached: changes nothing in the database
    return row


def _expire_token(token_row):
    """Updates expires_at on the token row via a fresh session, since the
    row returned by _get_reset_token_for came from an already-closed
    session and can't be mutated/committed directly."""
    db = SessionLocal()
    try:
        row = db.get(PasswordResetToken, token_row.id)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()


def test_forgot_password_returns_same_response_for_unknown_email(client):
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@a.com"})
    assert r.status_code == 202
    detail_for_unknown = r.json()["detail"]

    signup(client, email="known@a.com")
    r = client.post("/api/auth/forgot-password", json={"email": "known@a.com"})
    assert r.status_code == 202
    assert r.json()["detail"] == detail_for_unknown


def test_forgot_password_creates_a_usable_token_for_a_known_email(client):
    signup(client, email="reset-me@a.com")
    r = client.post("/api/auth/forgot-password", json={"email": "reset-me@a.com"})
    assert r.status_code == 202

    token_row = _get_reset_token_for("reset-me@a.com")
    assert token_row is not None
    assert token_row.used is False

    r = client.post("/api/auth/reset-password", json={"token": token_row.token, "new_password": "newpassword123"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "reset-me@a.com"

    # New password actually works now.
    r = client.post("/api/auth/login", json={"email": "reset-me@a.com", "password": "newpassword123"})
    assert r.status_code == 200

    # And logging in with the OLD password no longer works.
    r = client.post("/api/auth/login", json={"email": "reset-me@a.com", "password": "password123"})
    assert r.status_code == 401


def test_reset_token_cannot_be_used_twice(client):
    signup(client, email="once@a.com")
    client.post("/api/auth/forgot-password", json={"email": "once@a.com"})
    token_row = _get_reset_token_for("once@a.com")

    r = client.post("/api/auth/reset-password", json={"token": token_row.token, "new_password": "firstnewpass"})
    assert r.status_code == 200

    r = client.post("/api/auth/reset-password", json={"token": token_row.token, "new_password": "secondnewpass"})
    assert r.status_code == 400


def test_expired_reset_token_is_rejected(client):
    signup(client, email="expired@a.com")
    client.post("/api/auth/forgot-password", json={"email": "expired@a.com"})
    token_row = _get_reset_token_for("expired@a.com")
    _expire_token(token_row)

    r = client.post("/api/auth/reset-password", json={"token": token_row.token, "new_password": "newpassword123"})
    assert r.status_code == 400


def test_unknown_token_is_rejected(client):
    r = client.post("/api/auth/reset-password", json={"token": "not-a-real-token", "new_password": "newpassword123"})
    assert r.status_code == 400


def test_forgot_password_attempts_to_send_email_when_resend_configured(client):
    signup(client, email="notify-me@a.com")
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            r = client.post("/api/auth/forgot-password", json={"email": "notify-me@a.com"})
    assert r.status_code == 202
    mock_post.assert_called_once()
    assert mock_post.call_args.kwargs["json"]["to"] == ["notify-me@a.com"]

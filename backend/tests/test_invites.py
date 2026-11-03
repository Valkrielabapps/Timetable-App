"""
Tests for app/routers/invites.py's public, token-based accept flow, and
the admin-only invite management endpoints in app/routers/schools.py.
Covers the two branches AcceptInviteRequest's docstring calls out:
accepting creates a brand-new account (invite email never signed up) vs.
confirms an existing account's password (invite email already has a
User row) - and that a wrong password on the existing-account branch is
rejected rather than silently logging in as that user.
"""
from unittest.mock import patch

from app.core.config import settings
from tests.conftest import create_school, signup


def test_preview_invite_does_not_require_auth(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "new@a.com", "role": "viewer"}, headers=owner_headers
    )
    token = r.json()["token"]

    r = client.get(f"/api/invites/{token}")  # no Authorization header at all
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "new@a.com"
    assert body["role"] == "viewer"
    assert body["school_name"] == school["name"]
    assert body["status"] == "pending"


def test_accept_invite_for_brand_new_email_creates_account(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "brandnew@a.com", "role": "admin"}, headers=owner_headers
    )
    token = r.json()["token"]

    r = client.post(f"/api/invites/{token}/accept", json={"name": "Brand New", "password": "password123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "brandnew@a.com"
    new_headers = {"Authorization": f"Bearer {body['access_token']}"}

    # The new account should now actually have admin access to the school.
    r = client.get(f"/api/schools/{school['id']}", headers=new_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_accept_invite_for_existing_email_requires_correct_password(client):
    _, existing_headers = signup(client, email="existing@a.com", password="correcthorse")
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "existing@a.com", "role": "viewer"}, headers=owner_headers
    )
    token = r.json()["token"]

    r = client.post(f"/api/invites/{token}/accept", json={"password": "wrongpassword"})
    assert r.status_code == 401

    r = client.post(f"/api/invites/{token}/accept", json={"password": "correcthorse"})
    assert r.status_code == 200, r.text

    r = client.get(f"/api/schools/{school['id']}", headers=existing_headers)
    assert r.json()["role"] == "viewer"


def test_invite_cannot_be_accepted_twice(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "once@a.com", "role": "viewer"}, headers=owner_headers
    )
    token = r.json()["token"]

    r = client.post(f"/api/invites/{token}/accept", json={"name": "Once", "password": "password123"})
    assert r.status_code == 200

    r = client.post(f"/api/invites/{token}/accept", json={"name": "Once", "password": "password123"})
    assert r.status_code == 404


def test_revoked_invite_cannot_be_accepted(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "revoked@a.com", "role": "viewer"}, headers=owner_headers
    )
    invite = r.json()

    r = client.delete(f"/api/schools/{school['id']}/invites/{invite['id']}", headers=owner_headers)
    assert r.status_code == 204

    r = client.post(f"/api/invites/{invite['token']}/accept", json={"name": "X", "password": "password123"})
    assert r.status_code == 404


def test_create_invite_without_resend_configured_still_succeeds(client):
    """The whole point of email being best-effort: no RESEND_API_KEY (the
    default, and the test env's actual state) must never block invite
    creation itself - see app/services/email_service.py's docstring."""
    assert settings.resend_api_key is None
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "new@a.com", "role": "viewer"}, headers=owner_headers
    )
    assert r.status_code == 201
    assert r.json()["email_sent"] is False
    assert r.json()["token"]  # link is still usable regardless


def test_create_invite_reports_email_sent_when_resend_succeeds(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            r = client.post(
                f"/api/schools/{school['id']}/invites",
                json={"email": "new@a.com", "role": "viewer"}, headers=owner_headers,
            )
    assert r.status_code == 201
    assert r.json()["email_sent"] is True


def test_create_invite_still_succeeds_when_email_send_fails(client):
    """A Resend outage/misconfiguration must degrade to 'no email sent',
    not fail the whole invite-creation request."""
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post", side_effect=ConnectionError("boom")):
            r = client.post(
                f"/api/schools/{school['id']}/invites",
                json={"email": "new@a.com", "role": "viewer"}, headers=owner_headers,
            )
    assert r.status_code == 201
    assert r.json()["email_sent"] is False


def test_duplicate_pending_invite_for_same_email_is_rejected(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "dup@a.com", "role": "viewer"}, headers=owner_headers
    )
    assert r.status_code == 201

    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "dup@a.com", "role": "admin"}, headers=owner_headers
    )
    assert r.status_code == 400

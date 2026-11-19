"""
One account per address, whatever its capitals: new addresses are stored
lowercased, and every lookup lowercases both sides - so accounts made before
that, still stored with capitals, keep working. New addresses must be plain
ASCII, so two look-alike addresses (a Cyrillic letter for a Latin one) can't
name two accounts.
"""
from unittest.mock import patch

from app.core.auth import hash_password
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.school import SchoolInvite
from app.models.user import User
from tests.conftest import create_school, signup


def _stored_emails():
    db = SessionLocal()
    try:
        return [u.email for u in db.query(User).order_by(User.id)]
    finally:
        db.close()


def _old_account(email, password="password123"):
    """An account from before addresses were lowercased."""
    db = SessionLocal()
    try:
        db.add(User(email=email, hashed_password=hash_password(password), name="Old"))
        db.commit()
    finally:
        db.close()


def test_a_new_address_is_stored_lowercased_and_signs_in_any_case(client):
    user, _ = signup(client, email="  Allen@School.IN ")
    assert user["email"] == "allen@school.in"
    assert _stored_emails() == ["allen@school.in"]
    r = client.post("/api/auth/login", json={"email": "ALLEN@school.in", "password": "password123"})
    assert r.status_code == 200, r.text


def test_the_same_address_in_other_capitals_is_one_account(client):
    signup(client, email="allen@school.in")
    r = client.post("/api/auth/signup", json={"email": "Allen@School.in", "password": "password123"})
    assert r.status_code == 400
    assert _stored_emails() == ["allen@school.in"]


def test_an_older_account_with_capitals_still_works(client):
    _old_account("Priya.R@School.in")
    r = client.post("/api/auth/login", json={"email": "priya.r@school.in", "password": "password123"})
    assert r.status_code == 200, r.text
    # And nobody can open a second account for it in other capitals.
    r = client.post("/api/auth/signup", json={"email": "PRIYA.R@school.in", "password": "password123"})
    assert r.status_code == 400


def test_a_new_address_must_be_plain_ascii(client):
    # "аllen" with a Cyrillic а - looks the same as allen@school.in.
    r = client.post("/api/auth/signup", json={"email": "аllen@school.in", "password": "password123"})
    assert r.status_code == 422
    # Signing in isn't refused for it - just no such account.
    r = client.post("/api/auth/login", json={"email": "аllen@school.in", "password": "password123"})
    assert r.status_code == 401


def test_invites_use_the_lowercased_address(client):
    _, owner = signup(client, email="owner@school.in")
    school = create_school(client, owner)
    r = client.post(f"/api/schools/{school['id']}/invites", json={"email": "New.Teacher@School.in", "role": "viewer"},
                    headers=owner)
    assert r.status_code in (200, 201), r.text
    # Inviting the same person again in other capitals is the same invite, not a second one.
    client.post(f"/api/schools/{school['id']}/invites", json={"email": "new.teacher@school.in", "role": "viewer"},
                headers=owner)
    db = SessionLocal()
    try:
        assert [i.email for i in db.query(SchoolInvite)] == ["new.teacher@school.in"]
    finally:
        db.close()
    r = client.post(f"/api/invites/{r.json()['token']}/accept", json={"name": "New", "password": "password123"})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "new.teacher@school.in"


def test_an_invite_finds_an_older_account_with_capitals(client):
    _old_account("Kavya@School.in", password="correcthorse")
    _, owner = signup(client, email="owner@school.in")
    school = create_school(client, owner)
    token = client.post(f"/api/schools/{school['id']}/invites", json={"email": "kavya@school.in", "role": "viewer"},
                        headers=owner).json()["token"]
    # It's her existing account, so it wants her password - not a new account.
    assert client.post(f"/api/invites/{token}/accept", json={"name": "K", "password": "wrong-pass"}).status_code == 401
    r = client.post(f"/api/invites/{token}/accept", json={"password": "correcthorse"})
    assert r.status_code == 200, r.text
    assert _stored_emails().count("Kavya@School.in") == 1


def test_google_links_to_the_account_whatever_the_capitals(client):
    signup(client, email="allen@school.in")
    claims = {"email": "Allen@School.in", "email_verified": True, "sub": "google-sub-9", "name": "Allen"}
    with patch.object(settings, "google_client_id", "client-id"), \
            patch("app.routers.auth.google_id_token.verify_oauth2_token", return_value=claims):
        r = client.post("/api/auth/google", json={"credential": "x"})
    assert r.status_code == 200, r.text
    assert _stored_emails() == ["allen@school.in"]

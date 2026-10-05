"""Settings endpoints (rename school, update own name) and the support
ticket endpoint. Resend is mocked; nothing leaves the machine."""
from unittest.mock import patch

from app.core.config import settings
from tests.conftest import create_school, signup


def test_admin_can_rename_school(client):
    _, h = signup(client)
    school = create_school(client, h, name="Old Name")
    r = client.put(f"/api/schools/{school['id']}/name", json={"name": "  New Name  "}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "New Name"


def test_rename_rejects_blank(client):
    _, h = signup(client)
    school = create_school(client, h)
    r = client.put(f"/api/schools/{school['id']}/name", json={"name": "   "}, headers=h)
    assert r.status_code == 422


def test_stranger_cannot_rename_school(client):
    _, h1 = signup(client, email="owner@a.com")
    _, h2 = signup(client, email="other@a.com")
    school = create_school(client, h1)
    r = client.put(f"/api/schools/{school['id']}/name", json={"name": "Hijacked"}, headers=h2)
    assert r.status_code == 404


def test_user_can_update_own_name(client):
    _, h = signup(client, name="Old")
    r = client.patch("/api/auth/me", json={"name": "Allen Davis"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Allen Davis"
    assert client.get("/api/auth/me", headers=h).json()["name"] == "Allen Davis"


def test_support_ticket_503_when_email_not_configured(client):
    _, h = signup(client)
    r = client.post("/api/support/tickets", json={"subject": "Help", "message": "Stuck"}, headers=h)
    assert r.status_code == 503
    assert settings.support_email in r.json()["detail"]


def test_support_ticket_sent_with_reply_to_and_escaped_html(client):
    _, h = signup(client, email="admin@school.in", name="Priya")
    school = create_school(client, h, name="Riverside")
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            r = client.post(
                "/api/support/tickets",
                json={
                    "category": "problem",
                    "subject": "Can't generate",
                    "message": "<script>x</script>\nline two",
                    "school_id": school["id"],
                },
                headers=h,
            )
    assert r.status_code == 202, r.text
    sent = mock_post.call_args.kwargs["json"]
    assert sent["to"] == [settings.support_email]
    assert sent["reply_to"] == "admin@school.in"
    assert "[Support] Can't generate" == sent["subject"]
    assert "Riverside" in sent["html"]
    assert "<script>" not in sent["html"]
    assert "line two" in sent["html"]


def test_support_ticket_requires_login(client):
    r = client.post("/api/support/tickets", json={"subject": "a", "message": "b"})
    assert r.status_code == 401


def test_admin_can_save_school_profile_and_blanks_are_dropped(client):
    _, h = signup(client)
    school = create_school(client, h)
    r = client.put(
        f"/api/schools/{school['id']}/profile",
        json={
            "board": "CBSE",
            "city": " Thiruvananthapuram ",
            "state": "Kerala",
            "academic_year_start_month": 6,
            "website": "   ",
            "not_a_field": "ignored",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    profile = r.json()["profile"]
    assert profile == {
        "board": "CBSE",
        "city": "Thiruvananthapuram",
        "state": "Kerala",
        "academic_year_start_month": 6,
    }
    listed = client.get("/api/schools", headers=h).json()
    assert listed[0]["profile"]["board"] == "CBSE"


def test_profile_rejects_bad_month(client):
    _, h = signup(client)
    school = create_school(client, h)
    r = client.put(f"/api/schools/{school['id']}/profile", json={"academic_year_start_month": 13}, headers=h)
    assert r.status_code == 422


def test_viewer_cannot_edit_profile(client):
    _, h_owner = signup(client, email="owner@a.com")
    school = create_school(client, h_owner)
    invite = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer@a.com", "role": "viewer"}, headers=h_owner
    ).json()
    accepted = client.post(f"/api/invites/{invite['token']}/accept", json={"name": "V", "password": "password123"})
    assert accepted.status_code in (200, 201), accepted.text
    h_viewer = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    r = client.put(f"/api/schools/{school['id']}/profile", json={"board": "ICSE"}, headers=h_viewer)
    assert r.status_code == 403

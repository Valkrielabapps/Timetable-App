"""
Tests for app/core/access.py's require_school_access, exercised through
real router endpoints rather than calling the function directly - the
actual risk this closes (see docs/ARCHITECTURE.md's "Multiple admins per
school..." section) is a router forgetting to call it or getting the
school_id wrong, which a unit test on access.py alone wouldn't catch.

Covers, per the documented role model (owner/admin implicit, viewer
read-only, no relationship at all -> 404 not 403):
  - A user with no relationship to a school gets 404 from a resource
    endpoint, not a 403 or a 200 with someone else's data.
  - A viewer (added via accepting an invite) can read but gets 403 on a
    write endpoint.
  - An invited admin can write normally.
  - Only an admin can see the members/invites list; a viewer gets 403.
"""
from tests.conftest import create_school, signup


def _invite_and_accept(client, owner_headers, school_id, email, role):
    r = client.post(f"/api/schools/{school_id}/invites", json={"email": email, "role": role}, headers=owner_headers)
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    r = client.post(f"/api/invites/{token}/accept", json={"name": "Invitee", "password": "password123"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


def test_unrelated_user_gets_404_not_403_or_200(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)

    _, stranger_headers = signup(client, email="stranger@a.com")

    r = client.get(f"/api/subjects?school_id={school['id']}", headers=stranger_headers)
    assert r.status_code == 404

    r = client.post(
        "/api/subjects", json={"school_id": school["id"], "name": "Math"}, headers=stranger_headers
    )
    assert r.status_code == 404

    r = client.get(f"/api/schools/{school['id']}", headers=stranger_headers)
    assert r.status_code == 404


def test_viewer_can_read_but_not_write(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    _, viewer_headers = _invite_and_accept(client, owner_headers, school["id"], "viewer@a.com", "viewer")

    r = client.get(f"/api/subjects?school_id={school['id']}", headers=viewer_headers)
    assert r.status_code == 200
    assert r.json() == []

    r = client.post(
        "/api/subjects", json={"school_id": school["id"], "name": "Math"}, headers=viewer_headers
    )
    assert r.status_code == 403

    r = client.get(f"/api/schools/{school['id']}/members", headers=viewer_headers)
    assert r.status_code == 403


def test_invited_admin_can_write(client):
    _, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)
    _, second_admin_headers = _invite_and_accept(client, owner_headers, school["id"], "admin2@a.com", "admin")

    r = client.post(
        "/api/subjects", json={"school_id": school["id"], "name": "Math"}, headers=second_admin_headers
    )
    assert r.status_code == 201, r.text

    r = client.get(f"/api/schools/{school['id']}/members", headers=second_admin_headers)
    assert r.status_code == 200
    roles = {m["email"]: m["role"] for m in r.json()}
    assert roles["owner@a.com"] == "admin"
    assert roles["admin2@a.com"] == "admin"


def test_owner_cannot_be_removed_or_demoted(client):
    owner, owner_headers = signup(client, email="owner@a.com")
    school = create_school(client, owner_headers)

    r = client.patch(
        f"/api/schools/{school['id']}/members/{owner['id']}", json={"role": "viewer"}, headers=owner_headers
    )
    assert r.status_code == 400

    r = client.delete(f"/api/schools/{school['id']}/members/{owner['id']}", headers=owner_headers)
    assert r.status_code == 400


def test_cross_school_isolation(client):
    """A resource belonging to school A must not be readable/writable by
    an admin of unrelated school B, even though they're a real admin
    somewhere - access is per-school, not a global "is an admin" flag."""
    _, a_headers = signup(client, email="a_owner@a.com")
    school_a = create_school(client, a_headers, name="School A")
    r = client.post("/api/subjects", json={"school_id": school_a["id"], "name": "Math"}, headers=a_headers)
    subject_id = r.json()["id"]

    _, b_headers = signup(client, email="b_owner@a.com")
    create_school(client, b_headers, name="School B")

    r = client.get(f"/api/subjects/{subject_id}", headers=b_headers)
    assert r.status_code == 404

    r = client.put(f"/api/subjects/{subject_id}", json={"name": "Hijacked"}, headers=b_headers)
    assert r.status_code == 404

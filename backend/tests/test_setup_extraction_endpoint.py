"""
Tests for POST /api/schools/{id}/setup-extraction and its /commit
counterpart (app/routers/setup_extraction.py). Only the LLM call
(setup_extractor.extract_setup_llm) is mocked — file parsing and the
actual DB writes on /commit go through the real code paths.
"""
from unittest.mock import patch

from app.core.config import settings
from tests.conftest import create_school, signup


def _csv_file(content: bytes = b"Name,Subject\nMrs. Sharma,Math\n"):
    return {"file": ("staff.csv", content, "text/csv")}


def test_extract_unavailable_without_llm_configured(client):
    assert settings.anthropic_api_key is None
    _, headers = signup(client)
    school = create_school(client, headers)

    r = client.post(f"/api/schools/{school['id']}/setup-extraction", files=_csv_file(), headers=headers)
    assert r.status_code == 503


def test_extract_rejects_unsupported_file_type(client):
    _, headers = signup(client)
    school = create_school(client, headers)

    r = client.post(
        f"/api/schools/{school['id']}/setup-extraction",
        files={"file": ("staff.pdf", b"whatever", "application/pdf")},
        headers=headers,
    )
    assert r.status_code == 400


def test_extract_returns_preview_without_creating_anything(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    fake_extracted = {
        "teachers": [{"name": "Mrs. Sharma", "email": None, "subject_names": ["Math"]}],
        "subjects": [{"name": "Math"}],
        "class_groups": [{"name": "A", "grade": "Grade 8"}],
        "notes": "",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.setup_extraction.extract_setup_llm", return_value=fake_extracted):
            r = client.post(f"/api/schools/{school['id']}/setup-extraction", files=_csv_file(), headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["teachers"][0]["name"] == "Mrs. Sharma"

    # Nothing was actually created yet.
    assert client.get(f"/api/teachers?school_id={school['id']}", headers=headers).json() == []
    assert client.get(f"/api/subjects?school_id={school['id']}", headers=headers).json() == []


def test_viewer_cannot_extract(client):
    owner, headers = signup(client, email="owner@a.com")
    school = create_school(client, headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer@a.com", "role": "viewer"}, headers=headers
    )
    token = r.json()["token"]
    accept = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    r = client.post(f"/api/schools/{school['id']}/setup-extraction", files=_csv_file(), headers=viewer_headers)
    assert r.status_code == 403


def test_commit_creates_entities_and_resolves_teacher_subjects(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    payload = {
        "subjects": [{"name": "Math"}],
        "teachers": [{"name": "Mrs. Sharma", "email": "sharma@example.com", "subject_names": ["Math"]}],
        "class_groups": [{"name": "A", "grade": "Grade 8"}],
    }
    r = client.post(f"/api/schools/{school['id']}/setup-extraction/commit", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["subjects_created"] == 1
    assert body["teachers_created"] == 1
    assert body["class_groups_created"] == 1
    assert body["errors"] == []

    teachers = client.get(f"/api/teachers?school_id={school['id']}", headers=headers).json()
    subjects = client.get(f"/api/subjects?school_id={school['id']}", headers=headers).json()
    assert teachers[0]["qualified_subject_ids"] == [subjects[0]["id"]]


def test_commit_is_idempotent_upsert_by_name(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    payload = {"subjects": [{"name": "Math"}], "teachers": [], "class_groups": []}
    r1 = client.post(f"/api/schools/{school['id']}/setup-extraction/commit", json=payload, headers=headers)
    r2 = client.post(f"/api/schools/{school['id']}/setup-extraction/commit", json=payload, headers=headers)
    assert r1.json()["subjects_created"] == 1
    assert r2.json()["subjects_created"] == 0
    assert r2.json()["subjects_updated"] == 1
    subjects = client.get(f"/api/subjects?school_id={school['id']}", headers=headers).json()
    assert len(subjects) == 1


def test_viewer_cannot_commit(client):
    owner, headers = signup(client, email="owner2@a.com")
    school = create_school(client, headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer2@a.com", "role": "viewer"}, headers=headers
    )
    token = r.json()["token"]
    accept = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    payload = {"subjects": [{"name": "Math"}], "teachers": [], "class_groups": []}
    r = client.post(f"/api/schools/{school['id']}/setup-extraction/commit", json=payload, headers=viewer_headers)
    assert r.status_code == 403

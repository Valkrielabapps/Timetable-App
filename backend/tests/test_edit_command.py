"""
Tests for POST /api/timetables/{id}/edit-command
(app/routers/timetables.py's edit_command, backed by
app/services/edit_command_parser.py). Builds a real, small, generated
timetable through the actual solver (not mocked) so the entries/periods
being edited are genuine rows — only the LLM call itself is mocked,
never a real Anthropic request.
"""
import time
from unittest.mock import patch

from app.core.config import settings
from tests.conftest import create_school, signup


def _create_subject(client, headers, school_id, name):
    return client.post("/api/subjects", json={"school_id": school_id, "name": name}, headers=headers).json()


def _create_teacher(client, headers, school_id, name, qualified_subject_ids):
    return client.post(
        "/api/teachers",
        json={"school_id": school_id, "name": name, "qualified_subject_ids": qualified_subject_ids},
        headers=headers,
    ).json()


def _create_period(client, headers, school_id, day_of_week, order):
    r = client.post(
        "/api/periods",
        json={"school_id": school_id, "day_of_week": day_of_week, "order": order, "label": f"Period {order + 1}"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_class_group(client, headers, school_id, grade, name):
    return client.post(
        "/api/class-groups", json={"school_id": school_id, "grade": grade, "name": name}, headers=headers
    ).json()


def _build_and_generate_timetable(client, headers, school_id):
    """One class group, one subject needing 1 period/week, one qualified
    teacher, a 2-day x 2-period-per-day school — small enough that the
    solver finishes essentially instantly, and generates exactly one
    entry with an obvious extra free slot to move it into."""
    math = _create_subject(client, headers, school_id, "Math")
    _create_teacher(client, headers, school_id, "Mrs. Sharma", [math["id"]])
    cg = _create_class_group(client, headers, school_id, "Grade 8", "A")
    for day in (0, 1):
        for order in (0, 1):
            _create_period(client, headers, school_id, day, order)
    client.post(
        f"/api/class-groups/{cg['id']}/requirements",
        json={"class_group_id": cg["id"], "subject_id": math["id"], "periods_per_week": 1},
        headers=headers,
    )

    r = client.post(f"/api/timetables/generate?school_id={school_id}", headers=headers)
    assert r.status_code == 201, r.text
    timetable_id = r.json()["id"]

    for _ in range(20):
        r = client.get(f"/api/timetables/{timetable_id}", headers=headers)
        if r.json()["status"] != "generating":
            break
        time.sleep(0.1)
    body = r.json()
    assert body["status"] == "draft", body
    assert len(body["entries"]) == 1
    return body


def test_edit_command_unavailable_without_llm_configured(client):
    """No non-LLM fallback for this feature (see edit_command_parser.py's
    docstring) — must fail clearly (503), not silently do nothing."""
    assert settings.anthropic_api_key is None
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])

    r = client.post(
        f"/api/timetables/{timetable['id']}/edit-command",
        json={"text": "move Grade 8's Math to period 2 on Wednesdays"},
        headers=headers,
    )
    assert r.status_code == 503


def test_edit_command_moves_entry_when_llm_resolves_it(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])
    entry = timetable["entries"][0]

    # The other (day, order) slot in this 2x2 school, guaranteed free
    # since only one entry exists — figure out its period id the same way
    # the real periods list would let the LLM.
    periods = client.get(f"/api/periods?school_id={school['id']}", headers=headers).json()
    target_period = next(
        p for p in periods if (p["day_of_week"], p["order"]) != (entry["day_of_week"], entry["order"])
    )

    fake_parsed = {
        "action": "move",
        "entry_id": entry["id"],
        "target_period_id": target_period["id"],
        "target_teacher_id": None,
        "other_entry_id": None,
        "description": "Moved Grade 8 - A's Math to the other period.",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.timetables.parse_edit_command_llm", return_value=fake_parsed) as mock_parse:
            r = client.post(
                f"/api/timetables/{timetable['id']}/edit-command",
                json={"text": "move Grade 8's Math to the other slot"},
                headers=headers,
            )
    assert r.status_code == 200, r.text
    mock_parse.assert_called_once()
    body = r.json()
    assert body["action"] == "move"
    assert len(body["entries"]) == 1
    assert body["entries"][0]["period_id"] == target_period["id"]


def test_edit_command_toggles_lock(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])
    entry = timetable["entries"][0]
    assert entry["locked"] is False

    fake_parsed = {
        "action": "lock", "entry_id": entry["id"], "target_period_id": None,
        "target_teacher_id": None, "other_entry_id": None, "description": "Locked it.",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.timetables.parse_edit_command_llm", return_value=fake_parsed):
            r = client.post(
                f"/api/timetables/{timetable['id']}/edit-command",
                json={"text": "lock Grade 8's Math"},
                headers=headers,
            )
    assert r.status_code == 200, r.text
    assert r.json()["entries"][0]["locked"] is True


def test_edit_command_unresolved_returns_422_not_a_silent_noop(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])

    fake_parsed = {
        "action": "unresolved", "entry_id": None, "target_period_id": None,
        "target_teacher_id": None, "other_entry_id": None,
        "description": "There are multiple Math periods for Grade 8 — which day did you mean?",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.timetables.parse_edit_command_llm", return_value=fake_parsed):
            r = client.post(
                f"/api/timetables/{timetable['id']}/edit-command",
                json={"text": "move Grade 8's Math"},
                headers=headers,
            )
    assert r.status_code == 422
    assert "multiple Math periods" in r.json()["detail"]


def test_edit_command_hallucinated_id_is_rejected_not_trusted(client):
    """A returned id that doesn't actually belong to this timetable/school
    must be treated as a resolution failure, never used to mutate
    anything — see the endpoint's docstring on why every id is
    re-validated server-side."""
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])

    fake_parsed = {
        "action": "move", "entry_id": 999999, "target_period_id": 999999,
        "target_teacher_id": None, "other_entry_id": None, "description": "Moved it.",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.timetables.parse_edit_command_llm", return_value=fake_parsed):
            r = client.post(
                f"/api/timetables/{timetable['id']}/edit-command",
                json={"text": "move it somewhere"},
                headers=headers,
            )
    assert r.status_code == 422


def test_edit_command_rejects_move_of_locked_entry(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])
    entry = timetable["entries"][0]

    r = client.patch(f"/api/timetables/entries/{entry['id']}", json={"locked": True}, headers=headers)
    assert r.status_code == 200

    periods = client.get(f"/api/periods?school_id={school['id']}", headers=headers).json()
    target_period = next(
        p for p in periods if (p["day_of_week"], p["order"]) != (entry["day_of_week"], entry["order"])
    )
    fake_parsed = {
        "action": "move", "entry_id": entry["id"], "target_period_id": target_period["id"],
        "target_teacher_id": None, "other_entry_id": None, "description": "Moved it.",
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.timetables.parse_edit_command_llm", return_value=fake_parsed):
            r = client.post(
                f"/api/timetables/{timetable['id']}/edit-command",
                json={"text": "move it anyway"},
                headers=headers,
            )
    assert r.status_code == 400


def test_viewer_cannot_use_edit_command(client):
    owner, headers = signup(client, email="owner@a.com")
    school = create_school(client, headers)
    timetable = _build_and_generate_timetable(client, headers, school["id"])

    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer@a.com", "role": "viewer"}, headers=headers
    )
    token = r.json()["token"]
    accept = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    r = client.post(
        f"/api/timetables/{timetable['id']}/edit-command",
        json={"text": "anything"},
        headers=viewer_headers,
    )
    assert r.status_code == 403

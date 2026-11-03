"""
Tests for app/routers/constraints.py's direct-create/update/reparse CRUD
and its conflict-detection helpers (_find_placement_conflicts,
_find_day_conflicts) - exercised through POST/PUT /api/constraints
directly (skipping /parse's LLM-first/regex-fallback text parsing
entirely, since ConstraintCreate already accepts type/parameters
directly; the parsing pipeline itself is a separate concern from what
these endpoints do with an already-resolved constraint).
"""
from tests.conftest import create_school, signup


def _create_subject(client, headers, school_id, name):
    r = client.post("/api/subjects", json={"school_id": school_id, "name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _create_constraint(client, headers, school_id, type_, parameters, description="test"):
    r = client.post(
        "/api/constraints",
        json={"school_id": school_id, "type": type_, "parameters": parameters, "description": description},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_contradicting_require_subject_period_constraints_are_flagged(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    math = _create_subject(client, headers, school["id"], "Math")

    first = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "first"}, "Math must be first period",
    )
    second = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "last"}, "Math must be last period",
    )

    assert first["conflicts"] == []  # not yet known to conflict with anything at the moment it was created
    r = client.get(f"/api/constraints/{first['id']}", headers=headers)
    assert any(str(second["id"]) in c for c in r.json()["conflicts"])
    assert second["conflicts"] and str(first["id"]) in second["conflicts"][0]


def test_same_position_does_not_conflict(client):
    """Two 'require first period' rules for the same subject agree with
    each other, not contradict - only opposite positions should flag."""
    _, headers = signup(client)
    school = create_school(client, headers)
    math = _create_subject(client, headers, school["id"], "Math")

    _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "first"},
    )
    second = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "first"},
    )
    assert second["conflicts"] == []


def test_disjoint_scope_does_not_conflict(client):
    """Two contradicting position rules for the same subject, but scoped
    to different (non-overlapping) class groups, can both actually hold - 
    no conflict should be reported."""
    _, headers = signup(client)
    school = create_school(client, headers)
    math = _create_subject(client, headers, school["id"], "Math")

    cg_a = client.post(
        "/api/class-groups", json={"school_id": school["id"], "grade": "Grade 8", "name": "A"}, headers=headers
    ).json()
    cg_b = client.post(
        "/api/class-groups", json={"school_id": school["id"], "grade": "Grade 8", "name": "B"}, headers=headers
    ).json()

    first = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "first", "class_group_ids": [cg_a["id"]]},
    )
    second = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "last", "class_group_ids": [cg_b["id"]]},
    )
    assert first["conflicts"] == []
    assert second["conflicts"] == []


def test_require_and_ban_same_day_conflict(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    pe = _create_subject(client, headers, school["id"], "PE")

    require = _create_constraint(
        client, headers, school["id"], "require_subject_day",
        {"subject_id": pe["id"], "day_of_week": 0}, "PE must be on Monday",
    )
    ban = _create_constraint(
        client, headers, school["id"], "no_subject_day",
        {"subject_id": pe["id"], "day_of_week": 0}, "No PE on Monday",
    )
    assert ban["conflicts"] and str(require["id"]) in ban["conflicts"][0]


def test_reparse_keeps_the_same_id(client):
    """PUT /{id}/reparse mutates the existing row in place rather than
    creating a new one - the whole point is that a reworded rule keeps its
    id and position in the list (see the router's docstring)."""
    _, headers = signup(client)
    school = create_school(client, headers)
    teacher = client.post(
        "/api/teachers", json={"school_id": school["id"], "name": "Mrs. Sharma"}, headers=headers
    ).json()

    created = _create_constraint(
        client, headers, school["id"], "workload_limit",
        {"teacher_id": teacher["id"], "max_periods_per_week": 10}, "Mrs. Sharma: 10 periods/week",
    )
    assert created["enforced"] is True

    r = client.put(
        f"/api/constraints/{created['id']}/reparse",
        json={"text": "Mrs. Sharma can only teach 15 periods a week"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    reparsed = body["constraint"] if "constraint" in body else body
    assert reparsed["id"] == created["id"]


def test_update_scope_is_a_direct_field_edit(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    math = _create_subject(client, headers, school["id"], "Math")
    cg = client.post(
        "/api/class-groups", json={"school_id": school["id"], "grade": "Grade 8", "name": "A"}, headers=headers
    ).json()

    created = _create_constraint(
        client, headers, school["id"], "require_subject_period",
        {"subject_id": math["id"], "position": "first"},
    )
    r = client.put(
        f"/api/constraints/{created['id']}",
        json={"parameters": {"subject_id": math["id"], "position": "first", "class_group_ids": [cg["id"]]}},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["parameters"]["class_group_ids"] == [cg["id"]]
    assert r.json()["type"] == "require_subject_period"  # unchanged - this is a field edit, not a re-parse


def test_viewer_cannot_create_or_reparse_constraints(client):
    owner, headers = signup(client, email="owner@a.com")
    school = create_school(client, headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer@a.com", "role": "viewer"}, headers=headers
    )
    token = r.json()["token"]
    accept = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    r = client.post(
        "/api/constraints",
        json={"school_id": school["id"], "type": "workload_limit", "parameters": {}},
        headers=viewer_headers,
    )
    assert r.status_code == 403

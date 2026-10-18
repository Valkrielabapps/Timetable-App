"""
Tests for POST /api/constraints/batch (app/routers/constraints.py's
parse_and_create_constraints_batch) — the batch counterpart to /parse.
Covers both paths through _resolve_constraints_batch_text: the LLM batch
call (mocked here, never a real API call) and the per-line fallback that
kicks in when it's unavailable, which in this test env means "always"
(no ANTHROPIC_API_KEY is set — same as every other constraint test file).
"""
from unittest.mock import patch

from app.core.config import settings
from app.services.llm_constraint_parser import ParsedConstraint
from tests.conftest import create_school, signup


def _create_subject(client, headers, school_id, name):
    r = client.post("/api/subjects", json={"school_id": school_id, "name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _create_teacher(client, headers, school_id, name):
    r = client.post("/api/teachers", json={"school_id": school_id, "name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_batch_without_llm_falls_back_to_one_rule_per_line(client):
    """No ANTHROPIC_API_KEY in this test env (see conftest.py), so this
    exercises the per-line regex fallback end to end — two lines, each
    independently recognizable by the regex parser, should become two
    separate Constraint rows."""
    assert settings.anthropic_api_key is None
    _, headers = signup(client)
    school = create_school(client, headers)
    _create_teacher(client, headers, school["id"], "Mrs. Sharma")
    _create_subject(client, headers, school["id"], "PE")

    r = client.post(
        "/api/constraints/batch",
        json={
            "school_id": school["id"],
            "text": "Mrs. Sharma can only teach 15 periods a week\nNo PE on Fridays",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()["created"]
    assert len(body) == 2
    types = {item["constraint"]["type"] for item in body}
    assert types == {"workload_limit", "no_subject_day"}
    assert all(item["enforced"] for item in body)


def test_batch_ignores_blank_lines(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    _create_teacher(client, headers, school["id"], "Mrs. Sharma")

    r = client.post(
        "/api/constraints/batch",
        json={"school_id": school["id"], "text": "Mrs. Sharma can only teach 15 periods a week\n\n\n"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert len(r.json()["created"]) == 1


def test_batch_with_unparseable_text_returns_400(client):
    _, headers = signup(client)
    school = create_school(client, headers)

    r = client.post(
        "/api/constraints/batch",
        json={"school_id": school["id"], "text": "   \n  \n"},
        headers=headers,
    )
    assert r.status_code == 400


def _ir_parse(rule_dict):
    from app.services.constraint_ir import rule_from_dict
    from app.services.llm_ir_parser import IRParse
    return IRParse(rule=rule_from_dict(rule_dict), sentence="")


def _unclear():
    from app.services.llm_ir_parser import IRParse, Unclear
    return IRParse(unclear=Unclear(reason="ambiguous", explanation="?"))


def test_batch_reads_each_line_with_the_rule_parser(client):
    """Each line goes through the same parser as a single rule, so a pasted
    list can say things the older nine types can't - here a teacher-per-day
    cap and "right after lunch" - and they are saved as applied rules."""
    _, headers = signup(client)
    school = create_school(client, headers)
    _create_subject(client, headers, school["id"], "Physical Education")
    rules = {
        "No teacher should teach more than 6 periods in a day.":
            {"form": "count", "scope": ["teacher", "day"], "selector": {}, "relation": "<=", "value": 6},
        "No Physical Education right after lunch.":
            {"form": "count", "scope": [], "selector": {"subjects": ["Physical Education"], "period_orders": [6]},
             "relation": "==", "value": 0},
    }
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_rule_llm", side_effect=lambda text, *a, **k: _ir_parse(rules[text])):
            r = client.post("/api/constraints/batch", headers=headers,
                            json={"school_id": school["id"], "text": "\n".join(rules)})
    assert r.status_code == 201, r.text
    body = r.json()["created"]
    assert [item["constraint"]["type"] for item in body] == ["ir", "ir"]
    assert all(item["enforced"] for item in body)
    assert [item["constraint"]["source_text"] for item in body] == list(rules)


def test_a_line_the_rule_parser_cannot_read_falls_back(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    teacher = _create_teacher(client, headers, school["id"], "Mrs. Sharma")
    fake = ParsedConstraint(type="workload_limit", description="Mrs. Sharma: 12 periods/week",
                            teacher_name="Mrs. Sharma", max_periods_per_week=12)
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_rule_llm", return_value=_unclear()), \
             patch("app.routers.constraints.parse_constraint_llm", return_value=fake):
            r = client.post("/api/constraints/batch", headers=headers,
                            json={"school_id": school["id"], "text": "Mrs. Sharma teaches at most 12 periods a week"})
    assert r.status_code == 201, r.text
    (item,) = r.json()["created"]
    assert item["constraint"]["type"] == "workload_limit"
    assert item["constraint"]["parameters"]["teacher_id"] == teacher["id"]


def test_pasting_the_same_rules_again_adds_nothing(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    rule = {"form": "count", "scope": ["teacher", "day"], "selector": {}, "relation": "<=", "value": 6}
    text = "No teacher should teach more than 6 periods in a day.\nNo teacher should teach more than 6 periods in a day."
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_rule_llm", return_value=_ir_parse(rule)):
            first = client.post("/api/constraints/batch", headers=headers, json={"school_id": school["id"], "text": text})
            second = client.post("/api/constraints/batch", headers=headers, json={"school_id": school["id"], "text": text})
    assert first.status_code == 201 and len(first.json()["created"]) == 1  # the same line twice is one rule
    assert second.status_code == 400 and "already" in second.json()["detail"]
    listed = client.get(f"/api/constraints?school_id={school['id']}", headers=headers).json()
    assert len(listed) == 1

def test_batch_falls_back_to_per_line_when_llm_batch_call_fails(client):
    """parse_constraints_batch_llm returning None (its documented
    never-raises failure signal) must fall back to per-line parsing, not
    silently produce zero constraints."""
    _, headers = signup(client)
    school = create_school(client, headers)
    _create_teacher(client, headers, school["id"], "Mrs. Sharma")

    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_constraints_batch_llm", return_value=None):
            r = client.post(
                "/api/constraints/batch",
                json={"school_id": school["id"], "text": "Mrs. Sharma can only teach 15 periods a week"},
                headers=headers,
            )
    assert r.status_code == 201, r.text
    assert len(r.json()["created"]) == 1
    assert r.json()["created"][0]["constraint"]["type"] == "workload_limit"


def test_batch_flags_conflicts_between_two_rules_in_the_same_paste(client):
    """Two contradictory rules submitted in the SAME batch call must be
    flagged against each other, exactly like two separate /parse calls
    would be — conflict detection is DB-driven (queries every saved
    constraint), not scoped to "this batch" vs "earlier saves", so this
    should fall out for free rather than needing special-case logic."""
    _, headers = signup(client)
    school = create_school(client, headers)
    _create_subject(client, headers, school["id"], "Math")

    fake_parsed = [
        ParsedConstraint(
            type="subject_period_position", mode="require", position="first",
            subject_name="Math", description="Math must be first period",
        ),
        ParsedConstraint(
            type="subject_period_position", mode="require", position="last",
            subject_name="Math", description="Math must be last period",
        ),
    ]
    by_line = {"Math must be first period.": fake_parsed[0], "Math must be last period.": fake_parsed[1]}
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_rule_llm", return_value=_unclear()), \
             patch("app.routers.constraints.parse_constraint_llm", side_effect=lambda text, *a, **k: by_line[text]):
            r = client.post(
                "/api/constraints/batch",
                json={"school_id": school["id"], "text": "Math must be first period.\nMath must be last period."},
                headers=headers,
            )
    assert r.status_code == 201, r.text
    body = r.json()["created"]
    assert len(body) == 2
    assert body[0]["constraint"]["conflicts"] and body[1]["constraint"]["conflicts"]


def test_viewer_cannot_batch_create_constraints(client):
    owner, headers = signup(client, email="owner@a.com")
    school = create_school(client, headers)
    r = client.post(
        f"/api/schools/{school['id']}/invites", json={"email": "viewer@a.com", "role": "viewer"}, headers=headers
    )
    token = r.json()["token"]
    accept = client.post(f"/api/invites/{token}/accept", json={"name": "V", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {accept.json()['access_token']}"}

    r = client.post(
        "/api/constraints/batch",
        json={"school_id": school["id"], "text": "anything"},
        headers=viewer_headers,
    )
    assert r.status_code == 403



def test_a_line_with_a_question_is_handed_back_not_saved(client):
    """The rule parser asked a question and the older parser only managed a
    rule the solver ignores: the line comes back to be added on its own,
    rather than becoming a card marked "not applied"."""
    from app.services.llm_ir_parser import IRParse, Unclear
    _, headers = signup(client)
    school = create_school(client, headers)
    asked = IRParse(unclear=Unclear(reason="ambiguous", explanation="?", question="Saturday has no lunch - weekdays only?"))
    junk = ParsedConstraint(type="scheduling_rule", description="No PE right after lunch")
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("app.routers.constraints.parse_rule_llm", return_value=asked), \
             patch("app.routers.constraints.parse_constraint_llm", return_value=junk):
            r = client.post("/api/constraints/batch", headers=headers,
                            json={"school_id": school["id"], "text": "No Physical Education right after lunch."})
    assert r.status_code == 201, r.text
    assert r.json()["created"] == []
    (line,) = r.json()["unread"]
    assert line["text"] == "No Physical Education right after lunch."
    assert "Saturday" in line["reason"]
    assert client.get(f"/api/constraints?school_id={school['id']}", headers=headers).json() == []


def test_a_failed_call_is_retried(client):
    from app.services.constraint_ir import rule_from_dict
    from app.services.llm_ir_parser import IRParse
    _, headers = signup(client)
    school = create_school(client, headers)
    ok = IRParse(rule=rule_from_dict({"form": "count", "scope": ["teacher", "day"], "selector": {}, "relation": "<=", "value": 6}))
    with patch.object(settings, "anthropic_api_key", "fake-key"), patch("app.routers.constraints.time.sleep"):
        with patch("app.routers.constraints.parse_rule_llm", side_effect=[None, ok]) as parse:
            r = client.post("/api/constraints/batch", headers=headers,
                            json={"school_id": school["id"], "text": "No teacher more than 6 periods a day"})
    assert parse.call_count == 2
    assert [c["constraint"]["type"] for c in r.json()["created"]] == ["ir"]

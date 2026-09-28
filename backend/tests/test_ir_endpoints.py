"""
Tests for POST /api/constraints/interpret and /confirm.

The LLM is stubbed. What is under test is the contract around it: that
interpret saves nothing, that confirm stores the rule the admin was shown
rather than re-deriving it, and that a rule naming someone not on staff is
stopped while they are still looking at the sentence.

That last one is the whole reason the two steps are separate. With the nine
named types a rule the parser couldn't place landed in `scheduling_rule` and
sat in the UI marked unenforced, so a misreading was visible. The IR removes
that signal - nearly any sentence yields a valid rule - so the rendered
sentence and someone agreeing to it is what replaces it.
"""
import pytest

from app.models.school import Constraint
from app.services.constraint_ir import rule_from_dict
from app.services.llm_ir_parser import IRParse, Unclear
from tests.conftest import create_school, signup

RAO_DAILY_CAP = {
    "form": "count", "scope": ["teacher", "day"],
    "selector": {"teachers": ["Mrs. Rao"]}, "relation": "<=", "value": 6,
    "strength": "required",
}


@pytest.fixture
def school(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    client.post("/api/teachers",
                json={"school_id": school["id"], "name": "Mrs. Rao", "qualified_subject_ids": []},
                headers=headers)
    client.post("/api/subjects", json={"school_id": school["id"], "name": "Maths"}, headers=headers)
    return school, headers


def _stub(monkeypatch, result):
    monkeypatch.setattr("app.routers.constraints.parse_rule_llm",
                        lambda *a, **k: result)


def _understood(rule_dict):
    from app.services.constraint_ir_english import render
    rule = rule_from_dict(rule_dict)
    return IRParse(rule=rule, sentence=render(rule))


# ---------------------------------------------------------------------------
# interpret
# ---------------------------------------------------------------------------


def test_interpret_returns_the_sentence_and_saves_nothing(client, school, monkeypatch):
    school_row, headers = school
    _stub(monkeypatch, _understood(RAO_DAILY_CAP))

    r = client.post("/api/constraints/interpret",
                    json={"school_id": school_row["id"], "text": "Rao max 6 a day"},
                    headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["understood"] is True
    assert body["sentence"] == "Mrs. Rao has at most 6 periods on any day."
    assert body["rule"]["form"] == "count"

    listed = client.get(f"/api/constraints?school_id={school_row['id']}", headers=headers)
    assert listed.json() == []


def test_interpret_passes_a_decline_straight_through(client, school, monkeypatch):
    """The parser is given a tool to say it cannot read a sentence, and that
    answer is worth more than a guess - so it must survive the trip to the UI
    intact, question and all."""
    school_row, headers = school
    _stub(monkeypatch, IRParse(unclear=Unclear(
        reason="too_vague",
        explanation="\"Balanced\" doesn't have a measurable meaning here.",
        question="What would make the timetable balanced - even daily loads, or fewer gaps?",
    )))

    r = client.post("/api/constraints/interpret",
                    json={"school_id": school_row["id"], "text": "make it balanced"},
                    headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["understood"] is False
    assert body["reason"] == "too_vague"
    assert "measurable" in body["explanation"]
    assert body["question"]


def test_interpret_flags_a_name_the_school_does_not_have(client, school, monkeypatch):
    """Caught while they are still looking at the sentence they typed, rather
    than at solve time on a timetable that has already been generated."""
    school_row, headers = school
    _stub(monkeypatch, _understood({
        "form": "count", "scope": [], "selector": {"teachers": ["Mr. Verma"]},
        "relation": "==", "value": 0,
    }))

    r = client.post("/api/constraints/interpret",
                    json={"school_id": school_row["id"], "text": "Verma is off Mondays"},
                    headers=headers)
    assert r.json()["unknown_names"] == ["Mr. Verma"]


def test_interpret_says_so_when_the_parser_is_unavailable(client, school, monkeypatch):
    """No falling back to the regex parser here. This endpoint's contract is
    "what did you understand", and a keyword guess presented as an
    interpretation is the opposite of what confirming is for."""
    school_row, headers = school
    _stub(monkeypatch, None)

    r = client.post("/api/constraints/interpret",
                    json={"school_id": school_row["id"], "text": "anything"},
                    headers=headers)
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


def test_confirm_stores_the_rule_that_was_shown(client, school):
    school_row, headers = school
    r = client.post("/api/constraints/confirm",
                    json={"school_id": school_row["id"], "rule": RAO_DAILY_CAP,
                          "source_text": "Rao max 6 a day"},
                    headers=headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == "ir"
    assert body["parameters"]["form"] == "count"
    assert body["parameters"]["scope"] == ["teacher", "day"]
    # The description is the confirmed sentence, not a separate summary: it is
    # what they agreed to, so it is what they should keep being shown.
    assert body["description"] == "Mrs. Rao has at most 6 periods on any day."
    assert body["source_text"] == "Rao max 6 a day"
    assert body["parsed_by"] == "llm-ir"
    assert body["enforced"] is True


def test_a_confirmed_preference_is_stored_soft(client, school):
    """Strength is said out loud in the sentence the admin confirmed, so it has
    to survive into is_hard - a preference silently stored as a requirement
    would make the timetable infeasible instead of imperfect."""
    school_row, headers = school
    soft = {**RAO_DAILY_CAP, "strength": "preference"}
    r = client.post("/api/constraints/confirm",
                    json={"school_id": school_row["id"], "rule": soft,
                          "source_text": "try to keep Rao under 6 a day"},
                    headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["is_hard"] is False
    assert r.json()["description"].startswith("Where it can be arranged")


def test_confirm_refuses_a_rule_naming_someone_not_on_staff(client, school):
    school_row, headers = school
    r = client.post("/api/constraints/confirm",
                    json={"school_id": school_row["id"],
                          "rule": {"form": "count", "scope": [],
                                   "selector": {"teachers": ["Mr. Verma"]},
                                   "relation": "==", "value": 0},
                          "source_text": "Verma is off Mondays"},
                    headers=headers)
    assert r.status_code == 422
    assert "Mr. Verma" in r.json()["detail"]


def test_confirm_refuses_a_malformed_rule(client, school):
    school_row, headers = school
    r = client.post("/api/constraints/confirm",
                    json={"school_id": school_row["id"],
                          "rule": {"form": "teleport", "scope": []},
                          "source_text": "nonsense"},
                    headers=headers)
    assert r.status_code == 422


def test_a_confirmed_rule_appears_in_the_normal_list(client, school):
    """IR rules are ordinary Constraint rows, so everything that already reads
    that list keeps working without knowing they exist."""
    school_row, headers = school
    client.post("/api/constraints/confirm",
                json={"school_id": school_row["id"], "rule": RAO_DAILY_CAP,
                      "source_text": "Rao max 6 a day"},
                headers=headers)
    listed = client.get(f"/api/constraints?school_id={school_row['id']}", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["type"] == "ir"
    assert listed[0]["enforced"] is True


def test_a_confirmed_rule_can_be_deleted_like_any_other(client, school):
    school_row, headers = school
    created = client.post("/api/constraints/confirm",
                          json={"school_id": school_row["id"], "rule": RAO_DAILY_CAP,
                                "source_text": "x"},
                          headers=headers).json()
    assert client.delete(f"/api/constraints/{created['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/constraints?school_id={school_row['id']}", headers=headers).json() == []


def test_a_stored_rule_that_stops_validating_reports_as_unenforced(client, school, orm_db):
    """The badge has to track what the solver actually runs. A row written by
    an older version that no longer parses is exactly the case the old nine
    types got wrong - shown as enforced, doing nothing."""
    school_row, headers = school
    created = client.post("/api/constraints/confirm",
                          json={"school_id": school_row["id"], "rule": RAO_DAILY_CAP,
                                "source_text": "x"},
                          headers=headers).json()

    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        row = db.get(Constraint, created["id"])
        row.parameters = {"form": "teleport"}
        db.commit()
    finally:
        db.close()

    fetched = client.get(f"/api/constraints/{created['id']}", headers=headers).json()
    assert fetched["enforced"] is False

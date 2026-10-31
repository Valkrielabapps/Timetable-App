"""Rule-reading moments are recorded for the Timetablz team, and never get in
the way of the rule itself."""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.school import RuleReadEvent
from app.services import rule_events
from app.services.llm_ir_parser import IRParse, Unclear
from tests.conftest import verify_email, create_school, signup
from tests.test_ir_endpoints import RAO_DAILY_CAP, _stub, _understood

ADMIN = "staff@timetablz.com"


@pytest.fixture
def school(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    client.post("/api/teachers", json={"school_id": school["id"], "name": "Mrs. Rao", "qualified_subject_ids": []},
                headers=headers)
    return school["id"], headers


@pytest.fixture
def staff(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", ADMIN)
    _, h = signup(client, email=ADMIN)
    verify_email(ADMIN)
    return h


def _events(sid):
    db = SessionLocal()
    try:
        return [(e.kind, e.text) for e in db.query(RuleReadEvent).filter(RuleReadEvent.school_id == sid).order_by(RuleReadEvent.id)]
    finally:
        db.close()


def test_a_question_from_the_parser_is_recorded(client, school, monkeypatch):
    sid, h = school
    _stub(monkeypatch, IRParse(unclear=Unclear(reason="too_vague", explanation="Vague.", question="Which days?")))
    client.post("/api/constraints/interpret", json={"school_id": sid, "text": "balance it out"}, headers=h)
    assert _events(sid) == [("unclear", "balance it out")]


def test_read_then_confirmed_is_two_moments(client, school, monkeypatch):
    sid, h = school
    _stub(monkeypatch, _understood(RAO_DAILY_CAP))
    r = client.post("/api/constraints/interpret", json={"school_id": sid, "text": "Rao max 6 a day"}, headers=h)
    client.post("/api/constraints/confirm", json={"school_id": sid, "rule": r.json()["rule"],
                                                  "source_text": "Rao max 6 a day"}, headers=h)
    assert _events(sid) == [("interpreted", "Rao max 6 a day"), ("confirmed", "Rao max 6 a day")]


def test_cancel_and_reword_are_reported_by_the_page(client, school):
    sid, h = school
    for action in ("cancelled", "reworded"):
        r = client.post("/api/constraints/feedback", headers=h,
                        json={"school_id": sid, "text": "no pe after lunch", "action": action, "shown": "..."})
        assert r.status_code == 204, r.text
    assert [k for k, _ in _events(sid)] == ["cancelled", "reworded"]
    bad = client.post("/api/constraints/feedback", headers=h, json={"school_id": sid, "text": "x", "action": "liked"})
    assert bad.status_code == 422


def test_someone_elses_school_cannot_be_reported_on(client, school):
    sid, _ = school
    _, stranger = signup(client, email="stranger@else.com")
    r = client.post("/api/constraints/feedback", headers=stranger,
                    json={"school_id": sid, "text": "x", "action": "cancelled"})
    assert r.status_code in (403, 404)


def test_deleting_a_rule_soon_after_saving_it_is_recorded(client, school, monkeypatch):
    sid, h = school
    _stub(monkeypatch, _understood(RAO_DAILY_CAP))
    rule = client.post("/api/constraints/interpret", json={"school_id": sid, "text": "Rao max 6"}, headers=h).json()["rule"]
    saved = client.post("/api/constraints/confirm", json={"school_id": sid, "rule": rule, "source_text": "Rao max 6"},
                        headers=h).json()
    assert client.delete(f"/api/constraints/{saved['id']}", headers=h).status_code == 204
    assert _events(sid)[-1] == ("quick_delete", "Rao max 6")


def test_a_logging_failure_never_breaks_the_rule(client, school, monkeypatch):
    sid, h = school
    _stub(monkeypatch, _understood(RAO_DAILY_CAP))

    class Broken:
        def __call__(self):
            raise RuntimeError("database down")
    monkeypatch.setattr(rule_events, "SessionLocal", Broken())
    r = client.post("/api/constraints/interpret", json={"school_id": sid, "text": "Rao max 6 a day"}, headers=h)
    assert r.status_code == 200
    saved = client.post("/api/constraints/confirm", json={"school_id": sid, "rule": r.json()["rule"],
                                                          "source_text": "Rao max 6 a day"}, headers=h)
    assert saved.status_code == 201


def test_the_admin_page_lists_problems_and_files_them(client, school, staff, monkeypatch):
    sid, h = school
    _stub(monkeypatch, _understood(RAO_DAILY_CAP))
    client.post("/api/constraints/interpret", json={"school_id": sid, "text": "Rao max 6 a day"}, headers=h)
    client.post("/api/constraints/feedback", headers=h,
                json={"school_id": sid, "text": "Rao max 6 a day", "action": "cancelled"})

    assert client.get("/api/admin/rule-events", headers=h).status_code == 404  # school admins can't see it
    body = client.get("/api/admin/rule-events", headers=staff).json()
    assert [e["kind"] for e in body["events"]] == ["cancelled"]  # the success isn't listed by default
    assert body["counts"]["interpreted"] == 1
    event = body["events"][0]
    assert event["school_name"]

    r = client.patch(f"/api/admin/rule-events/{event['id']}", headers=staff, json={"triage": "misread"})
    assert r.json()["triage"] == "misread"
    assert client.get("/api/admin/rule-events?triage=none", headers=staff).json()["events"] == []
    assert client.patch(f"/api/admin/rule-events/{event['id']}", headers=staff, json={"triage": "meh"}).status_code == 422

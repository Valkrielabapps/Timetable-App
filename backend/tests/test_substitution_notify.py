"""
Emailing a day's cover to the teachers taking it, with calendar invites
that update and cancel as the cover changes.
"""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, Subject, Teacher
from app.services import email_service
from app.services.email_service import send_cover_email as _real_send_cover_email
from app.services.substitution_notify import _times
from tests.conftest import create_school, signup


@pytest.mark.parametrize("label,expected", [
    ("9:00-9:45", ((9, 0), (9, 45))), ("Period 3 (10.30 - 11.15)", ((10, 30), (11, 15))),
    ("1:30 pm to 2:15 pm", ((13, 30), (14, 15))), ("2:15-3:00", ((14, 15), (15, 0))),
    ("Period 3", None), ("Lunch", None),
])
def test_times_are_read_from_period_labels(label, expected):
    assert _times(label) == expected


@pytest.fixture
def day(client, monkeypatch):
    from app.services import substitution_notify

    monkeypatch.setattr(substitution_notify, "_pace", lambda: None)
    monkeypatch.setattr(settings, "resend_api_key", "test")
    sent = []
    monkeypatch.setattr(email_service, "send_cover_email",
                        lambda to, subject, html, ics, reply_to=None: sent.append((to, subject, html, ics)) or True)
    monkeypatch.setattr(email_service, "send_batch",
                        lambda msgs, ctx="": [sent.append((m["to"], m["subject"], m["html"], None)) or True for m in msgs])
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        p1 = Period(school_id=sid, day_of_week=1, order=0, label="9:00-9:45")
        p2 = Period(school_id=sid, day_of_week=1, order=1, label="Period 2")
        maths = Subject(school_id=sid, name="Maths")
        rao = Teacher(school_id=sid, name="Mrs. Rao", email="rao@school.in")
        iyer = Teacher(school_id=sid, name="Mr. Iyer", email="iyer@school.in")
        das = Teacher(school_id=sid, name="Ms. Das", email="das@school.in")
        nomail = Teacher(school_id=sid, name="Mr. Khan")
        cg = ClassGroup(school_id=sid, grade="Grade 7", name="B")
        db.add_all([p1, p2, maths, rao, iyer, das, nomail, cg])
        db.commit()
        ids = dict(school=sid, p1=p1.id, p2=p2.id, maths=maths.id, rao=rao.id, iyer=iyer.id, das=das.id,
                   khan=nomail.id, cg=cg.id)
    finally:
        db.close()
    return ids, h, sent


def _save(client, w, h, covers):
    r = client.post(f"/api/schools/{w['school']}/substitutions", json={
        "date": "2026-11-17",
        "absences": [{"teacher_id": w["rao"], "period_ids": None}],
        "changes": [{"period_id": w[p], "absent_teacher_id": w["rao"], "substituting_teacher_id": w[who],
                     "class_group_id": w["cg"], "subject_id": w["maths"]} for p, who in covers],
    }, headers=h)
    assert r.status_code == 201, r.text


def _notify(client, w, h, everyone=False):
    r = client.post(f"/api/schools/{w['school']}/substitutions/notify",
                    json={"date": "2026-11-17", "everyone": everyone}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_each_covering_teacher_gets_their_periods_and_a_calendar_invite(client, day):
    w, h, sent = day
    _save(client, w, h, [("p1", "iyer"), ("p2", "khan")])
    r = _notify(client, w, h)
    assert r["sent"] == ["Mr. Iyer"] and r["no_email"] == ["Mr. Khan"] and r["email_configured"] is True
    (to, subject, body, ics), = sent
    assert to == "iyer@school.in" and "Cover on Tuesday 17 November 2026: 1 period" == subject
    assert "Period 1: Grade 7 - B Maths, for Mrs. Rao" in body
    assert "METHOD:REQUEST" in ics and "DTSTART;TZID=Asia/Kolkata:20261117T090000" in ics
    assert "DTEND;TZID=Asia/Kolkata:20261117T094500" in ics
    assert "SUMMARY:Cover: Grade 7 - B Maths (Period 1)" in ics and "ATTENDEE;CN=Mr. Iyer" in ics


def test_a_period_with_no_time_is_an_all_day_entry(client, day):
    w, h, sent = day
    _save(client, w, h, [("p2", "das")])
    _notify(client, w, h)
    assert "DTSTART;VALUE=DATE:20261117" in sent[0][3] and "DTEND;VALUE=DATE:20261118" in sent[0][3]


def test_changing_the_cover_updates_one_calendar_and_cancels_the_other(client, day):
    w, h, sent = day
    _save(client, w, h, [("p1", "iyer")])
    _notify(client, w, h)
    uid = next(l for l in sent[0][3].splitlines() if l.startswith("UID:"))
    sent.clear()
    _save(client, w, h, [("p1", "das")])  # same date: replaces the cover
    r = _notify(client, w, h)
    assert r["sent"] == ["Ms. Das"] and r["cancelled"] == 1
    by_to = {s[0]: s for s in sent}
    assert uid in by_to["das@school.in"][3]  # the same lesson, now Das's
    assert "METHOD:CANCEL" in by_to["iyer@school.in"][3] and uid in by_to["iyer@school.in"][3]
    assert "cancelled" in by_to["iyer@school.in"][1]


def test_everyone_can_get_the_whole_arrangement(client, day):
    w, h, sent = day
    _save(client, w, h, [("p1", "iyer")])
    r = _notify(client, w, h, everyone=True)
    assert r["summary_sent"] == 2  # Rao and Das; Iyer has their own email, Khan has none
    summary = [s for s in sent if s[1].startswith("Cover arrangement")]
    assert {s[0] for s in summary} == {"rao@school.in", "das@school.in"}
    assert "Covered by" in summary[0][2] and summary[0][3] is None


def test_nothing_saved_says_so_and_viewers_cannot_send(client, day):
    w, h, _ = day
    r = client.post(f"/api/schools/{w['school']}/substitutions/notify", json={"date": "2026-11-18"}, headers=h)
    assert r.status_code == 400 and "Save the cover" in r.json()["detail"]
    _, other = signup(client, email="o@x.com")
    r = client.post(f"/api/schools/{w['school']}/substitutions/notify", json={"date": "2026-11-17"}, headers=other)
    assert r.status_code in (403, 404)


def test_a_refusal_from_resend_is_explained(client, day, monkeypatch):
    w, h, _ = day
    monkeypatch.setattr(email_service, "send_cover_email", _real_send_cover_email)  # the real one, this time

    class Refused:
        status_code = 403
        text = '{"message":"You can only send testing emails to your own email address. To send emails to other recipients, please verify a domain"}'

    monkeypatch.setattr(email_service.requests, "post", lambda *a, **k: Refused())
    _save(client, w, h, [("p1", "iyer")])
    r = _notify(client, w, h)
    assert r["failed"] == ["Mr. Iyer"] and "isn't verified in Resend" in r["errors"][0]


def test_too_many_at_once_is_retried(monkeypatch):
    calls = []

    class Busy:
        status_code = 429
        text = "rate limited"

    class Ok:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(settings, "resend_api_key", "test")
    monkeypatch.setattr(email_service.time, "sleep", lambda s: None)
    monkeypatch.setattr(email_service.requests, "post", lambda *a, **k: calls.append(k["json"]) or (Busy() if len(calls) < 3 else Ok()))
    assert _real_send_cover_email("a@b.c", "Cover", "<p>x</p>", "BEGIN:VCALENDAR\r\nMETHOD:REQUEST\r\nEND:VCALENDAR") is True
    assert len(calls) == 3
    assert calls[0]["attachments"][0]["content_type"] == "text/calendar"


def test_a_hundred_and_fifty_go_in_two_requests(monkeypatch):
    calls = []

    class Ok:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(settings, "resend_api_key", "test")
    monkeypatch.setattr(email_service.requests, "post", lambda url, **k: calls.append((url, len(k["json"]))) or Ok())
    out = email_service.send_batch([{"to": f"t{i}@s.in", "subject": "s", "html": "h"} for i in range(150)])
    assert out == [True] * 150 and calls == [(email_service._RESEND_BATCH_URL, 100), (email_service._RESEND_BATCH_URL, 50)]


def test_a_used_up_quota_is_said_plainly_and_not_retried(monkeypatch):
    calls = []

    class Quota:
        status_code = 429
        text = '{"name":"daily_quota_exceeded","message":"You have reached your daily email sending quota."}'

    monkeypatch.setattr(settings, "resend_api_key", "test")
    monkeypatch.setattr(email_service.requests, "post", lambda *a, **k: calls.append(1) or Quota())
    assert email_service.send_batch([{"to": "a@b.c", "subject": "s", "html": "h"}]) == [False]
    assert len(calls) == 1 and "Upgrade Resend to Pro" in email_service.last_error()

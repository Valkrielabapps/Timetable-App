"""
Where schools get stuck, on the admin page: failed generations, blocked
moves, setup problems and "Send to Timetablz support", each with enough to
reproduce it.
"""
import pytest

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.problems import ProblemEvent
from app.models.school import Timetable
from tests.conftest import create_school, signup, verify_email

ADMIN = "staff@timetablz.com"


@pytest.fixture
def staff(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", ADMIN)
    _, h = signup(client, email=ADMIN)
    verify_email(ADMIN)
    return h


@pytest.fixture
def school(client):
    """Grade 9 A asks for 6 periods of Maths in a 4-period week."""
    _, h = signup(client, email="head@school.in")
    sid = create_school(client, h)["id"]

    def post(url, body):
        r = client.post(url, json=body, headers=h)
        assert r.status_code in (200, 201), r.text
        return r.json()

    for order in range(4):
        post("/api/periods", {"school_id": sid, "day_of_week": 0, "order": order, "label": f"P{order + 1}"})
    maths = post("/api/subjects", {"school_id": sid, "name": "Maths"})["id"]
    post("/api/teachers", {"school_id": sid, "name": "Asha", "email": "asha@school.in", "qualified_subject_ids": [maths]})
    cg = post("/api/class-groups", {"school_id": sid, "grade": "Grade 9", "name": "A"})["id"]
    post(f"/api/class-groups/{cg}/requirements", {"class_group_id": cg, "subject_id": maths, "periods_per_week": 6})
    return {"sid": sid, "h": h, "cg": cg}


def rows(**match):
    db = SessionLocal()
    try:
        return db.query(ProblemEvent).filter_by(**match).order_by(ProblemEvent.id).all()
    finally:
        db.close()


def test_a_failed_generation_is_logged_with_the_schools_setup(client, school):
    from app.routers.timetables import _run_generation_job
    db = SessionLocal()
    try:
        tt = Timetable(school_id=school["sid"], status="generating")
        db.add(tt)
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    _run_generation_job(tt_id, school["sid"])
    [row] = rows(kind="generation_failed")
    assert row.school_id == school["sid"] and row.timetable_id == tt_id
    assert "Maths" in row.summary and row.detail["reasons"]
    snap = row.snapshot
    assert len(snap["periods"]) == 4 and snap["requirements"][0]["periods_per_week"] == 6
    assert snap["teachers"][0]["name"] == "Asha" and "email" not in snap["teachers"][0]


def test_setup_problems_are_logged_once_a_day(client, school):
    for _ in range(3):
        assert client.get(f"/api/schools/{school['sid']}/setup-check", headers=school["h"]).status_code == 200
    logged = rows(kind="setup_error")
    # One row per problem, however many times the page was opened.
    assert sorted(r.detail["check"] for r in logged) == ["section_overfull", "teacher_overloaded"]
    assert all(r.snapshot is None for r in logged)


def test_send_to_support_saves_a_snapshot(client, school, staff):
    r = client.post(f"/api/schools/{school['sid']}/support-snapshot", headers=school["h"], json={
        "message": "Maths won't fit, what do I change?",
        "context": {"where": "the failed-generation dialog", "reasons": ["Grade 9 A needs 6 periods"]},
    })
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    listed = client.get("/api/admin/problems?kind=support_request", headers=staff).json()
    [p] = listed["problems"]
    assert p["id"] == pid and p["has_snapshot"] and p["summary"] == "Maths won't fit, what do I change?"
    assert p["detail"]["email"] == "head@school.in"
    snap = client.get(f"/api/admin/problems/{pid}/snapshot", headers=staff)
    assert snap.status_code == 200 and "attachment" in snap.headers["content-disposition"]
    assert snap.json()["class_groups"][0]["name"] == "A"


def test_only_the_schools_own_people_can_send(client, school):
    _, other = signup(client, email="other@school.in")
    r = client.post(f"/api/schools/{school['sid']}/support-snapshot", headers=other, json={"message": "hi"})
    assert r.status_code in (403, 404)


def test_a_blocked_move_is_logged_once(client, school, staff):
    from app.models.school import TimetableEntry
    db = SessionLocal()
    try:
        from app.models.school import Period, Subject, Teacher
        tt = Timetable(school_id=school["sid"], status="draft", solver_status="optimal")
        db.add(tt)
        db.commit()
        periods = db.query(Period).filter_by(school_id=school["sid"]).order_by(Period.order).all()
        maths = db.query(Subject).filter_by(school_id=school["sid"]).one()
        asha = db.query(Teacher).filter_by(school_id=school["sid"]).one()
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=school["cg"], subject_id=maths.id,
                              teacher_id=asha.id, period_id=periods[0].id, locked=True))
        db.commit()
        tt_id, p = tt.id, [x.id for x in periods]
    finally:
        db.close()
    for _ in range(2):
        r = client.post(f"/api/timetables/{tt_id}/suggest-move", headers=school["h"],
                        json={"class_group_id": school["cg"], "from_period_id": p[0], "to_period_id": p[1]})
        assert r.json()["status"] == "blocked"
    [row] = rows(kind="move_blocked")
    assert "locked" in row.summary and row.detail["from"] == "Mon P1" and row.detail["fixes_found"] == 0


def test_the_admin_list_marks_and_groups(client, school, staff):
    client.get(f"/api/schools/{school['sid']}/setup-check", headers=school["h"])
    data = client.get("/api/admin/problems", headers=staff).json()
    assert data["counts"]["setup_error"] == 2
    assert {"kind": "setup_error", "label": "section_overfull", "schools": 1} in data["common"]
    pid = data["problems"][0]["id"]
    r = client.patch(f"/api/admin/problems/{pid}", headers=staff, json={"status": "school_setup", "note": "Their setup"})
    assert r.json() == {"id": pid, "status": "school_setup", "note": "Their setup"}
    # Open only by default: the one marked has gone from the list.
    assert pid not in [p["id"] for p in client.get("/api/admin/problems", headers=staff).json()["problems"]]


def test_hidden_from_everyone_else(client, school):
    assert client.get("/api/admin/problems", headers=school["h"]).status_code in (403, 404)

"""A generation whose job died with the server process (a deploy, a restart)
is marked failed when it is next read, instead of spinning forever."""
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.school import Timetable
from app.routers import timetables as router
from tests.conftest import create_school, signup


def _generating(sid, created_at):
    db = SessionLocal()
    try:
        tt = Timetable(school_id=sid, status="generating", created_at=created_at)
        db.add(tt)
        db.commit()
        if created_at is None:
            # Inserting None lets the server default fill in "now"; rows from
            # before the column existed are genuinely empty, so empty it after.
            db.query(Timetable).filter(Timetable.id == tt.id).update({Timetable.created_at: None})
            db.commit()
        return tt.id
    finally:
        db.close()


def test_a_generation_from_before_a_restart_is_reported_as_interrupted(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    tt = _generating(sid, router._PROCESS_STARTED - timedelta(minutes=1))
    body = client.get(f"/api/timetables/{tt}", headers=h).json()
    assert body["status"] == "failed"
    assert "interrupted" in body["error_message"] and "Generate again" in body["error_message"]


def test_one_with_no_start_time_is_treated_the_same(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    tt = _generating(sid, None)
    assert client.get(f"/api/timetables/{tt}", headers=h).json()["status"] == "failed"


def test_a_generation_still_running_is_left_alone(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    tt = _generating(sid, datetime.now(timezone.utc))
    assert client.get(f"/api/timetables/{tt}", headers=h).json()["status"] == "generating"


def test_one_running_absurdly_long_is_stopped(client, monkeypatch):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    monkeypatch.setattr(router, "_PROCESS_STARTED", datetime.now(timezone.utc) - timedelta(hours=2))
    tt = _generating(sid, datetime.now(timezone.utc) - timedelta(minutes=30))
    body = client.get(f"/api/timetables/{tt}", headers=h).json()
    assert body["status"] == "failed" and "took far longer" in body["error_message"]

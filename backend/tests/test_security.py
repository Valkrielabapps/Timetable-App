"""
Security fixes from the October 2026 review. Each test is one hole that was
open, shown closed:

  - a school can't point its records at another school's teachers, rooms,
    subjects or periods - which used to read their names back;
  - new passwords need 8+ characters (old short ones still log in);
  - a signup with someone else's email can't later ride along when its real
    owner signs in with Google;
  - changing the password signs every other session out;
  - reset links are stored hashed, and using one cancels the others;
  - the admin page needs a verified email;
  - invite emails escape what the inviter typed, and are rate-limited;
  - one generation per school at a time;
  - uploads are capped in size, unpacked size and rows;
  - spreadsheet exports never contain live formulas;
  - API docs only in debug mode; security headers on every response;
  - text fields have length limits.
"""
import io
import zipfile
from unittest.mock import patch

import openpyxl
import pytest

from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.core.rate_limit import reset_quotas
from app.models.school import (
    ClassGroup, Period, Room, School, Subject, SubjectRequirement, Teacher, Timetable, TimetableEntry,
)
from app.models.user import PasswordResetToken, User
from tests.conftest import create_school, signup, verify_email


def _db():
    return SessionLocal()


# ---------------------------------------------------------------------------
# Cross-school ids
# ---------------------------------------------------------------------------


@pytest.fixture
def two_schools(client):
    """School A (ours, with a timetable of one lesson) and School B, whose
    teacher, room, subject and period we must never be able to use."""
    _, a = signup(client, email="a@a.com")
    _, b = signup(client, email="b@b.com")
    sa = create_school(client, a, name="A")["id"]
    sb = create_school(client, b, name="B")["id"]
    db = _db()
    try:
        maths_a, secret_b = Subject(school_id=sa, name="Maths"), Subject(school_id=sb, name="B-secret-subject")
        db.add_all([maths_a, secret_b])
        db.commit()
        ta, tb = Teacher(school_id=sa, name="A teacher"), Teacher(school_id=sb, name="B-secret-teacher")
        rb = Room(school_id=sb, name="B-secret-room")
        cga = ClassGroup(school_id=sa, grade="Grade 1", name="A")
        pa, pb = Period(school_id=sa, day_of_week=0, order=0), Period(school_id=sb, day_of_week=0, order=0)
        db.add_all([ta, tb, rb, cga, pa, pb])
        db.commit()
        tt = Timetable(school_id=sa, status="draft")
        db.add(tt)
        db.commit()
        e = TimetableEntry(timetable_id=tt.id, class_group_id=cga.id, subject_id=maths_a.id,
                           teacher_id=ta.id, period_id=pa.id)
        db.add(e)
        db.commit()
        ids = dict(sa=sa, sb=sb, maths_a=maths_a.id, secret_b=secret_b.id, ta=ta.id, tb=tb.id, rb=rb.id,
                   cga=cga.id, pa=pa.id, pb=pb.id, tt=tt.id, e=e.id)
    finally:
        db.close()
    return ids, a


def test_a_lesson_cannot_take_another_schools_teacher_room_or_period(client, two_schools):
    ids, a = two_schools
    for change in ({"teacher_id": ids["tb"]}, {"room_id": ids["rb"]}, {"period_id": ids["pb"]}):
        r = client.patch(f"/api/timetables/entries/{ids['e']}", json=change, headers=a)
        assert r.status_code == 404, (change, r.text)
        assert "secret" not in r.text
    # Its own teacher is fine.
    r = client.patch(f"/api/timetables/entries/{ids['e']}", json={"teacher_id": ids["ta"]}, headers=a)
    assert r.status_code == 200, r.text


def test_a_lesson_already_pointing_elsewhere_doesnt_name_it(client, two_schools):
    """Bad data from before the fix: the reply still mustn't read the name out."""
    ids, a = two_schools
    db = _db()
    try:
        db.get(TimetableEntry, ids["e"]).teacher_id = ids["tb"]
        db.commit()
    finally:
        db.close()
    r = client.patch(f"/api/timetables/entries/{ids['e']}", json={"room_id": None}, headers=a)
    assert r.status_code == 200, r.text
    assert "B-secret-teacher" not in r.text


def test_a_section_cannot_take_another_schools_subject_or_teacher(client, two_schools):
    ids, a = two_schools
    url = f"/api/class-groups/{ids['cga']}/requirements"
    base = {"class_group_id": ids["cga"], "periods_per_week": 1}
    assert client.post(url, json={**base, "subject_id": ids["secret_b"]}, headers=a).status_code == 404
    for field in ("preferred_teacher_id", "assistant_teacher_id"):
        r = client.post(url, json={**base, "subject_id": ids["maths_a"], field: ids["tb"]}, headers=a)
        assert r.status_code == 404, field
    r = client.post(url, json={**base, "subject_id": ids["maths_a"]}, headers=a)
    assert r.status_code == 201
    req_id = r.json()["id"]
    r = client.put(f"/api/class-groups/requirements/{req_id}", json={"preferred_teacher_id": ids["tb"]}, headers=a)
    assert r.status_code == 404


def test_a_teacher_cannot_take_another_schools_subjects_or_periods(client, two_schools):
    ids, a = two_schools
    body = {"school_id": ids["sa"], "name": "T"}
    assert client.post("/api/teachers", json={**body, "qualified_subject_ids": [ids["secret_b"]]},
                       headers=a).status_code == 404
    assert client.post("/api/teachers", json={**body, "unavailable_period_ids": [ids["pb"]]},
                       headers=a).status_code == 404
    assert client.put(f"/api/teachers/{ids['ta']}", json={"qualified_subject_ids": [ids["maths_a"], ids["secret_b"]]},
                      headers=a).status_code == 404
    assert client.put(f"/api/teachers/{ids['ta']}", json={"qualified_subject_ids": [ids["maths_a"]]},
                      headers=a).status_code == 200


def test_substitutions_cannot_name_another_schools_rows(client, two_schools):
    ids, a = two_schools
    url = f"/api/schools/{ids['sa']}/substitutions"
    change = {"period_id": ids["pa"], "class_group_id": ids["cga"], "absent_teacher_id": ids["ta"],
              "substituting_teacher_id": None, "subject_id": ids["maths_a"]}
    for bad in ({"substituting_teacher_id": ids["tb"]}, {"absent_teacher_id": ids["tb"]},
                {"period_id": ids["pb"]}, {"subject_id": ids["secret_b"]}):
        r = client.post(url, json={"date": "2026-10-26", "changes": [{**change, **bad}]}, headers=a)
        assert r.status_code == 404, bad
    r = client.post(url, json={"date": "2026-10-26", "absences": [{"teacher_id": ids["tb"]}], "changes": []},
                    headers=a)
    assert r.status_code == 404
    assert client.post(url, json={"date": "2026-10-26", "changes": [change]}, headers=a).status_code == 201


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("password", ["", "x", "1234567", "y" * 73, "é" * 37])
def test_new_passwords_must_be_8_to_72(client, password):
    r = client.post("/api/auth/signup", json={"email": "n@a.com", "password": password, "name": "N"})
    assert r.status_code == 422


def test_the_reason_is_readable(client):
    r = client.post("/api/auth/signup", json={"email": "n@a.com", "password": "short", "name": "N"})
    assert "Use at least 8 characters for your password." in r.text


def test_an_old_short_password_still_logs_in(client):
    from app.core.auth import hash_password
    db = _db()
    try:
        db.add(User(email="old@a.com", hashed_password=hash_password("abc"), name="Old"))
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/login", json={"email": "old@a.com", "password": "abc"}).status_code == 200


def test_accepting_an_invite_as_a_new_account_needs_a_real_password(client):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    token = client.post(f"/api/schools/{sid}/invites", json={"email": "new@a.com", "role": "viewer"},
                        headers=h).json()["token"]
    r = client.post(f"/api/invites/{token}/accept", json={"name": "N", "password": "short"})
    assert r.status_code == 422 and "8 characters" in r.text
    r = client.post(f"/api/invites/{token}/accept", json={"name": "N", "password": "long enough"})
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "new@a.com"
    db = _db()
    try:
        assert db.query(User).filter_by(email="new@a.com").one().email_verified is True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Signing in with Google over an unverified signup
# ---------------------------------------------------------------------------


def _google(client, email, sub="google-sub-1"):
    claims = {"email": email, "email_verified": True, "sub": sub, "name": "Owner"}
    with patch.object(settings, "google_client_id", "client-id"), \
            patch("app.routers.auth.google_id_token.verify_oauth2_token", return_value=claims):
        return client.post("/api/auth/google", json={"credential": "x"})


def test_google_sign_in_takes_over_an_unverified_signup(client):
    # Someone signs up with the owner's address and a password of their own.
    _, squatter = signup(client, email="owner@school.in", password="squatter-pw")
    r = _google(client, "owner@school.in")
    assert r.status_code == 200, r.text
    owner = {"Authorization": f"Bearer {r.json()['access_token']}"}
    # The squatter's session and password no longer work; the owner's does.
    assert client.get("/api/auth/me", headers=squatter).status_code == 401
    assert client.post("/api/auth/login", json={"email": "owner@school.in", "password": "squatter-pw"}).status_code == 401
    assert client.get("/api/auth/me", headers=owner).status_code == 200


def test_google_sign_in_keeps_a_verified_accounts_password(client):
    signup(client, email="me@school.in", password="my-own-pw")
    verify_email("me@school.in")
    assert _google(client, "me@school.in").status_code == 200
    assert client.post("/api/auth/login", json={"email": "me@school.in", "password": "my-own-pw"}).status_code == 200


def test_a_google_account_is_verified(client):
    _google(client, "fresh@school.in")
    db = _db()
    try:
        assert db.query(User).filter_by(email="fresh@school.in").one().email_verified is True
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Sessions and reset links
# ---------------------------------------------------------------------------


def _reset(client, email, monkeypatch):
    sent = {}
    monkeypatch.setattr("app.routers.auth.send_password_reset_email",
                        lambda to_email, reset_token: sent.__setitem__("token", reset_token))
    client.post("/api/auth/forgot-password", json={"email": email})
    return sent["token"]


def test_resetting_the_password_signs_out_every_other_session(client, monkeypatch):
    _, old = signup(client, email="r@a.com")
    token = _reset(client, "r@a.com", monkeypatch)
    r = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pw"})
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new).status_code == 200


def test_reset_links_are_stored_hashed_and_using_one_cancels_the_rest(client, monkeypatch):
    signup(client, email="r@a.com")
    first = _reset(client, "r@a.com", monkeypatch)
    second = _reset(client, "r@a.com", monkeypatch)
    db = _db()
    try:
        stored = {t.token for t in db.query(PasswordResetToken)}
    finally:
        db.close()
    assert first not in stored and second not in stored
    assert client.post("/api/auth/reset-password", json={"token": second, "new_password": "brand-new-pw"}).status_code == 200
    r = client.post("/api/auth/reset-password", json={"token": first, "new_password": "another-pw"})
    assert r.status_code == 400


def test_tokens_from_before_versions_still_work(client):
    """Sessions issued before this change carry no version: not logged out."""
    import jwt
    from datetime import datetime, timedelta, timezone
    user, _ = signup(client, email="legacy@a.com")
    legacy = jwt.encode({"sub": str(user["id"]), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                        settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 200


def test_the_admin_page_needs_a_verified_email(client, monkeypatch):
    monkeypatch.setattr(settings, "platform_admin_emails", "staff@timetablz.com")
    _, h = signup(client, email="staff@timetablz.com")
    assert client.get("/api/auth/me", headers=h).json()["is_platform_admin"] is False
    assert client.get("/api/admin/schools", headers=h).status_code == 404
    verify_email("staff@timetablz.com")
    assert client.get("/api/auth/me", headers=h).json()["is_platform_admin"] is True


# ---------------------------------------------------------------------------
# Invite emails
# ---------------------------------------------------------------------------


def test_invite_emails_escape_what_the_inviter_typed(client):
    _, h = signup(client, name='Evil <img src=x onerror=alert(1)>')
    sid = create_school(client, h, name='<a href="https://evil.example">Verify your account</a>')["id"]
    with patch.object(settings, "resend_api_key", "key"), \
            patch("app.services.email_service.requests.post") as post:
        post.return_value.status_code = 200
        client.post(f"/api/schools/{sid}/invites", json={"email": "victim@a.com", "role": "viewer"}, headers=h)
    body = post.call_args.kwargs["json"]
    assert '<a href="https://evil.example">' not in body["html"]
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in body["html"]
    assert "<img" not in body["html"]
    assert "\n" not in body["subject"] and body["subject"].endswith("on Timetablz")


def test_invites_are_rate_limited(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    reset_quotas()
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    codes = [client.post(f"/api/schools/{sid}/invites", json={"email": f"p{i}@a.com", "role": "viewer"},
                         headers=h).status_code for i in range(21)]
    reset_quotas()
    assert codes[-1] == 429
    assert all(c in (201, 402) for c in codes[:-1])


# ---------------------------------------------------------------------------
# Generation: one at a time per school
# ---------------------------------------------------------------------------


def test_one_generation_at_a_time_per_school(client, monkeypatch):
    started = []
    monkeypatch.setattr("app.routers.timetables.threading.Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: started.append(args)})())
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    assert client.post(f"/api/timetables/generate?school_id={sid}", headers=h).status_code == 201
    r = client.post(f"/api/timetables/generate?school_id={sid}", headers=h)
    assert r.status_code == 409 and "already being generated" in r.text
    assert len(started) == 1


def test_a_run_that_died_doesnt_lock_the_school_out(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr("app.routers.timetables.threading.Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: None})())
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = _db()
    try:
        db.add(Timetable(school_id=sid, status="generating",
                         created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)))
        db.commit()
    finally:
        db.close()
    assert client.post(f"/api/timetables/generate?school_id={sid}", headers=h).status_code == 201


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def _upload(client, h, sid, name, content):
    return client.post("/api/teachers/bulk-import", headers=h, data={"school_id": str(sid)},
                       files={"file": (name, content, "application/octet-stream")})


@pytest.fixture
def school(client):
    _, h = signup(client)
    return create_school(client, h)["id"], h


def test_uploads_over_5mb_are_refused(client, school):
    sid, h = school
    r = _upload(client, h, sid, "t.csv", b"name\n" + b"x" * (5 * 1024 * 1024))
    assert r.status_code == 413


def test_an_xlsx_that_unpacks_huge_is_refused(client, school):
    sid, h = school
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml", b"a" * (60 * 1024 * 1024))
    assert len(buf.getvalue()) < 1024 * 1024  # small on the wire
    r = _upload(client, h, sid, "t.xlsx", buf.getvalue())
    assert r.status_code == 400 and "too big" in r.text


def test_a_fake_xlsx_is_refused(client, school):
    sid, h = school
    r = _upload(client, h, sid, "t.xlsx", b"not a zip")
    assert r.status_code == 400 and "valid .xlsx" in r.text


def test_too_many_rows_are_refused(client, school):
    sid, h = school
    content = "name\n" + "".join(f"Teacher {i}\n" for i in range(5001))
    r = _upload(client, h, sid, "t.csv", content.encode())
    assert r.status_code == 400 and "more than 5000 rows" in r.text


# ---------------------------------------------------------------------------
# Exports, docs, headers, limits
# ---------------------------------------------------------------------------


def test_exports_never_contain_live_formulas(client, school):
    sid, h = school
    db = _db()
    try:
        subj = Subject(school_id=sid, name='=HYPERLINK("https://evil.example","Click")')
        db.add(subj)
        db.commit()
        t = Teacher(school_id=sid, name="=1+1")
        cg = ClassGroup(school_id=sid, grade="Grade 1", name="A")
        p = Period(school_id=sid, day_of_week=0, order=0)
        db.add_all([t, cg, p])
        db.commit()
        tt = Timetable(school_id=sid, status="draft")
        db.add(tt)
        db.commit()
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=cg.id, subject_id=subj.id, teacher_id=t.id,
                              period_id=p.id))
        db.commit()
        tt_id = tt.id
    finally:
        db.close()
    r = client.get(f"/api/timetables/{tt_id}/export?format=xlsx", headers=h)
    assert r.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    cells = [c for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None]
    assert cells and all(c.data_type != "f" for c in cells)


def test_debug_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("DEBUG", raising=False)
    assert Settings(_env_file=None).debug is False


def test_api_docs_only_in_debug_mode():
    from app.main import app
    expected = "/docs" if settings.debug else None
    assert app.docs_url == expected
    assert app.openapi_url == ("/openapi.json" if settings.debug else None)


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_the_solver_check_needs_a_login(client):
    assert client.get("/api/solver/test").status_code == 401


def test_text_fields_have_limits(client):
    _, h = signup(client)
    assert client.post("/api/schools", json={"name": "S" * 121}, headers=h).status_code == 422
    sid = create_school(client, h)["id"]
    assert client.put(f"/api/schools/{sid}/name", json={"name": "S" * 121}, headers=h).status_code == 422
    assert client.put(f"/api/schools/{sid}/name", json={"name": "Sunrise"}, headers=h).status_code == 200
    r = client.post("/api/auth/signup", json={"email": "x@a.com", "password": "password123", "name": "N" * 101})
    assert r.status_code == 422

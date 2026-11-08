"""
The admin page: a school's data, and deleting schools and accounts for good
- everything belonging to them goes, invoices and terms acceptances stay.
"""
import pytest

from app.core.database import SessionLocal
from app.models.payment import Invoice
from app.models.problems import ProblemEvent
from app.models.school import (
    ClassGroup, School, SchoolMembership, Subject, SubjectRequirement, Teacher, Timetable, TimetableEntry,
)
from app.models.user import TermsAcceptance, User
from app.services import billing
from tests.conftest import create_school, signup


@pytest.fixture
def admin(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "platform_admin_emails", "boss@timetablz.com")
    _, h = signup(client, email="boss@timetablz.com")
    db = SessionLocal()
    try:
        db.query(User).filter_by(email="boss@timetablz.com").update({"email_verified": True})
        db.commit()
    finally:
        db.close()
    return h


def _full_school(client, email="owner@school.in", name="Riverside"):
    from app.core.terms import CURRENT_TERMS_VERSION

    _, h = signup(client, email=email)
    client.post("/api/auth/accept-terms", json={"version": CURRENT_TERMS_VERSION}, headers=h)
    sid = create_school(client, h, name=name)["id"]
    cg = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 6", "name": "A"}, headers=h).json()
    subj = client.post("/api/subjects", json={"school_id": sid, "name": "Maths"}, headers=h).json()
    t = client.post("/api/teachers", json={"school_id": sid, "name": "Anil", "email": "anil@school.in",
                                           "qualified_subject_ids": [subj["id"]]}, headers=h).json()
    db = SessionLocal()
    try:
        db.query(ClassGroup).filter_by(id=cg["id"]).update({"class_teacher_id": t["id"]})
        db.add(SubjectRequirement(class_group_id=cg["id"], subject_id=subj["id"], periods_per_week=5,
                                  preferred_teacher_id=t["id"]))
        school = db.get(School, sid)
        tt = Timetable(school_id=sid)
        db.add(tt)
        db.commit()
        billing.issue_invoice(db, school, description="Pro, 365 days", amount_paise=499900, method="bank_transfer",
                              reference="UTR1")
        db.add(ProblemEvent(school_id=sid, kind="generation_failed", summary="x", snapshot={"a": 1}))
        db.commit()
    finally:
        db.close()
    return sid, h


def test_the_admin_sees_a_schools_data(client, admin):
    sid, _ = _full_school(client)
    d = client.get(f"/api/admin/schools/{sid}/data", headers=admin).json()
    assert d["counts"]["sections"] == 1 and d["counts"]["teachers"] == 1 and d["counts"]["timetables"] == 1
    assert d["teachers"][0]["email"] == "anil@school.in"
    assert d["people"][0] == {"email": "owner@school.in", "name": "A", "role": "owner"}
    assert d["invoices"][0]["amount"] == 4999


def test_deleting_a_school_removes_its_data_but_keeps_invoices(client, admin):
    sid, _ = _full_school(client)
    r = client.request("DELETE", f"/api/admin/schools/{sid}", json={"confirm": "wrong"}, headers=admin)
    assert r.status_code == 400
    name = client.get(f"/api/admin/schools/{sid}/data", headers=admin).json()["school"]["name"]
    r = client.request("DELETE", f"/api/admin/schools/{sid}", json={"confirm": name.upper()}, headers=admin)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.get(School, sid) is None
        for model in (ClassGroup, Subject, Teacher, Timetable, ProblemEvent):
            assert db.query(model).filter_by(school_id=sid).count() == 0, model
        assert db.query(SubjectRequirement).count() == 0 and db.query(TimetableEntry).count() == 0
        assert db.query(SchoolMembership).filter_by(school_id=sid).count() == 0
        (inv,) = db.query(Invoice).all()
        assert inv.school_id is None and inv.billed_to["name"] == name
        # The owner's account stays.
        assert db.query(User).filter_by(email="owner@school.in").count() == 1
    finally:
        db.close()
    invoices = client.get("/api/admin/invoices", headers=admin).json()
    assert invoices[0]["school_name"] == f"{name} (deleted)"


def test_deleting_an_account_that_owns_schools_needs_a_tick(client, admin):
    sid, _ = _full_school(client)
    owner = next(a for a in client.get("/api/admin/accounts", headers=admin).json() if a["email"] == "owner@school.in")
    detail = client.get(f"/api/admin/accounts/{owner['id']}", headers=admin).json()
    assert detail["owns"][0]["id"] == sid and detail["terms"][0]["version"]

    r = client.request("DELETE", f"/api/admin/accounts/{owner['id']}", json={"confirm": "owner@school.in"}, headers=admin)
    assert r.status_code == 409 and "owns" in r.json()["detail"]
    r = client.request("DELETE", f"/api/admin/accounts/{owner['id']}",
                       json={"confirm": "owner@school.in", "delete_schools": True}, headers=admin)
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        assert db.query(User).filter_by(email="owner@school.in").count() == 0
        assert db.get(School, sid) is None
        (t,) = db.query(TermsAcceptance).all()  # the proof of what they agreed to stays
        assert t.user_id is None and t.email == "owner@school.in"
        assert db.query(Invoice).count() == 1
    finally:
        db.close()


def test_deleting_a_member_leaves_the_school(client, admin):
    sid, owner_h = _full_school(client)
    _, mh = signup(client, email="teacher@school.in")
    db = SessionLocal()
    try:
        member = db.query(User).filter_by(email="teacher@school.in").one()
        db.add(SchoolMembership(school_id=sid, user_id=member.id, role="viewer"))
        db.commit()
        mid = member.id
    finally:
        db.close()
    r = client.request("DELETE", f"/api/admin/accounts/{mid}", json={"confirm": "teacher@school.in"}, headers=admin)
    assert r.status_code == 200 and r.json()["schools"] == []
    db = SessionLocal()
    try:
        assert db.get(School, sid) is not None
        assert db.query(SchoolMembership).filter_by(user_id=mid).count() == 0
    finally:
        db.close()


def test_guard_rails(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    r = client.request("DELETE", f"/api/admin/accounts/{me['id']}", json={"confirm": me["email"]}, headers=admin)
    assert r.status_code == 400
    _, h = signup(client, email="nobody@x.com")
    assert client.get("/api/admin/schools/1/data", headers=h).status_code == 404
    assert client.request("DELETE", "/api/admin/accounts/1", json={"confirm": "x"}, headers=h).status_code == 404

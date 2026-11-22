"""
Settings > Clear all data: a school starts over. Everything it set up goes;
the school, its members, plan and invoices stay; another school is untouched.
"""
from app.core.database import SessionLocal
from app.models.payment import Invoice
from app.models.school import (
    ClassGroup, Constraint, Period, School, SchoolAlias, Subject, Teacher, Timetable,
)
from tests.conftest import create_school, signup


def _fill(client, h, sid):
    client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 9", "name": "A"}, headers=h)
    client.post("/api/teachers", json={"school_id": sid, "name": "Priya"}, headers=h)
    client.post("/api/subjects", json={"school_id": sid, "name": "Maths"}, headers=h)
    db = SessionLocal()
    try:
        db.add(Period(school_id=sid, day_of_week=0, order=0, label="P1"))
        db.add(Constraint(school_id=sid, type="custom", description="rule"))
        db.add(Timetable(school_id=sid, status="draft", solver_status="manual", version_number=1))
        db.add(SchoolAlias(school_id=sid, kind="subject", key="mat", text="MAT", meaning="Maths"))
        db.add(Invoice(number=f"INV-{sid}", description="Plan", amount_paise=100, method="card", school_id=sid))
        s = db.get(School, sid)
        s.fixed_periods = [{"subject_id": 1, "grades": ["Grade 9"], "period": 8, "days": None}]
        db.commit()
    finally:
        db.close()


def _count(model, sid):
    db = SessionLocal()
    try:
        return db.query(model).filter_by(school_id=sid).count()
    finally:
        db.close()


def test_clearing_a_school_keeps_the_school_members_and_invoices(client):
    _, h = signup(client)
    sid = create_school(client, h, name="Keren Public School")["id"]
    _, h2 = signup(client, email="b@b.com")
    other = create_school(client, h2, name="Other School")["id"]
    _fill(client, h, sid)
    _fill(client, h2, other)

    r = client.post(f"/api/schools/{sid}/clear-data", json={"confirm": "keren public school"}, headers=h)
    assert r.status_code == 200, r.text
    for model in (ClassGroup, Teacher, Subject, Period, Constraint, Timetable, SchoolAlias):
        assert _count(model, sid) == 0, model.__name__
        assert _count(model, other) > 0, model.__name__   # the other school untouched
    assert _count(Invoice, sid) == 1
    assert client.get(f"/api/schools/{sid}", headers=h).status_code == 200   # still theirs
    db = SessionLocal()
    try:
        s = db.get(School, sid)
        assert s.name == "Keren Public School" and s.fixed_periods is None
    finally:
        db.close()


def test_the_name_must_be_typed_and_only_an_admin_can_clear(client):
    _, h = signup(client)
    sid = create_school(client, h, name="Keren Public School")["id"]
    _fill(client, h, sid)
    assert client.post(f"/api/schools/{sid}/clear-data", json={"confirm": "Keren"}, headers=h).status_code == 400
    _, h2 = signup(client, email="c@c.com")
    assert client.post(f"/api/schools/{sid}/clear-data", json={"confirm": "Keren Public School"},
                       headers=h2).status_code == 404
    assert _count(Teacher, sid) == 1

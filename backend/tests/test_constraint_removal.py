"""
Removing (or rewording) a workload or availability constraint must undo what
it wrote onto the Teacher row.

Those two types are enforced through Teacher.max_periods_per_week and
Teacher.unavailable_period_ids - the Constraint row is only the record the UI
shows. Before this was fixed, deleting the card left the teacher blocked or
capped, and every later generation kept honouring a rule that no longer
existed.
"""
from app.core.database import SessionLocal
from app.models.school import Constraint, Period, Teacher
from app.routers.constraints import _apply_parsed_constraint, _load_resolution_data
from app.services.llm_constraint_parser import ParsedConstraint
from tests.conftest import create_school, signup
from tests.test_period_availability import _school_with_a_week


def _add(school_id, parsed):
    """Resolve a parsed rule and store it the way the parse endpoint does."""
    db = SessionLocal()
    try:
        data = _load_resolution_data(db, school_id)
        resolved = _apply_parsed_constraint(db, school_id, parsed, data)
        row = Constraint(school_id=school_id, type=resolved.db_type, parameters=resolved.parameters,
                         description=parsed.description, is_hard=True)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _teacher(school_id):
    db = SessionLocal()
    try:
        t = db.query(Teacher).filter(Teacher.school_id == school_id).one()
        blocked = db.query(Period).filter(Period.id.in_(t.unavailable_period_ids or [-1])).all()
        return t.max_periods_per_week, {(p.day_of_week, p.order) for p in blocked}
    finally:
        db.close()


def test_deleting_an_availability_rule_frees_the_teacher(client):
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    cid = _add(school["id"], ParsedConstraint(type="availability", description="Mr. Khan is away on Tuesdays",
                                              teacher_name="Mr. Khan", day_of_week=1))
    assert len(_teacher(school["id"])[1]) == 8

    r = client.delete(f"/api/constraints/{cid}", headers=headers)
    assert r.status_code == 204
    assert _teacher(school["id"])[1] == set()


def test_overlapping_rule_keeps_its_periods_blocked(client):
    """Tuesday off and "no first period, any day" share Tuesday P1. Deleting
    the Tuesday rule must keep P1 blocked on every day, Tuesday included."""
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    tuesday = _add(school["id"], ParsedConstraint(type="availability", description="Away Tuesdays",
                                                  teacher_name="Mr. Khan", day_of_week=1))
    _add(school["id"], ParsedConstraint(type="availability", description="No first period",
                                        teacher_name="Mr. Khan", period_orders=[1]))

    client.delete(f"/api/constraints/{tuesday}", headers=headers)
    assert _teacher(school["id"])[1] == {(d, 1) for d in range(5)}


def test_deleting_a_workload_cap_removes_the_cap(client):
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    cid = _add(school["id"], ParsedConstraint(type="workload_limit", description="Max 3 a week for Mr. Khan",
                                              teacher_name="Mr. Khan", max_periods_per_week=3))
    assert _teacher(school["id"])[0] == 3

    client.delete(f"/api/constraints/{cid}", headers=headers)
    assert _teacher(school["id"])[0] is None


def test_deleting_one_of_two_caps_falls_back_to_the_other(client):
    _, headers = signup(client)
    school = _school_with_a_week(client, headers)
    _add(school["id"], ParsedConstraint(type="workload_limit", description="Max 10",
                                        teacher_name="Mr. Khan", max_periods_per_week=10))
    newer = _add(school["id"], ParsedConstraint(type="workload_limit", description="Max 3",
                                                teacher_name="Mr. Khan", max_periods_per_week=3))

    client.delete(f"/api/constraints/{newer}", headers=headers)
    assert _teacher(school["id"])[0] == 10

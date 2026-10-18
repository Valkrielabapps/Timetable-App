"""A rule saved after a timetable was generated isn't "broken" by it.

The timetable simply predates the rule, so it is reported as pending
("generate again") rather than as a violation."""
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Constraint, Period, Subject, Teacher, Timetable, TimetableEntry
from tests.conftest import create_school, signup

NO_PE_P1 = {"form": "count", "scope": [], "selector": {"subjects": ["PE"], "period_orders": [1]},
            "relation": "==", "value": 0}


def _setup(client, rule_offset):
    _, h = signup(client)
    sid = create_school(client, h)["id"]
    db = SessionLocal()
    try:
        p = Period(school_id=sid, day_of_week=0, order=0, kind="lesson")
        pe = Subject(school_id=sid, name="PE")
        cg = ClassGroup(school_id=sid, grade="Grade 8", name="A")
        t = Teacher(school_id=sid, name="Coach", qualified_subject_ids=[])
        db.add_all([p, pe, cg, t])
        db.commit()
        made = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
        tt = Timetable(school_id=sid, status="draft", solver_status="optimal", created_at=made)
        db.add(tt)
        db.commit()
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=cg.id, subject_id=pe.id, teacher_id=t.id, period_id=p.id))
        rule = Constraint(school_id=sid, type="ir", parameters=NO_PE_P1, description="No PE in period 1",
                          created_at=made + rule_offset)
        db.add(rule)
        db.commit()
        return h, tt.id, rule.id
    finally:
        db.close()


def test_a_rule_added_after_the_timetable_is_pending_not_broken(client):
    h, tt, rule = _setup(client, timedelta(hours=1))
    body = client.get(f"/api/timetables/{tt}", headers=h).json()
    assert body["violations"] == []
    assert body["pending_constraint_ids"] == [rule]


def test_a_rule_that_was_there_when_it_was_generated_is_still_checked(client):
    h, tt, rule = _setup(client, -timedelta(hours=1))
    body = client.get(f"/api/timetables/{tt}", headers=h).json()
    assert [v["constraint_id"] for v in body["violations"]] == [rule]
    assert body["pending_constraint_ids"] == []

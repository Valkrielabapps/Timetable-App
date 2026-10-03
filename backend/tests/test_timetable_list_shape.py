"""
Listing timetables must not carry their entries.

GET /api/timetables used to return the full timetable - entries, resolved
names and all - for every timetable a school had ever generated. Every caller
then read one or two fields from it: the highest id, or the first row marked
draft. On a 28-section school with ten generations that is a 4 MB response and
71 queries to produce an integer, and it grew with every generation, so the
longer a school used the app the slower the Timetable tab became.

That is the shape of problem that looks like it needs caching and does not:
fetching four megabytes quickly is still fetching four megabytes.

These tests pin the shape rather than the speed, because a timing assertion
would be flaky and the shape is what actually went wrong - the moment `entries`
is back in this response, the cost is back with it whatever the clock says.
"""
import pytest

from tests.conftest import create_school, signup


@pytest.fixture
def school_with_timetables(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    from app.core.database import SessionLocal
    from app.models.school import (ClassGroup, Period, Subject, Teacher, Timetable,
                                   TimetableEntry)
    db = SessionLocal()
    try:
        period = Period(school_id=school["id"], day_of_week=0, order=0)
        subject = Subject(school_id=school["id"], name="Maths")
        teacher = Teacher(school_id=school["id"], name="Mrs. Rao", qualified_subject_ids=[])
        cg = ClassGroup(school_id=school["id"], grade="Grade 8", name="A")
        db.add_all([period, subject, teacher, cg])
        db.commit()
        for _ in range(3):
            tt = Timetable(school_id=school["id"], status="draft", solver_status="optimal")
            db.add(tt)
            db.commit()
            db.refresh(tt)
            db.add(TimetableEntry(timetable_id=tt.id, class_group_id=cg.id,
                                  subject_id=subject.id, teacher_id=teacher.id,
                                  period_id=period.id))
            db.commit()
    finally:
        db.close()
    return school, headers


def test_the_list_does_not_include_entries(client, school_with_timetables):
    """The whole point. Callers that need entries fetch one timetable by id."""
    school, headers = school_with_timetables
    rows = client.get(f"/api/timetables?school_id={school['id']}", headers=headers).json()
    assert len(rows) == 3
    for row in rows:
        assert "entries" not in row, "listing timetables must not carry their entries"


def test_the_list_does_not_run_the_violation_check(client, school_with_timetables):
    """Checking rules is cheap for one timetable and wasteful for every
    timetable ever generated - and nothing in the list view shows them."""
    school, headers = school_with_timetables
    rows = client.get(f"/api/timetables?school_id={school['id']}", headers=headers).json()
    for row in rows:
        assert "violations" not in row


def test_the_list_still_carries_what_callers_actually_use(client, school_with_timetables):
    """Every consumer reads the id to find the newest, or the status to find
    the draft. Trimming past those would just move the problem."""
    school, headers = school_with_timetables
    rows = client.get(f"/api/timetables?school_id={school['id']}", headers=headers).json()
    for row in rows:
        assert isinstance(row["id"], int)
        assert row["status"] == "draft"
        assert row["school_id"] == school["id"]
        # Kept because a failed generation is listed too, and the reason is
        # worth having without a second request.
        assert "error_message" in row
        assert "solver_status" in row


def test_fetching_one_timetable_still_returns_everything(client, school_with_timetables):
    """The trimming is on the list only. Asking for a specific timetable is how
    entries and violations are meant to be reached, and that has to keep
    working or the list change just breaks the tab differently."""
    school, headers = school_with_timetables
    rows = client.get(f"/api/timetables?school_id={school['id']}", headers=headers).json()
    newest = max(rows, key=lambda r: r["id"])

    full = client.get(f"/api/timetables/{newest['id']}", headers=headers).json()
    assert len(full["entries"]) == 1
    assert full["entries"][0]["subject_name"] == "Maths"
    assert full["entries"][0]["teacher_name"] == "Mrs. Rao"
    assert full["violations"] == []


def test_the_list_costs_the_same_however_many_entries_exist(client, school_with_timetables):
    """The failure was that cost grew with every generation. Counting queries
    rather than timing: one SELECT, regardless.

    A per-timetable query here is the N+1 coming back, and it would show up as
    a tab that gets slower the longer a school uses the app - which is exactly
    how this went unnoticed in the first place.
    """
    from sqlalchemy import event

    from app.core.database import engine

    school, headers = school_with_timetables
    statements = []
    listener = lambda conn, cur, stmt, *a: statements.append(stmt)  # noqa: E731
    event.listen(engine, "before_cursor_execute", listener)
    try:
        client.get(f"/api/timetables?school_id={school['id']}", headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", listener)

    selects = [s for s in statements if "timetable_entries" in s.lower()]
    assert selects == [], f"the list touched entries {len(selects)} time(s)"

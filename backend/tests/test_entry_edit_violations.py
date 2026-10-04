"""
Every edit returns the rules the timetable now breaks, alongside the rows.

The frontend patches the returned rows into its cached timetable rather than
re-reading the whole thing - re-reading a school-wide timetable to reflect one
drag is what made dragging slow. So anything the edit changes that the UI shows
has to come back with it, and the violation band is exactly that: without the
violations riding along it goes stale the moment a slot moves, which is
precisely when it has something to say.

Recomputed over the whole timetable rather than the moved slot, because a rule
is about a group of lessons - moving one can fix a violation elsewhere as
easily as cause one here.
"""
import pytest

from tests.conftest import create_school, signup


@pytest.fixture
def school(client):
    """A class with two Maths periods and a rule barring the first period."""
    _, headers = signup(client)
    school = create_school(client, headers)
    from app.core.database import SessionLocal
    from app.models.school import (ClassGroup, Constraint, Period, Subject, Teacher,
                                   Timetable, TimetableEntry)
    db = SessionLocal()
    try:
        periods = [Period(school_id=school["id"], day_of_week=0, order=o) for o in range(4)]
        subject = Subject(school_id=school["id"], name="Maths")
        teacher = Teacher(school_id=school["id"], name="Mrs. Rao", qualified_subject_ids=[])
        cg = ClassGroup(school_id=school["id"], grade="Grade 8", name="A")
        db.add_all([*periods, subject, teacher, cg])
        db.add(Constraint(
            school_id=school["id"], type="ir",
            parameters={"form": "count", "scope": ["class_group"],
                        "selector": {"subjects": ["Maths"], "period_orders": [1]},
                        "relation": "==", "value": 0, "strength": "required"},
            description="No class has Maths periods in period 1.",
        ))
        db.commit()
        timetable = Timetable(school_id=school["id"], status="draft", solver_status="optimal")
        db.add(timetable)
        db.commit()
        db.refresh(timetable)
        # Both safely in later periods to begin with.
        entries = [
            TimetableEntry(timetable_id=timetable.id, class_group_id=cg.id,
                           subject_id=subject.id, teacher_id=teacher.id,
                           period_id=periods[2].id),
            TimetableEntry(timetable_id=timetable.id, class_group_id=cg.id,
                           subject_id=subject.id, teacher_id=teacher.id,
                           period_id=periods[3].id),
        ]
        db.add_all(entries)
        db.commit()
        ids = {"entries": [e.id for e in entries],
               "periods": [p.id for p in periods],
               "timetable": timetable.id}
    finally:
        db.close()
    return school, headers, ids


def test_an_edit_returns_the_rows_it_changed(client, school):
    _, headers, ids = school
    r = client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                     json={"period_id": ids["periods"][1]}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [e["id"] for e in body["entries"]] == [ids["entries"][0]]


def test_moving_into_a_barred_period_reports_it_on_the_same_response(client, school):
    """The drag is already finished on screen by the time this answers, so the
    band has to be told here or not at all until the next full read."""
    _, headers, ids = school
    r = client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                     json={"period_id": ids["periods"][0]}, headers=headers)
    body = r.json()
    assert len(body["violations"]) == 1
    assert body["violations"][0]["description"] == "No class has Maths periods in period 1."
    assert body["violations"][0]["entry_ids"] == [ids["entries"][0]]


def test_moving_back_out_clears_it_on_the_same_response(client, school):
    """A band that only ever appears is a band people learn to ignore."""
    _, headers, ids = school
    client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                 json={"period_id": ids["periods"][0]}, headers=headers)
    r = client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                     json={"period_id": ids["periods"][1]}, headers=headers)
    assert r.json()["violations"] == []


def test_the_check_covers_the_whole_timetable_not_just_the_moved_slot(client, school):
    """A rule is about a group of lessons. Moving the second entry into the
    barred period has to surface even though the first one is what was moved
    last - and a check scoped to the edited row would miss it."""
    _, headers, ids = school
    client.patch(f"/api/timetables/entries/{ids['entries'][1]}",
                 json={"period_id": ids["periods"][0]}, headers=headers)
    # Now move the OTHER entry somewhere harmless; the first violation stands.
    r = client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                     json={"period_id": ids["periods"][2]}, headers=headers)
    assert [v["entry_ids"] for v in r.json()["violations"]] == [[ids["entries"][1]]]


def test_a_swap_returns_both_rows_and_the_violations(client, school):
    _, headers, ids = school
    # Put one in the barred period so the swap moves a violation about.
    client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                 json={"period_id": ids["periods"][0]}, headers=headers)
    r = client.post(
        f"/api/timetables/entries/{ids['entries'][0]}/swap-with/{ids['entries'][1]}",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["entries"]) == 2
    # The violation followed the slot, not the row.
    assert body["violations"][0]["entry_ids"] == [ids["entries"][1]]


def test_a_lock_toggle_does_not_pretend_the_timetable_changed(client, school):
    """Locking moves nothing, so the violations it reports are just the
    standing ones - but it still has to report them, or the band would blank
    whenever someone toggled a lock."""
    _, headers, ids = school
    client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                 json={"period_id": ids["periods"][0]}, headers=headers)
    r = client.patch(f"/api/timetables/entries/{ids['entries'][1]}",
                     json={"locked": True}, headers=headers)
    assert len(r.json()["violations"]) == 1


def test_a_rejected_move_changes_nothing(client, school):
    """The frontend moves the cell before asking and rolls back on a refusal,
    so a rejection must leave the timetable exactly as it was."""
    _, headers, ids = school
    # Both entries are the same class group, so the second period is taken.
    r = client.patch(f"/api/timetables/entries/{ids['entries'][0]}",
                     json={"period_id": ids["periods"][3]}, headers=headers)
    assert r.status_code == 400

    full = client.get(f"/api/timetables/{ids['timetable']}", headers=headers).json()
    by_id = {e["id"]: e for e in full["entries"]}
    assert by_id[ids["entries"][0]]["period_id"] == ids["periods"][2]
    assert full["violations"] == []

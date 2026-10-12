"""
The structure, class teachers and the special periods, through the API.
"""
import io

import openpyxl
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Period, Subject, Teacher, Timetable, TimetableEntry, ZeroPeriod
from app.services.llm_constraint_parser import _period_summary
from tests.conftest import create_school, signup

DAY = {"days": [0], "periods_per_day": 3}


@pytest.fixture
def world(client):
    _, headers = signup(client)
    school = create_school(client, headers)
    sid = school["id"]
    six = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 6", "name": "A"}, headers=headers).json()
    seven = client.post("/api/class-groups", json={"school_id": sid, "grade": "Grade 7", "name": "A"}, headers=headers).json()
    db = SessionLocal()
    try:
        rao = Teacher(school_id=sid, name="Mrs. Rao", qualified_subject_ids=[])
        maths = Subject(school_id=sid, name="Maths")
        db.add_all([rao, maths])
        db.commit()
        ids = {"school": sid, "six": six["id"], "seven": seven["id"], "rao": rao.id, "maths": maths.id}
    finally:
        db.close()
    return ids, headers


def put(client, w, h, **structure):
    return client.put(f"/api/schools/{w['school']}/timetable-structure", json=structure, headers=h)


def periods(client, w, h):
    return client.get(f"/api/periods?school_id={w['school']}", headers=h).json()


# ---------------------------------------------------------------------------
# Structure endpoints
# ---------------------------------------------------------------------------


def test_saving_a_structure_makes_the_periods(client, world):
    w, h = world
    r = put(client, w, h, **DAY, breaks=[{"after": 2, "label": "Lunch"}], class_teacher_period={"enabled": True})
    assert r.status_code == 200, r.text
    assert r.json()["structure"]["breaks"] == [{"after": 2, "label": "Lunch"}]
    shown = [(p["kind"], p["number"], p["label"]) for p in periods(client, w, h)]
    assert shown == [("class_teacher", None, None), ("lesson", 1, None), ("lesson", 2, None),
                     ("break", None, "Lunch"), ("lesson", 3, None)]


def test_reading_it_back(client, world):
    w, h = world
    put(client, w, h, **DAY, class_teacher_period={"enabled": True, "after": 1})
    r = client.get(f"/api/schools/{w['school']}/timetable-structure", headers=h).json()
    assert r["irregular"] is False
    assert r["structure"]["class_teacher_period"] == {"enabled": True, "after": 1}


def test_a_school_with_no_periods_reads_back_as_none(client, world):
    w, h = world
    assert client.get(f"/api/schools/{w['school']}/timetable-structure", headers=h).json() == {
        "structure": None, "irregular": False,
    }


def test_an_impossible_structure_is_refused_with_its_reason(client, world):
    w, h = world
    r = put(client, w, h, **DAY, breaks=[{"after": 3}])
    assert r.status_code == 400
    assert "after a period between 1 and 2" in r.json()["detail"]
    assert periods(client, w, h) == []


def test_the_report_comes_back(client, world):
    w, h = world
    r = put(client, w, h, **DAY, class_teacher_period={"enabled": True})
    report = r.json()["report"]
    assert report["changed"] is True
    assert report["sections_without_class_teacher"] == ["Grade 6 - A", "Grade 7 - A"]


def test_a_viewer_cannot_change_the_structure(client, world):
    w, h = world
    _, other = signup(client, email="viewer@x.com")
    assert put(client, w, other, **DAY).status_code in (403, 404)


def test_a_periods_zero_grades_are_shown(client, world):
    w, h = world
    put(client, w, h, **DAY, zero_period={"enabled": True, "scope": "grade",
                                          "placements": [{"grade": "Grade 6", "every_day": 2}]})
    second = next(p for p in periods(client, w, h) if p["number"] == 2)
    assert second["zero_grades"] == ["Grade 6"] and second["zero_all"] is False


# ---------------------------------------------------------------------------
# Old-style period endpoints still work
# ---------------------------------------------------------------------------


def test_a_period_can_still_be_made_a_break_the_old_way(client, world):
    w, h = world
    r = client.post("/api/periods", json={"school_id": w["school"], "day_of_week": 0, "order": 0,
                                          "is_break": True}, headers=h)
    assert r.status_code == 201
    assert r.json()["kind"] == "break" and r.json()["is_break"] is True and r.json()["number"] is None


def test_a_period_kind_can_be_set_directly(client, world):
    w, h = world
    pid = client.post("/api/periods", json={"school_id": w["school"], "day_of_week": 0, "order": 0},
                      headers=h).json()["id"]
    r = client.put(f"/api/periods/{pid}", json={"kind": "class_teacher"}, headers=h)
    assert r.json()["kind"] == "class_teacher" and r.json()["is_break"] is True


# ---------------------------------------------------------------------------
# Manual edits
# ---------------------------------------------------------------------------


def _timetable(w, slot_number=1, section="six"):
    db = SessionLocal()
    try:
        all_periods = db.query(Period).filter(Period.school_id == w["school"]).all()
        from app.services.timetable_structure import lesson_numbers
        numbers = lesson_numbers(all_periods)
        by_number = {numbers[p.id]: p.id for p in all_periods if p.id in numbers}
        tt = Timetable(school_id=w["school"], status="draft")
        db.add(tt)
        db.commit()
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=w[section], subject_id=w["maths"],
                              teacher_id=w["rao"], period_id=by_number[slot_number]))
        db.commit()
        other = {p.kind: p.id for p in all_periods if p.kind != "lesson"}
        return tt.id, by_number, other
    finally:
        db.close()


def _move(client, h, tt, section, frm, to):
    return client.post(f"/api/timetables/{tt}/move-slot", json={
        "class_group_id": section, "from_period_id": frm, "to_period_id": to}, headers=h)


def test_a_lesson_cannot_be_dragged_into_the_class_teacher_period(client, world):
    w, h = world
    put(client, w, h, **DAY, class_teacher_period={"enabled": True})
    tt, lessons, other = _timetable(w)
    r = _move(client, h, tt, w["six"], lessons[1], other["class_teacher"])
    assert r.status_code == 400
    assert "class teacher period" in r.json()["detail"]


def test_a_lesson_cannot_be_dragged_into_its_grades_zero_period(client, world):
    w, h = world
    put(client, w, h, **DAY, zero_period={"enabled": True, "scope": "grade",
                                          "placements": [{"grade": "Grade 6", "every_day": 2}]})
    tt, lessons, _ = _timetable(w)
    r = _move(client, h, tt, w["six"], lessons[1], lessons[2])
    assert r.status_code == 400
    assert "Grade 6's zero period" in r.json()["detail"]


def test_another_grade_can_use_that_slot(client, world):
    w, h = world
    put(client, w, h, **DAY, zero_period={"enabled": True, "scope": "grade",
                                          "placements": [{"grade": "Grade 6", "every_day": 2}]})
    tt, lessons, _ = _timetable(w, section="seven")
    assert _move(client, h, tt, w["seven"], lessons[1], lessons[2]).status_code == 200


# ---------------------------------------------------------------------------
# Class teachers
# ---------------------------------------------------------------------------


def test_a_section_gets_a_class_teacher(client, world):
    w, h = world
    r = client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": w["rao"]}, headers=h)
    assert r.status_code == 200 and r.json()["class_teacher_id"] == w["rao"]
    listed = client.get(f"/api/class-groups?school_id={w['school']}", headers=h).json()
    assert next(c for c in listed if c["id"] == w["six"])["class_teacher_id"] == w["rao"]


def test_a_class_teacher_can_be_cleared(client, world):
    w, h = world
    client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": w["rao"]}, headers=h)
    r = client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": None}, headers=h)
    assert r.json()["class_teacher_id"] is None


def test_renaming_a_section_leaves_its_class_teacher_alone(client, world):
    w, h = world
    client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": w["rao"]}, headers=h)
    r = client.put(f"/api/class-groups/{w['six']}", json={"name": "B"}, headers=h)
    assert r.json()["class_teacher_id"] == w["rao"]


def test_another_schools_teacher_cannot_be_class_teacher(client, world):
    w, h = world
    _, other = signup(client, email="o@o.com")
    theirs = create_school(client, other)
    db = SessionLocal()
    try:
        t = Teacher(school_id=theirs["id"], name="Outsider", qualified_subject_ids=[])
        db.add(t)
        db.commit()
        tid = t.id
    finally:
        db.close()
    assert client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": tid}, headers=h).status_code == 404


def test_deleting_a_teacher_clears_them_as_class_teacher(client, world):
    w, h = world
    client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": w["rao"]}, headers=h)
    assert client.delete(f"/api/teachers/{w['rao']}", headers=h).status_code == 204
    assert client.get(f"/api/class-groups/{w['six']}", headers=h).json()["class_teacher_id"] is None


def test_renaming_a_grade_takes_its_zero_periods_with_it(client, world):
    w, h = world
    put(client, w, h, **DAY, zero_period={"enabled": True, "scope": "grade",
                                          "placements": [{"grade": "Grade 6", "every_day": 2}]})
    client.put(f"/api/class-groups/{w['six']}", json={"grade": "Class VI"}, headers=h)
    db = SessionLocal()
    try:
        assert [z.grade for z in db.query(ZeroPeriod).all()] == ["Class VI"]
    finally:
        db.close()


def test_a_grade_still_in_use_keeps_its_zero_periods(client, world):
    w, h = world
    client.post("/api/class-groups", json={"school_id": w["school"], "grade": "Grade 6", "name": "B"}, headers=h)
    put(client, w, h, **DAY, zero_period={"enabled": True, "scope": "grade",
                                          "placements": [{"grade": "Grade 6", "every_day": 2}]})
    client.put(f"/api/class-groups/{w['six']}", json={"grade": "Grade 7"}, headers=h)
    db = SessionLocal()
    try:
        assert [z.grade for z in db.query(ZeroPeriod).all()] == ["Grade 6"]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Exports and the AI's view of the day
# ---------------------------------------------------------------------------


def test_the_export_names_the_special_periods(client, world):
    w, h = world
    client.put(f"/api/class-groups/{w['six']}", json={"class_teacher_id": w["rao"]}, headers=h)
    put(client, w, h, **DAY, class_teacher_period={"enabled": True}, breaks=[{"after": 1, "label": "Lunch"}],
        zero_period={"enabled": True, "scope": "grade", "placements": [{"grade": "Grade 6", "every_day": 3}]})
    tt, _, _ = _timetable(w)
    r = client.get(f"/api/timetables/{tt}/export?format=xlsx", headers=h)
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    sheet = [[c.value for c in row] for row in wb["Grade 6 - A"].iter_rows()]
    # Layout: heading, subtitle, spacer, header row, then the periods. A break
    # is one band across the week, so its name sits in the day cells and the
    # period column is left empty.
    rows = sheet[4:]
    labels = [row[0] or row[1] for row in rows]
    assert labels == ["Class teacher", "Period 1", "Lunch", "Period 2", "Period 3", "Period 4"]
    assert rows[0][1] == "Class teacher\nMrs. Rao"
    assert rows[4][1] == "Zero period"
    pdf = client.get(f"/api/timetables/{tt}/export?format=pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_the_ai_is_told_lessons_are_numbered_and_the_rest_are_not():
    week = [(0, 0, None, "class_teacher")] + [(0, o, None, "lesson") for o in range(1, 4)] + \
           [(0, 4, "Lunch", "break")] + [(0, o, None, "lesson") for o in range(5, 7)]
    summary = _period_summary(week)
    assert "5 periods per day, numbered 1 to 5" in summary
    assert "class teacher period" in summary and "at the start of the day" in summary
    assert '"Lunch"' in summary and "after period 3" in summary

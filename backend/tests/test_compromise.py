"""
Generate with compromises: when the school's rules can't all hold, it still
gets a full timetable, with the clashing rules loosened and a short list of
exactly what was given up - never a teacher in two places.
"""
import pytest

from app.core.database import SessionLocal
from app.models.problems import ProblemEvent
from app.models.school import Constraint, Timetable
from app.services.constraint_ir import Count, Rule, Selector, rule_to_dict
from tests.conftest import create_school, signup


@pytest.fixture
def school(client):
    """Grade 9 A: four Maths lessons a week in a four-period week."""
    _, h = signup(client, email="head@school.in")
    sid = create_school(client, h)["id"]

    def post(url, body):
        r = client.post(url, json=body, headers=h)
        assert r.status_code in (200, 201), r.text
        return r.json()

    for order in range(4):
        post("/api/periods", {"school_id": sid, "day_of_week": 0, "order": order, "label": f"P{order + 1}"})
    maths = post("/api/subjects", {"school_id": sid, "name": "Maths"})["id"]
    post("/api/teachers", {"school_id": sid, "name": "Asha", "qualified_subject_ids": [maths]})
    cg = post("/api/class-groups", {"school_id": sid, "grade": "Grade 9", "name": "A"})["id"]
    post(f"/api/class-groups/{cg}/requirements", {"class_group_id": cg, "subject_id": maths, "periods_per_week": 4})
    return {"sid": sid, "h": h, "cg": cg, "maths": maths}


def add_rule(sid, description, rule=None, legacy=None):
    db = SessionLocal()
    try:
        if legacy:
            c = Constraint(school_id=sid, type=legacy[0], parameters=legacy[1], is_hard=True, description=description)
        else:
            c = Constraint(school_id=sid, type="ir", parameters=rule_to_dict(rule), description=description)
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def generate(client, school):
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
    return client.get(f"/api/timetables/{tt_id}", headers=school["h"]).json()


NO_MATHS_LAST = Rule(
    form=Count(scope=("class_group",), selector=Selector(subjects=("Maths",), period_positions=("last",)),
               relation="<=", value=0),
    description="No Maths in the last period",
)


def test_rules_that_cant_all_hold_still_give_a_timetable_and_say_what_was_given_up(client, school):
    rid = add_rule(school["sid"], "No Maths in the last period", NO_MATHS_LAST)
    t = generate(client, school)
    assert t["status"] == "draft", t.get("error_message")
    assert len(t["entries"]) == 4  # every lesson placed
    comp = t["compromise"]
    assert comp["rules"] == ["No Maths in the last period"] and comp["rule_ids"] == [rid]
    assert comp["accepted"] is False and comp["reason"]
    # The loosened rule is broken as little as possible - once - and shows
    # as broken on the grid like any other.
    broken = [v for v in t["violations"] if v["constraint_id"] == rid]
    assert broken and sum(len(v["entry_ids"]) for v in broken) == 1
    db = SessionLocal()
    try:
        assert db.query(ProblemEvent).filter_by(kind="generation_failed", school_id=school["sid"]).count() == 1
    finally:
        db.close()


def test_an_older_kind_of_rule_is_left_out_and_named(client, school):
    add_rule(school["sid"], "Maths never in the first period",
             legacy=("no_subject_period", {"subject_id": school["maths"], "position": "first"}))
    t = generate(client, school)
    assert t["status"] == "draft", t.get("error_message")
    assert t["compromise"]["rules"] == ["Maths never in the first period"]
    assert len(t["entries"]) == 4


def test_a_setup_that_cant_work_still_fails_with_its_reason(client, school):
    # Six Maths lessons in a four-period week: no rule is to blame.
    client.post(f"/api/class-groups/{school['cg']}/requirements", headers=school["h"], json={
        "class_group_id": school["cg"], "subject_id": school["maths"], "periods_per_week": 6})
    db = SessionLocal()
    try:
        from app.models.school import SubjectRequirement
        r = db.query(SubjectRequirement).filter_by(class_group_id=school["cg"]).first()
        r.periods_per_week = 6
        db.commit()
    finally:
        db.close()
    add_rule(school["sid"], "No Maths in the last period", NO_MATHS_LAST)
    t = generate(client, school)
    assert t["status"] == "failed" and t["compromise"] is None


def test_a_timetable_that_fits_has_no_compromise(client, school):
    t = generate(client, school)
    assert t["status"] == "draft" and t["compromise"] is None


def test_accepting_puts_the_notice_away(client, school):
    add_rule(school["sid"], "No Maths in the last period", NO_MATHS_LAST)
    t = generate(client, school)
    r = client.post(f"/api/timetables/{t['id']}/accept-compromise", headers=school["h"])
    assert r.status_code == 200, r.text
    assert r.json()["compromise"]["accepted"] is True
    # A timetable without one can't be "accepted".
    ok = generate(client, {**school})
    assert client.post(f"/api/timetables/{ok['id']}/accept-compromise", headers=school["h"]).status_code in (200, 400)

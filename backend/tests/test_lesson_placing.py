"""
Building a timetable by hand: the cards, placing a lesson, taking one off,
starting blank, and generating around what's been placed.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, ElectiveOption, Period, Room, School, Subject, SubjectRequirement, Teacher,
    Timetable,
)
from app.routers import timetables as router_module
from app.services.solver import KEEP_PLACED
from tests.conftest import create_school, signup


@pytest.fixture
def world(client):
    """Grade 9 A and B, Physics with Susan or George, Maths with Emmanuel, a
    lab, and a Grade 11 block. Two days of three periods, then a break."""
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        periods = [Period(school_id=sid, day_of_week=d, order=o, label=f"P{o + 1}") for d in range(2) for o in range(3)]
        brk = Period(school_id=sid, day_of_week=0, order=3, is_break=True)
        physics = Subject(school_id=sid, name="Physics", required_room_type="lab")
        maths = Subject(school_id=sid, name="Maths")
        accounts = Subject(school_id=sid, name="Accounts")
        robotics = Subject(school_id=sid, name="Robotics", lab_batch_count=2)
        db.add_all([*periods, brk, physics, maths, accounts, robotics])
        db.flush()
        susan = Teacher(school_id=sid, name="Susan", qualified_subject_ids=[physics.id], qualified_grades=["Grade 9", "Grade 11"])
        george = Teacher(school_id=sid, name="George", qualified_subject_ids=[physics.id, robotics.id])
        emmanuel = Teacher(school_id=sid, name="Emmanuel", qualified_subject_ids=[maths.id, robotics.id])
        nair = Teacher(school_id=sid, name="Nair", qualified_subject_ids=[accounts.id])
        a = ClassGroup(school_id=sid, grade="Grade 9", name="A")
        b = ClassGroup(school_id=sid, grade="Grade 9", name="B")
        c = ClassGroup(school_id=sid, grade="Grade 10", name="A")
        d = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        room = Room(school_id=sid, name="Lab 1", room_type="lab")
        db.add_all([susan, george, emmanuel, nair, a, b, c, d, room])
        db.flush()
        db.add_all([
            SubjectRequirement(class_group_id=a.id, subject_id=physics.id, periods_per_week=2),
            SubjectRequirement(class_group_id=b.id, subject_id=physics.id, periods_per_week=1),
            SubjectRequirement(class_group_id=c.id, subject_id=physics.id, periods_per_week=1),
            SubjectRequirement(class_group_id=a.id, subject_id=maths.id, periods_per_week=1, preferred_teacher_id=emmanuel.id),
            SubjectRequirement(class_group_id=a.id, subject_id=robotics.id, periods_per_week=1),
        ])
        block = ElectiveBlock(school_id=sid, class_group_id=d.id, name="Block A", periods_per_week=1,
                              options=[ElectiveOption(subject_id=physics.id), ElectiveOption(subject_id=accounts.id)])
        tt = Timetable(school_id=sid, status="draft", solver_status="manual", version_number=1)
        db.add_all([block, tt])
        db.commit()
        yield {
            "sid": sid, "headers": headers, "tt": tt.id, "periods": [p.id for p in periods], "break": brk.id,
            "physics": physics.id, "maths": maths.id, "robotics": robotics.id, "room": room.id, "block": block.id,
            "susan": susan.id, "george": george.id, "emmanuel": emmanuel.id, "nair": nair.id,
            "a": a.id, "b": b.id, "c": c.id, "d": d.id,
        }
    finally:
        db.close()


def place(client, w, period=0, section="a", subject="physics", teacher="susan", tt=None):
    return client.post(f"/api/timetables/{tt or w['tt']}/place-lesson", headers=w["headers"], json={
        "class_group_id": w[section], "subject_id": w[subject], "teacher_id": w[teacher], "period_id": w["periods"][period],
    })


def lessons(client, w):
    res = client.get(f"/api/timetables/lessons?school_id={w['sid']}", headers=w["headers"])
    assert res.status_code == 200
    return res.json()


def test_cards_follow_qualifications(client, world):
    w = world
    by = {(r["class_group_id"], r["label"]): r for r in lessons(client, w)}
    assert set(by[(w["a"], "Physics")]["teacher_ids"]) == {w["susan"], w["george"]}
    # Susan's grades stop at 9 and 11, so Grade 10 is George's alone.
    assert by[(w["c"], "Physics")]["teacher_ids"] == [w["george"]]
    # The plan's chosen teacher is the only one offered.
    assert by[(w["a"], "Maths")]["teacher_ids"] == [w["emmanuel"]]
    assert by[(w["a"], "Robotics")]["split"] is True
    block = by[(w["d"], "Block A")]
    assert block["detail"] == "Physics / Accounts"
    assert set(block["teacher_ids"]) == {w["susan"], w["george"], w["nair"]}


def test_place_a_lesson(client, world):
    w = world
    res = place(client, w)
    assert res.status_code == 200, res.text
    entry = res.json()["entries"][0]
    assert entry["teacher_name"] == "Susan" and entry["subject_name"] == "Physics"
    assert entry["period_id"] == w["periods"][0]
    assert entry["room_id"] == w["room"], "a subject needing a lab gets a free one"


@pytest.mark.parametrize("second, message", [
    ({"period": 0, "subject": "maths", "teacher": "emmanuel"}, "already has a lesson"),
    ({"period": 0, "section": "b"}, "already teaching"),
    ({"period": 1, "teacher": "george"}, "already teaches this subject"),
])
def test_place_refuses_what_cant_be(client, world, second, message):
    w = world
    assert place(client, w).status_code == 200
    res = place(client, w, **second)
    assert res.status_code == 400 and message in res.json()["detail"]


def test_second_physics_with_no_lab_free_still_places(client, world):
    w = world
    place(client, w)
    res = place(client, w, period=0, section="b", teacher="george")
    assert res.status_code == 200
    assert res.json()["entries"][0]["room_id"] is None, "rooms are best effort, as the solver's are"


def test_place_refuses_more_than_the_plan_asks(client, world):
    w = world
    assert place(client, w, section="b").status_code == 200
    res = place(client, w, period=1, section="b")
    assert res.status_code == 400 and "placed already" in res.json()["detail"]


def test_place_refuses_an_unqualified_teacher(client, world):
    res = place(client, world, section="c", teacher="susan")
    assert res.status_code == 400 and "set up" in res.json()["detail"]


def test_place_refuses_a_split_lab(client, world):
    res = place(client, world, subject="robotics", teacher="george")
    assert res.status_code == 400 and "Split labs" in res.json()["detail"]


def test_place_refuses_a_break_and_a_frozen_section(client, world):
    w = world
    res = client.post(f"/api/timetables/{w['tt']}/place-lesson", headers=w["headers"], json={
        "class_group_id": w["a"], "subject_id": w["physics"], "teacher_id": w["susan"], "period_id": w["break"],
    })
    assert res.status_code == 400
    db = SessionLocal()
    db.get(ClassGroup, w["a"]).frozen = True
    db.commit()
    db.close()
    res = place(client, w)
    assert res.status_code == 400 and "frozen" in res.json()["detail"].lower()


def test_place_a_block_gives_every_group_a_teacher(client, world):
    w = world
    res = client.post(f"/api/timetables/{w['tt']}/place-lesson", headers=w["headers"], json={
        "block_id": w["block"], "teacher_id": w["nair"], "period_id": w["periods"][2],
    })
    assert res.status_code == 200, res.text
    rows = res.json()["entries"]
    assert {r["subject_name"] for r in rows} == {"Physics", "Accounts"}
    assert {r["elective_block_id"] for r in rows} == {w["block"]}
    assert next(r for r in rows if r["subject_name"] == "Accounts")["teacher_name"] == "Nair"
    assert next(r for r in rows if r["subject_name"] == "Physics")["teacher_name"] in ("Susan", "George")


def test_remove_and_restore(client, world):
    w = world
    entry = place(client, w).json()["entries"][0]
    url = f"/api/timetables/{w['tt']}"
    res = client.post(f"{url}/remove-slot", headers=w["headers"], json={"class_group_id": w["a"], "period_id": entry["period_id"]})
    assert res.status_code == 200 and res.json()["removed_ids"] == [entry["id"]]
    assert client.get(url, headers=w["headers"]).json()["entries"] == []

    back = {k: entry[k] for k in ("class_group_id", "subject_id", "teacher_id", "room_id", "period_id")}
    res = client.post(f"{url}/restore-slot", headers=w["headers"], json={"entries": [back]})
    assert res.status_code == 200 and res.json()["entries"][0]["teacher_name"] == "Susan"
    # Something else took the place: refused, not double-booked.
    assert client.post(f"{url}/remove-slot", headers=w["headers"],
                       json={"class_group_id": w["a"], "period_id": entry["period_id"]}).status_code == 200
    assert place(client, w, section="b").status_code == 200
    assert client.post(f"{url}/restore-slot", headers=w["headers"], json={"entries": [back]}).status_code == 400


def test_remove_refuses_a_locked_lesson(client, world):
    w = world
    entry = place(client, w).json()["entries"][0]
    client.post(f"/api/timetables/{w['tt']}/lock-slot", headers=w["headers"],
                json={"class_group_id": w["a"], "period_id": entry["period_id"], "locked": True})
    res = client.post(f"/api/timetables/{w['tt']}/remove-slot", headers=w["headers"],
                      json={"class_group_id": w["a"], "period_id": entry["period_id"]})
    assert res.status_code == 400 and "locked" in res.json()["detail"]


def test_restore_cant_point_at_another_school(client, world):
    w = world
    _, other_headers = signup(client, email="other@a.com")
    other = create_school(client, other_headers, name="Other")["id"]
    db = SessionLocal()
    stranger = Teacher(school_id=other, name="Stranger", qualified_subject_ids=[])
    db.add(stranger)
    db.commit()
    stranger_id = stranger.id
    db.close()
    res = client.post(f"/api/timetables/{w['tt']}/restore-slot", headers=w["headers"], json={"entries": [{
        "class_group_id": w["a"], "subject_id": w["physics"], "teacher_id": stranger_id, "period_id": w["periods"][0],
    }]})
    assert res.status_code in (400, 404)


@pytest.mark.parametrize("call", [
    lambda c, w, h: c.get(f"/api/timetables/lessons?school_id={w['sid']}", headers=h),
    lambda c, w, h: c.post(f"/api/timetables/blank?school_id={w['sid']}", headers=h),
    lambda c, w, h: c.post(f"/api/timetables/{w['tt']}/forecast", headers=h, json={"teacher_id": w["susan"]}),
    lambda c, w, h: c.post(f"/api/timetables/{w['tt']}/place-lesson", headers=h, json={
        "class_group_id": w["a"], "subject_id": w["physics"], "teacher_id": w["susan"], "period_id": w["periods"][0]}),
    lambda c, w, h: c.post(f"/api/timetables/{w['tt']}/remove-slot", headers=h, json={"class_group_id": w["a"], "period_id": w["periods"][0]}),
    lambda c, w, h: c.post(f"/api/timetables/{w['tt']}/restore-slot", headers=h, json={"entries": []}),
])
def test_other_schools_are_refused(client, world, call):
    _, other_headers = signup(client, email="other@a.com")
    assert call(client, world, other_headers).status_code in (403, 404)


def test_start_blank(client, world):
    w = world
    res = client.post(f"/api/timetables/blank?school_id={w['sid']}", headers=w["headers"])
    assert res.status_code == 201, res.text
    blank = res.json()
    assert blank["status"] == "draft" and blank["entries"] == [] and blank["version_number"] == 2
    assert blank["is_current"] is True
    versions = client.get(f"/api/timetables?school_id={w['sid']}", headers=w["headers"]).json()
    assert {v["id"] for v in versions} >= {w["tt"], blank["id"]}, "earlier versions stay"
    assert place(client, w, tt=blank["id"]).status_code == 200


def test_forecast_warns_and_saves_nothing(client, world):
    w = world
    place(client, w)
    url = f"/api/timetables/{w['tt']}"
    before = client.get(url, headers=w["headers"]).json()["entries"]
    db = SessionLocal()
    db.get(Teacher, w["susan"]).unavailable_period_ids = [w["periods"][1]]
    db.commit()
    db.close()
    res = client.post(f"{url}/forecast", headers=w["headers"], json={"teacher_id": w["susan"]})
    assert res.status_code == 200, res.text
    moved = res.json()["slots"][f"{w['a']}:{w['periods'][0]}"][str(w["periods"][1])]
    assert moved["status"] == "warn" and "unavailable" in moved["reason"]
    assert client.get(url, headers=w["headers"]).json()["entries"] == before


def test_rules_broken_by_a_lesson_not_yet_placed(client, world):
    """The same rule engine as the warnings, counting a lesson that doesn't exist yet."""
    from app.services.constraint_ir_checker import Placement, Violation
    from app.services.slot_board import Board
    w = world
    db = SessionLocal()
    timetable = db.get(Timetable, w["tt"])
    period = db.get(Period, w["periods"][0])
    seen = []

    def fake_check(placements, rules, index):
        seen.append(list(placements))
        if any(p.entry_id == -1 for p in placements):
            return [Violation(constraint_id=1, description="No Physics first", detail="x", entry_ids=[-1], strength="required")]
        return []

    import app.services.slot_board as slot_board
    original, slot_board.check_rules = slot_board.check_rules, fake_check
    try:
        board = Board(db, timetable, rules=([], None))
        extra = [Placement(entry_id=-1, class_group_id=w["a"], subject_id=w["physics"], teacher_id=w["susan"],
                           period_id=period.id, day_of_week=period.day_of_week, order=period.order, occupies_teacher=True)]
        assert board.rules_broken_by(extra) == ["No Physics first"]
        assert board.extra == [], "the pretend lesson doesn't stay on the board"
    finally:
        slot_board.check_rules = original
        db.close()


def _generate_now(school_id, keep_placed):
    db = SessionLocal()
    tt = Timetable(school_id=school_id, status="generating", version_number=99)
    db.add(tt)
    db.commit()
    tid = tt.id
    db.close()
    token = KEEP_PLACED.set(keep_placed)
    try:
        router_module._generate(tid, school_id)
    finally:
        KEEP_PLACED.reset(token)
    return tid


def test_generating_keeps_what_was_placed_and_fills_the_rest(client, world):
    w = world
    # Tuesday's last period: nothing would choose it for this on its own.
    placed = place(client, w, period=5).json()["entries"][0]
    tid = _generate_now(w["sid"], True)
    got = client.get(f"/api/timetables/{tid}", headers=w["headers"]).json()
    assert got["status"] == "draft", got["error_message"]
    rows = [e for e in got["entries"] if e["class_group_id"] == w["a"] and e["subject_id"] == w["physics"]]
    assert len(rows) == 2, "the plan's two Physics lessons, one kept and one added"
    assert any(e["period_id"] == placed["period_id"] for e in rows)
    assert all(e["teacher_id"] == w["susan"] for e in rows), "one teacher per subject per section"
    assert not any(e["locked"] for e in got["entries"]), "kept, not locked"
    subjects = {(e["class_group_id"], e["subject_id"]) for e in got["entries"]}
    assert (w["a"], w["maths"]) in subjects and (w["b"], w["physics"]) in subjects, "the gaps are filled"


def test_the_generate_route_keeps_what_was_placed(client, world):
    """The real route: the flag has to reach the background thread."""
    import time
    w = world
    placed = place(client, w, period=5).json()["entries"][0]
    res = client.post(f"/api/timetables/generate?school_id={w['sid']}&keep_placed=true", headers=w["headers"])
    assert res.status_code == 201, res.text
    tid = res.json()["id"]
    for _ in range(300):
        got = client.get(f"/api/timetables/{tid}", headers=w["headers"]).json()
        if got["status"] != "generating":
            break
        time.sleep(0.1)
    assert got["status"] == "draft", got["error_message"]
    assert any(e["period_id"] == placed["period_id"] and e["subject_id"] == w["physics"] and e["class_group_id"] == w["a"]
               for e in got["entries"])
    assert got["is_current"] is True and got["id"] != w["tt"]


def test_a_rule_saved_later_still_warns_when_placing_by_hand(client, world):
    """A rule added after a generated version isn't held against it, but
    whoever is placing lessons should still see the amber."""
    from datetime import datetime, timedelta, timezone

    from app.services.constraint_ir import Count, Rule, Selector, rule_to_dict
    w = world
    db = SessionLocal()
    tt = db.get(Timetable, w["tt"])
    tt.solver_status = "optimal"
    tt.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    rule = Rule(form=Count(scope=("teacher",), selector=Selector(teachers=("Susan",), period_orders=(2,)), relation="<=", value=0),
                description="Susan: not in period 2")
    db.add(Constraint(school_id=w["sid"], type="ir", parameters=rule_to_dict(rule), description=rule.description,
                      created_at=datetime.now(timezone.utc)))
    db.commit()
    db.close()
    res = client.post(f"/api/timetables/{w['tt']}/forecast", headers=w["headers"], json={"teacher_id": w["susan"]}).json()
    lesson = next(x for x in lessons(client, w) if x["class_group_id"] == w["a"] and x["label"] == "Physics")
    assert res["cards"][lesson["key"]][str(w["periods"][1])]["reason"] == "Susan: not in period 2"
    # The timetable itself isn't blamed for a rule newer than it.
    assert place(client, w, period=1).json()["violations"] == []


def test_a_timetable_built_by_hand_is_held_to_every_rule(client, world):
    from datetime import datetime, timedelta, timezone

    from app.services.constraint_ir import Count, Rule, Selector, rule_to_dict
    w = world
    db = SessionLocal()
    db.get(Timetable, w["tt"]).created_at = datetime.now(timezone.utc) - timedelta(days=1)
    rule = Rule(form=Count(scope=("teacher",), selector=Selector(teachers=("Susan",), period_orders=(2,)), relation="<=", value=0),
                description="Susan: not in period 2")
    db.add(Constraint(school_id=w["sid"], type="ir", parameters=rule_to_dict(rule), description=rule.description,
                      created_at=datetime.now(timezone.utc)))
    db.commit()
    db.close()
    violations = place(client, w, period=1).json()["violations"]
    assert [v["description"] for v in violations] == ["Susan: not in period 2"]


def test_generating_without_the_flag_rebuilds(client, world):
    w = world
    place(client, w, period=5)
    db = SessionLocal()
    current = db.get(School, w["sid"]).current_timetable_id
    db.close()
    tid = _generate_now(w["sid"], False)
    assert tid != current
    got = client.get(f"/api/timetables/{tid}", headers=w["headers"]).json()
    assert got["status"] == "draft"
    assert not any(e["locked"] for e in got["entries"])

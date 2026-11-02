"""
Where a dragged slot can go: every period of the section marked ok, warn
(allowed, but a rule or a teacher's unavailability is broken) or blocked
(move-slot would refuse it), with the reason - and the answer has to agree
with what move-slot then actually does.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, ElectiveOption, Period, Subject, Teacher, Timetable,
    TimetableEntry,
)
from app.services.constraint_ir import Count, Rule, Selector, rule_to_dict
from tests.conftest import create_school, signup


@pytest.fixture
def world(client):
    """One day of four periods, then a break.

    11 A: English with Verma in P2. A block (Physics/Accounts) in P1.
    11 B: Maths with Verma in P3.
    """
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        periods = [Period(school_id=sid, day_of_week=0, order=o, label=f"P{o + 1}") for o in range(4)]
        brk = Period(school_id=sid, day_of_week=0, order=4, is_break=True)
        subjects = {n: Subject(school_id=sid, name=n) for n in ("English", "Maths", "Physics", "Accounts")}
        teachers = {n: Teacher(school_id=sid, name=n, qualified_subject_ids=[]) for n in ("Verma", "Rao", "Khan")}
        a = ClassGroup(school_id=sid, grade="Grade 11", name="A")
        b = ClassGroup(school_id=sid, grade="Grade 11", name="B")
        db.add_all([*periods, brk, *subjects.values(), *teachers.values(), a, b])
        db.commit()
        block = ElectiveBlock(school_id=sid, class_group_id=a.id, name="Block 1", periods_per_week=1,
                              options=[ElectiveOption(subject_id=subjects[n].id) for n in ("Physics", "Accounts")])
        tt = Timetable(school_id=sid, status="draft", solver_status="optimal")
        db.add_all([block, tt])
        db.commit()

        def entry(cg, subject, teacher, period, **kw):
            e = TimetableEntry(timetable_id=tt.id, class_group_id=cg.id, subject_id=subjects[subject].id,
                               teacher_id=teachers[teacher].id, period_id=periods[period].id, **kw)
            db.add(e)
            return e

        entry(a, "Physics", "Rao", 0, elective_block_id=block.id)
        entry(a, "Accounts", "Khan", 0, elective_block_id=block.id)
        english = entry(a, "English", "Verma", 1)
        entry(b, "Maths", "Verma", 2)
        db.commit()
        ids = {"sid": sid, "tt": tt.id, "a": a.id, "b": b.id, "p": [p.id for p in periods], "break": brk.id,
               "english": english.id, "verma": teachers["Verma"].id}
    finally:
        db.close()
    return ids, headers


def targets(client, headers, w, section, period):
    r = client.post(f"/api/timetables/{w['tt']}/move-targets",
                    json={"class_group_id": section, "from_period_id": period}, headers=headers)
    assert r.status_code == 200, r.text
    return {t["period_id"]: t for t in r.json()["targets"]}


def move(client, headers, w, section, frm, to):
    return client.post(f"/api/timetables/{w['tt']}/move-slot",
                       json={"class_group_id": section, "from_period_id": frm, "to_period_id": to}, headers=headers)


def test_each_period_is_ok_or_blocked_with_the_reason(client, world):
    w, headers = world
    p = w["p"]
    t = targets(client, headers, w, w["a"], p[1])
    assert set(t) == {p[0], p[2], p[3]}  # not its own period, not the break
    assert t[p[0]]["status"] == "ok"  # swaps with the block
    assert t[p[3]]["status"] == "ok"
    assert t[p[2]] == {"period_id": p[2], "status": "blocked", "reason": "Verma teaches Grade 11 B then"}


def test_the_answer_matches_what_move_slot_does(client, world):
    w, headers = world
    p = w["p"]
    t = targets(client, headers, w, w["a"], p[1])
    assert move(client, headers, w, w["a"], p[1], p[2]).status_code == 400
    assert t[p[3]]["status"] == "ok" and move(client, headers, w, w["a"], p[1], p[3]).status_code == 200


def test_a_locked_slot_there_is_named(client, world):
    w, headers = world
    p = w["p"]
    assert client.post(f"/api/timetables/{w['tt']}/lock-slot",
                       json={"class_group_id": w["a"], "period_id": p[0], "locked": True},
                       headers=headers).status_code == 200
    t = targets(client, headers, w, w["a"], p[1])
    assert t[p[0]]["status"] == "blocked" and "is locked there" in t[p[0]]["reason"]
    assert move(client, headers, w, w["a"], p[1], p[0]).status_code == 400


def test_allowed_but_breaking_a_rule_or_unavailability_is_a_warning(client, world):
    w, headers = world
    p = w["p"]
    db = SessionLocal()
    try:
        rule = Rule(form=Count(scope=("class_group",), selector=Selector(subjects=("English",), period_positions=("last",)),
                               relation="<=", value=0), description="No English in the last period")
        db.add(Constraint(school_id=w["sid"], type="ir", parameters=rule_to_dict(rule),
                          description="No English in the last period"))
        verma = db.get(Teacher, w["verma"])
        verma.unavailable_period_ids = [p[0]]
        db.commit()
    finally:
        db.close()
    t = targets(client, headers, w, w["a"], p[1])
    assert t[p[3]]["status"] == "warn" and "No English in the last period" in t[p[3]]["reason"]
    assert t[p[0]]["status"] == "warn" and t[p[0]]["reason"] == "Verma is marked unavailable then"
    assert move(client, headers, w, w["a"], p[1], p[3]).status_code == 200  # allowed, as promised


def test_a_frozen_section_blocks_everything(client, world):
    w, headers = world
    db = SessionLocal()
    try:
        db.get(ClassGroup, w["a"]).frozen = True
        db.commit()
    finally:
        db.close()
    t = targets(client, headers, w, w["a"], w["p"][1])
    assert all(x["status"] == "blocked" and "frozen" in x["reason"] for x in t.values())


def test_viewers_cant_ask(client, world):
    w, _ = world
    _, other = signup(client, email="stranger@example.com")
    r = client.post(f"/api/timetables/{w['tt']}/move-targets",
                    json={"class_group_id": w["a"], "from_period_id": w["p"][1]}, headers=other)
    assert r.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Suggesting a fix for a blocked move, and applying it


def suggest(client, headers, w, section, frm, to):
    r = client.post(f"/api/timetables/{w['tt']}/suggest-move",
                    json={"class_group_id": section, "from_period_id": frm, "to_period_id": to}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def chain(client, headers, w, steps):
    return client.post(f"/api/timetables/{w['tt']}/move-chain", json={"steps": [
        {k: s[k] for k in ("class_group_id", "from_period_id", "to_period_id")} for s in steps]}, headers=headers)


def periods_of(w):
    db = SessionLocal()
    try:
        return {e.id: e.period_id for e in db.query(TimetableEntry).filter_by(timetable_id=w["tt"])}
    finally:
        db.close()


def test_a_blocked_move_comes_with_a_way_to_make_room(client, world):
    w, headers = world
    p = w["p"]
    r = suggest(client, headers, w, w["a"], p[1], p[2])  # English onto P3, where Verma teaches 11 B
    assert r["status"] == "blocked" and r["reason"] == "Verma teaches Grade 11 B then"
    best = r["suggestions"][0]
    assert len(best["steps"]) == 2 and best["status"] == "ok"
    first = best["steps"][0]
    assert first["class_group_id"] == w["b"] and first["from_period_id"] == p[2]
    assert best["summary"].startswith("Verma teaches Grade 11 B then. Move Grade 11 B's Maths from Mon P3 to ")
    assert best["summary"].endswith(" as well?")
    assert best["steps"][-1]["text"] == "Move Grade 11 A's English from Mon P2 to Mon P3"
    # Nothing moved yet.
    before = periods_of(w)
    assert periods_of(w) == before

    r = chain(client, headers, w, best["steps"])
    assert r.status_code == 200, r.text
    after = periods_of(w)
    assert after[w["english"]] == p[2]


def test_a_move_that_is_fine_needs_no_suggestion(client, world):
    w, headers = world
    r = suggest(client, headers, w, w["a"], w["p"][1], w["p"][3])
    assert r["status"] == "ok" and r["suggestions"] == []


def test_a_lock_in_the_way_has_no_suggestion(client, world):
    w, headers = world
    p = w["p"]
    client.post(f"/api/timetables/{w['tt']}/lock-slot",
                json={"class_group_id": w["a"], "period_id": p[0], "locked": True}, headers=headers)
    r = suggest(client, headers, w, w["a"], p[1], p[0])
    assert r["status"] == "blocked" and r["suggestions"] == []


def test_a_chain_is_all_or_nothing(client, world):
    w, headers = world
    p = w["p"]
    before = periods_of(w)
    r = chain(client, headers, w, [
        {"class_group_id": w["a"], "from_period_id": p[1], "to_period_id": p[3]},   # fine
        {"class_group_id": w["a"], "from_period_id": p[3], "to_period_id": p[2]},   # Verma is in 11 B
    ])
    assert r.status_code == 400 and r.json()["detail"].startswith("Move 2 of 2 can't be made:")
    assert periods_of(w) == before


def test_three_moves_when_the_lesson_in_the_way_is_stuck_too(client):
    """11 A's English (Verma, P1) wants P3, where Verma teaches 11 B. Every
    other period of 11 B is full, and each lesson that would swap back into
    P3 has a teacher busy in P3 elsewhere - so 11 B's Maths can only move once
    one of those is moved first."""
    _, headers = signup(client)
    sid = create_school(client, headers)["id"]
    db = SessionLocal()
    try:
        periods = [Period(school_id=sid, day_of_week=0, order=o) for o in range(4)]
        names = ("English", "Maths", "Art", "Hindi", "PE", "Music")
        subjects = {n: Subject(school_id=sid, name=n) for n in names}
        teachers = {n: Teacher(school_id=sid, name=n, qualified_subject_ids=[])
                    for n in ("Verma", "Das", "Rao", "Nair", "Iyer")}
        cg = {x: ClassGroup(school_id=sid, grade="Grade 11", name=x) for x in "ABCDE"}
        db.add_all([*periods, *subjects.values(), *teachers.values(), *cg.values()])
        db.commit()
        tt = Timetable(school_id=sid, status="draft", solver_status="optimal")
        db.add(tt)
        db.commit()

        def entry(c, subject, teacher, period):
            e = TimetableEntry(timetable_id=tt.id, class_group_id=cg[c].id, subject_id=subjects[subject].id,
                               teacher_id=teachers[teacher].id, period_id=periods[period].id)
            db.add(e)
            return e

        english = entry("A", "English", "Verma", 0)
        entry("B", "Art", "Das", 0)
        entry("B", "Hindi", "Rao", 1)
        entry("B", "Maths", "Verma", 2)
        entry("B", "PE", "Nair", 3)
        entry("C", "Art", "Das", 2)     # Das busy in P3
        entry("D", "Hindi", "Rao", 2)   # Rao busy in P3
        entry("E", "PE", "Nair", 2)     # Nair busy in P3
        db.commit()
        w = {"tt": tt.id}
        a, p, english_id = cg["A"].id, [x.id for x in periods], english.id
    finally:
        db.close()

    r = suggest(client, headers, w, a, p[0], p[2])
    assert r["status"] == "blocked" and r["suggestions"], r
    best = r["suggestions"][0]
    assert len(best["steps"]) == 3
    assert chain(client, headers, w, best["steps"]).status_code == 200
    assert periods_of(w)[english_id] == p[2]

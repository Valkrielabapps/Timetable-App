"""When a timetable is impossible for no reason the direct checks can name,
find_blocking_rules switches rules off to find which ones are to blame."""
from app.models.school import Constraint
from app.services.solver import find_blocking_rules, generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def _rule(db, school, description, parameters, hard=True):  # noqa: F811
    db.add(Constraint(school_id=school.id, type="ir", parameters=parameters, description=description, is_hard=hard))
    db.commit()


def _pe_school(db):  # noqa: F811
    school = _school(db, days=1, per_day=2)
    pe = _subject(db, school, "PE")
    _teacher(db, school, "Coach", [pe.id])
    _require(db, _class_group(db, school), pe, 1)
    return school


def _no_pe_in(period):
    return {"form": "count", "scope": [], "selector": {"subjects": ["PE"], "period_orders": [period]},
            "relation": "==", "value": 0}


def test_names_each_rule_whose_removal_is_enough(db):  # noqa: F811
    school = _pe_school(db)
    _rule(db, school, "No PE in period 1", _no_pe_in(1))
    _rule(db, school, "No PE in period 2", _no_pe_in(2))
    assert generate_school_timetable(db, school.id).status not in ("optimal", "feasible")

    (message,) = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert "No PE in period 1" in message and "No PE in period 2" in message


def test_one_rule_alone_is_named_alone(db):  # noqa: F811
    school = _pe_school(db)
    _rule(db, school, "No PE at all", {"form": "count", "scope": [], "selector": {"subjects": ["PE"]},
                                        "relation": "==", "value": 0})
    _rule(db, school, "Harmless", _no_pe_in(1), hard=False)
    (message,) = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert message.startswith("The rule “No PE at all” makes the timetable impossible")
    assert "Harmless" not in message


def test_says_when_the_rules_are_not_the_cause(db):  # noqa: F811
    school = _school(db, days=1, per_day=2)
    pe = _subject(db, school, "PE")
    _teacher(db, school, "Coach", [pe.id])
    _require(db, _class_group(db, school), pe, 3)  # 3 lessons, 2 periods
    _rule(db, school, "No PE in period 1", _no_pe_in(1))
    (message,) = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert message.startswith("This isn't caused by your rules")


# ---------------------------------------------------------------------------
# No rules to blame: the setup is checked instead
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from app.services.solver import _diagnose_setup  # noqa: E402


def _school_with_two_teachers(db):  # noqa: F811
    school = _school(db, days=1, per_day=2)
    eng = _subject(db, school, "English")
    rao = _teacher(db, school, "Rao", [eng.id])
    iyer = _teacher(db, school, "Iyer", [eng.id])
    cg = _class_group(db, school)
    return school, eng, rao, iyer, cg


def test_names_the_section_that_only_works_split(db):  # noqa: F811
    school, eng, rao, iyer, cg = _school_with_two_teachers(db)

    def attempt(skip, relax=frozenset()):
        if "one_teacher" in relax:  # fits only with English split between the two
            return SimpleNamespace(status="feasible", assignments=[
                {"class_group_id": cg.id, "subject_id": eng.id, "teacher_id": rao.id},
                {"class_group_id": cg.id, "subject_id": eng.id, "teacher_id": iyer.id},
            ])
        return SimpleNamespace(status="infeasible", assignments=[])

    lead, *lines = _diagnose_setup(db, school.id, attempt, set(), had_rules=False)
    assert lead.startswith("This isn't caused by any rule")
    assert "keep one teacher per subject" in lead
    assert lines == ["English in Grade 8 - A - split between Rao (1) and Iyer (1)"]


def test_names_the_teachers_over_their_limit(db):  # noqa: F811
    from app.models.school import Teacher
    school, eng, rao, iyer, cg = _school_with_two_teachers(db)
    db.get(Teacher, rao.id).max_periods_per_week = 1
    db.commit()

    def attempt(skip, relax=frozenset()):
        if "max_periods" in relax:
            return SimpleNamespace(status="feasible", assignments=[
                {"class_group_id": cg.id, "subject_id": eng.id, "teacher_id": rao.id},
                {"class_group_id": cg.id, "subject_id": eng.id, "teacher_id": rao.id},
            ])
        return SimpleNamespace(status="infeasible", assignments=[])

    lead, *lines = _diagnose_setup(db, school.id, attempt, set(), had_rules=True)
    assert lead.startswith("This isn't caused by your rules")
    assert "max periods/week" in lead
    assert lines == ["Rao: needs 2, limit 1"]


def test_a_school_with_no_rules_still_gets_a_reason(db):  # noqa: F811
    school = _school(db, days=1, per_day=2)
    pe = _subject(db, school, "PE")
    _teacher(db, school, "Coach", [pe.id])
    _require(db, _class_group(db, school), pe, 3)  # 3 lessons, 2 periods
    messages = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert messages and messages[0].startswith("This isn't caused by any rule")


# ---------------------------------------------------------------------------
# Combinations, and running out of time
# ---------------------------------------------------------------------------

import time as _time  # noqa: E402

from app.services import solver as _solver  # noqa: E402


def _four_rules(db):  # noqa: F811
    school = _pe_school(db)
    for name in "ABCD":
        _rule(db, school, f"Rule {name}", _no_pe_in(1))
    ids = {c.description[-1]: c.id for c in db.query(Constraint).filter(Constraint.school_id == school.id)}
    return school, ids


def _stub(ids, impossible, delay=0.0):
    def fake(db, school_id):
        if delay:
            _time.sleep(delay)
        on = {name for name, i in ids.items() if i not in _solver._SKIP_RULES.get()}
        return SimpleNamespace(status="infeasible" if impossible(on) else "optimal", assignments=[], errors=[])
    return fake


def test_a_combination_is_narrowed_down(db, monkeypatch):  # noqa: F811
    school, ids = _four_rules(db)
    # Impossible while A and B are both on, or C and D are: no single rule
    # removed fixes it, so the deletion filter has to find a pair.
    monkeypatch.setattr(_solver, "generate_school_timetable",
                        _stub(ids, lambda on: {"A", "B"} <= on or {"C", "D"} <= on))
    (message,) = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert message.startswith("These rules can't all be met at the same time")
    named = {n for n in "ABCD" if f"Rule {n}" in message}
    assert named in ({"A", "B"}, {"C", "D"})


def test_running_out_of_time_still_says_something(db, monkeypatch):  # noqa: F811
    school, ids = _four_rules(db)
    monkeypatch.setattr(_solver, "generate_school_timetable",
                        _stub(ids, lambda on: bool(on), delay=1.0))
    lead, *rest = find_blocking_rules(db, school.id, budget_seconds=6, per_try_seconds=5)
    assert "There wasn't time to test every rule" in lead
    assert rest  # the rules it didn't get to are listed


# ---------------------------------------------------------------------------
# Fixed periods and teachers' unavailable periods are part of the setup too:
# switching every rule off leaves them on, so they're checked on their own.
# ---------------------------------------------------------------------------

def test_names_the_fixed_period_that_makes_it_impossible(db):  # noqa: F811
    from app.models.school import School

    school = _school(db, days=2, per_day=3)
    electives = _subject(db, school, "ELECTIVES")
    eng = _subject(db, school, "English")
    _teacher(db, school, "Persis", [electives.id])  # the only one who can teach it
    _teacher(db, school, "Rao", [eng.id])
    _teacher(db, school, "Iyer", [eng.id])
    for name in "AB":
        cg = _class_group(db, school, grade="Grade 6", name=name)
        _require(db, cg, electives, 1)
        _require(db, cg, eng, 5)
    # Both sections at once, with one teacher: impossible. Anywhere else, fine.
    db.get(School, school.id).fixed_periods = [
        {"subject_id": electives.id, "grades": ["Grade 6"], "period": 1, "days": [0]}]
    db.commit()
    assert generate_school_timetable(db, school.id).status not in ("optimal", "feasible")

    message, *lines = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert "fixed periods" in message
    (line,) = lines
    assert line.startswith("Mon period 1: 2 fixed lessons need a teacher at the same moment")
    assert "free then: Persis" in line and "ELECTIVES in Grade 6 A; ELECTIVES in Grade 6 B" in line


def test_names_the_teacher_whose_unavailable_periods_make_it_impossible(db):  # noqa: F811
    from app.models.school import Period

    school = _school(db, days=1, per_day=3)
    maths = _subject(db, school, "Maths")
    eng = _subject(db, school, "English")
    anil = _teacher(db, school, "Anil", [maths.id])  # the only Maths teacher
    rao = _teacher(db, school, "Rao", [eng.id])
    _require(db, _class_group(db, school), maths, 3)
    periods = db.query(Period).filter(Period.school_id == school.id).order_by(Period.order).all()
    anil.unavailable_period_ids = [periods[2].id]  # 3 Maths lessons, 2 periods he's free
    rao.unavailable_period_ids = [periods[0].id]   # restricted too, but not the cause
    db.commit()
    assert generate_school_timetable(db, school.id).status not in ("optimal", "feasible")

    message, *lines = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert "unavailable periods" in message
    assert lines == ["Anil: unavailable for 1 period a week"]


def test_narrows_fixed_periods_that_only_clash_together(db):  # noqa: F811
    """Three subjects fixed at period 1 for one section: taking any one away
    still leaves two clashing, so no single one is to blame. The message
    narrows it to a pair that can't hold together, and doesn't blame the
    harmless fourth."""
    from app.models.school import School

    school = _school(db, days=1, per_day=4)
    subs = [_subject(db, school, n) for n in ("Art", "Music", "Dance", "Games")]
    cg = _class_group(db, school, grade="Grade 6", name="A")
    for s_ in subs:
        _require(db, cg, s_, 1)
    db.get(School, school.id).fixed_periods = [
        {"subject_id": s_.id, "grades": ["Grade 6"], "period": 1, "days": None} for s_ in subs[:3]
    ] + [{"subject_id": subs[3].id, "grades": ["Grade 6"], "period": 4, "days": None}]
    db.commit()
    message, *lines = find_blocking_rules(db, school.id, budget_seconds=60, per_try_seconds=5)
    assert "can't all hold together" in message
    assert len(lines) == 2 and not any("Games" in x for x in lines), lines

"""
The "one period of a subject a day" tick box is checked on a saved timetable
and on every drag, like a typed rule.

Reported from a real school: Grade 2 - A had Games twice on a Monday with
the box ticked, and nothing said so - the tick boxes weren't checked
anywhere after generating. "Try to" rules turned nothing amber while
dragging either.
"""
from app.models.school import Constraint, Period, School, Timetable, TimetableEntry
from app.routers.timetables import _board, _to_timetable_out
from app.services import standard_rules
from app.services.standard_checks import ONE_A_DAY
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def _timetable(db, school, lessons):
    """A draft timetable with these (section, subject, teacher, day, order) lessons."""
    periods = {(p.day_of_week, p.order): p.id for p in db.query(Period).filter(Period.school_id == school.id)}
    tt = Timetable(school_id=school.id, status="draft", solver_status="manual")
    db.add(tt)
    db.commit()
    for cg, subject, teacher, day, order in lessons:
        db.add(TimetableEntry(timetable_id=tt.id, class_group_id=cg.id, subject_id=subject.id,
                              teacher_id=teacher.id, period_id=periods[(day, order)]))
    db.commit()
    db.refresh(tt)
    return tt, periods


def _setup(db, per_week):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    games = _subject(db, school, "Games")
    rao = _teacher(db, school, "Rao", [games.id])
    a = _class_group(db, school, grade="Grade 2", name="A")
    _require(db, a, games, per_week)
    return school, games, rao, a


def _flags(db, tt):
    return [v.model_dump() for v in _to_timetable_out(db, tt).violations if v.description == ONE_A_DAY]


def test_two_games_on_one_day_is_flagged_as_a_broken_rule(db):  # noqa: F811
    school, games, rao, a = _setup(db, 3)
    tt, _ = _timetable(db, school, [(a, games, rao, 0, 2), (a, games, rao, 0, 3), (a, games, rao, 2, 1)])
    flags = _flags(db, tt)
    assert len(flags) == 1
    assert flags[0]["strength"] == "required"
    assert flags[0]["detail"] == "Grade 2 A has Games twice on Monday"
    assert len(flags[0]["entry_ids"]) == 2


def test_nothing_is_flagged_when_the_box_is_unticked_or_the_week_is_spread(db):  # noqa: F811
    school, games, rao, a = _setup(db, 3)
    spread, _ = _timetable(db, school, [(a, games, rao, 0, 1), (a, games, rao, 2, 1), (a, games, rao, 4, 1)])
    assert _flags(db, spread) == []
    bunched, _ = _timetable(db, school, [(a, games, rao, 0, 1), (a, games, rao, 0, 2), (a, games, rao, 4, 1)])
    db.get(School, school.id).standard_rules = standard_rules.to_store({"subject_spread": {"on": False}})
    db.commit()
    assert _flags(db, bunched) == []


def test_more_periods_than_days_only_asks_for_an_even_spread(db):  # noqa: F811
    """6 over 5 days: one day of two is right, a day of three (or a day
    without any while another has two) is a preference not met."""
    school, games, rao, a = _setup(db, 6)
    fine, _ = _timetable(db, school, [(a, games, rao, d, 1) for d in range(5)] + [(a, games, rao, 0, 2)])
    assert _flags(db, fine) == []
    three = [(a, games, rao, 0, o) for o in (1, 2, 3)] + [(a, games, rao, d, 1) for d in (1, 2, 3)]
    flags = _flags(db, _timetable(db, school, three)[0])
    assert [f["strength"] for f in flags] == ["preference"]
    assert "3 times on Monday" in flags[0]["detail"]


def test_a_drag_onto_a_second_games_that_day_turns_amber(db):  # noqa: F811
    school, games, rao, a = _setup(db, 2)
    tt, periods = _timetable(db, school, [(a, games, rao, 0, 1), (a, games, rao, 2, 1)])
    board = _board(db, tt)
    verdict = board.judge(a.id, periods[(2, 1)], periods[(0, 3)])
    assert verdict.status == "warn"
    assert "Grade 2 A has Games twice on Monday" in verdict.reason and ONE_A_DAY in verdict.reason
    assert board.judge(a.id, periods[(2, 1)], periods[(3, 2)]).status == "ok"


def test_a_drag_against_a_try_to_rule_turns_amber_too(db):  # noqa: F811
    school, games, rao, a = _setup(db, 2)
    db.add(Constraint(
        school_id=school.id, type="ir", is_hard=False,
        parameters={"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Games"], "period_orders": [1]},
                    "relation": "==", "value": 0, "strength": "preference"},
        description="Try to keep Games out of period 1",
    ))
    db.commit()
    tt, periods = _timetable(db, school, [(a, games, rao, 0, 2), (a, games, rao, 2, 2)])
    verdict = _board(db, tt).judge(a.id, periods[(2, 2)], periods[(3, 1)])
    assert verdict.status == "warn"
    assert verdict.reason == "Goes against “Try to keep Games out of period 1”"


def test_fixed_periods_are_left_alone(db):  # noqa: F811
    """Setup fixes Games to periods 1 and 2 on Friday: two that day is the plan."""
    school, games, rao, a = _setup(db, 2)
    db.get(School, school.id).fixed_periods = [
        {"subject_id": games.id, "grades": ["Grade 2"], "period": 1, "days": [4]},
        {"subject_id": games.id, "grades": ["Grade 2"], "period": 2, "days": [4]},
    ]
    db.commit()
    tt, _ = _timetable(db, school, [(a, games, rao, 4, 1), (a, games, rao, 4, 2)])
    assert _flags(db, tt) == []


def test_a_teacher_kept_off_some_days_makes_it_a_preference(db):  # noqa: F811
    """"Rao has no periods on Wednesday or Friday": two Games on a day there
    is a preference not met, not a broken rule - the generator only prefers
    one a day for Rao's subjects."""
    school, games, rao, a = _setup(db, 3)
    db.add(Constraint(
        school_id=school.id, type="ir",
        parameters={"form": "count", "scope": [], "selector": {"teachers": ["Rao"], "days": [2, 4]},
                    "relation": "==", "value": 0, "strength": "required"},
        description="Rao has no periods on Wednesday or Friday",
    ))
    db.commit()
    tt, _ = _timetable(db, school, [(a, games, rao, 0, 1), (a, games, rao, 0, 2), (a, games, rao, 1, 1)])
    assert [f["strength"] for f in _flags(db, tt)] == ["preference"]

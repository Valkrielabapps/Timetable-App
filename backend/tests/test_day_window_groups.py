"""A rule grouped by day that also names days applies to those days only.

"9A should have physics on wednesday" came back from the parser grouped per day:
read literally, every day needed a Wednesday Physics lesson, so no timetable
existed - while the English shown to the school read exactly as intended.
"""
from app.models.school import Period
from app.services.constraint_ir import rule_from_dict
from app.services.constraint_ir_checker import Placement, check_rules
from app.services.constraint_ir_compiler import SchoolIndex
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _ir, _require, _school, _subject, _teacher, db  # noqa: F401


def _rule(days, scope=("class_group", "day")):
    return {"form": "count", "scope": list(scope), "selector": {"subjects": ["Physics"], "days": days},
            "relation": ">=", "value": 1}


def test_a_named_day_with_per_day_grouping_is_solvable(db):  # noqa: F811
    school = _school(db, days=3, per_day=2)
    phy = _subject(db, school, "Physics")
    _teacher(db, school, "Das", [phy.id])
    a = _class_group(db, school)
    _require(db, a, phy, 2)
    _ir(db, school, _rule([1]), description="Physics on Tuesday, per day")
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert any(db.get(Period, x["period_id"]).day_of_week == 1 for x in result.assignments)


def test_every_named_day_still_needs_one(db):  # noqa: F811
    """'Physics every Mon and Wed' keeps meaning both days."""
    school = _school(db, days=3, per_day=2)
    phy = _subject(db, school, "Physics")
    _teacher(db, school, "Das", [phy.id])
    a = _class_group(db, school)
    _require(db, a, phy, 2)
    _ir(db, school, _rule([0, 2]), description="Physics on Mon and Wed")
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert {db.get(Period, x["period_id"]).day_of_week for x in result.assignments} == {0, 2}


def test_the_checker_agrees():
    index = SchoolIndex(subject_ids={"Physics": 1}, teacher_ids={}, class_group_ids={},
                        orders_by_day={d: [1, 2] for d in range(3)},
                        first_order_by_day={d: 1 for d in range(3)}, last_order_by_day={d: 2 for d in range(3)})
    tuesday = [Placement(entry_id=1, class_group_id=1, subject_id=1, teacher_id=9, period_id=3, day_of_week=1, order=1),
               Placement(entry_id=2, class_group_id=1, subject_id=1, teacher_id=9, period_id=5, day_of_week=2, order=1)]
    assert check_rules(tuesday, [(None, rule_from_dict(_rule([1])))], index) == []
    monday_only = [Placement(entry_id=1, class_group_id=1, subject_id=1, teacher_id=9, period_id=1, day_of_week=0, order=1)]
    assert len(check_rules(monday_only, [(None, rule_from_dict(_rule([1])))], index)) == 1

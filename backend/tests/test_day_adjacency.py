"""'PE shouldn't be on two days in a row' - adjacency between school days."""
import pytest

from app.models.school import Period
from app.services.constraint_ir import IRError, rule_from_dict
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _ir, _require, _school, _subject, _teacher, db  # noqa: F401

PE_DAYS = {"form": "adjacency", "scope": ["class_group"], "first": {"subjects": ["PE"]},
           "second": {"subjects": ["PE"]}, "unit": "day", "min_gap": 1}


def test_the_same_subject_on_both_sides_is_allowed_for_days_only():
    rule_from_dict(PE_DAYS)
    with pytest.raises(IRError):
        rule_from_dict({**PE_DAYS, "unit": "period"})
    with pytest.raises(IRError):
        rule_from_dict({**PE_DAYS, "scope": ["class_group", "day"]})


def test_pe_never_lands_on_neighbouring_days(db):  # noqa: F811
    school = _school(db, days=5, per_day=2)
    pe = _subject(db, school, "PE")
    eng = _subject(db, school, "English")
    _teacher(db, school, "Biju", [pe.id])
    _teacher(db, school, "Iyer", [eng.id])
    a = _class_group(db, school)
    _require(db, a, pe, 3)  # 3 of 5 days with no two adjacent: only Mon, Wed, Fri
    _require(db, a, eng, 4)
    _ir(db, school, PE_DAYS, description="PE not two days in a row")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert not result.warnings, result.warnings
    days = sorted(db.get(Period, x["period_id"]).day_of_week for x in result.assignments if x["subject_id"] == pe.id)
    assert days == [0, 2, 4], days


def test_four_pe_days_out_of_five_cannot_avoid_neighbours(db):  # noqa: F811
    school = _school(db, days=5, per_day=2)
    pe = _subject(db, school, "PE")
    _teacher(db, school, "Biju", [pe.id])
    a = _class_group(db, school)
    _require(db, a, pe, 4)
    _ir(db, school, {"form": "count", "scope": ["class_group", "day"], "selector": {"subjects": ["PE"]},
                     "relation": "<=", "value": 1}, description="one a day")
    _ir(db, school, PE_DAYS, description="PE not two days in a row")
    assert generate_school_timetable(db, school.id).status == "infeasible"


def test_the_checker_flags_neighbouring_days_and_nothing_else():
    from app.services.constraint_ir_checker import Placement, check_rules
    from app.services.constraint_ir_compiler import SchoolIndex
    index = SchoolIndex(subject_ids={"PE": 1}, teacher_ids={}, class_group_ids={},
                        orders_by_day={d: [1, 2] for d in range(5)},
                        first_order_by_day={d: 1 for d in range(5)}, last_order_by_day={d: 2 for d in range(5)})

    def pe(i, day):
        return Placement(entry_id=i, class_group_id=1, subject_id=1, teacher_id=9, period_id=i,
                         day_of_week=day, order=1)
    rule = rule_from_dict(PE_DAYS)
    assert check_rules([pe(1, 0), pe(2, 2), pe(3, 4)], [(None, rule)], index) == []
    assert len(check_rules([pe(1, 0), pe(2, 1)], [(None, rule)], index)) == 1

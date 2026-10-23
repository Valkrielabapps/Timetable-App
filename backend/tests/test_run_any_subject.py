"""'No section has the same subject more than 2 periods in a row' - a run rule
for every subject, grouped by subject instead of naming them."""
import pytest

from app.models.school import Period
from app.services.constraint_ir import IRError, rule_from_dict
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _ir, _require, _school, _subject, _teacher, db  # noqa: F401

RULE = {"form": "run", "scope": ["class_group", "subject"], "selector": {}, "max_consecutive": 2}


def test_grouped_by_subject_it_needs_no_subject_list():
    rule_from_dict(RULE)


def test_without_grouping_by_subject_an_empty_selector_is_still_refused():
    with pytest.raises(IRError):
        rule_from_dict({**RULE, "scope": ["class_group"]})


def test_no_subject_runs_three_in_a_row(db):  # noqa: F811
    school = _school(db, days=1, per_day=4)
    maths = _subject(db, school, "Maths")
    eng = _subject(db, school, "English")
    _teacher(db, school, "Rao", [maths.id])
    _teacher(db, school, "Iyer", [eng.id])
    a = _class_group(db, school)
    _require(db, a, maths, 3)
    _require(db, a, eng, 1)
    _ir(db, school, RULE, description="No subject more than 2 in a row")

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert not result.warnings, result.warnings
    order = {db.get(Period, x["period_id"]).order: x["subject_id"] for x in result.assignments}
    seq = [order[o] for o in sorted(order)]
    assert all(not (seq[i] == seq[i + 1] == seq[i + 2]) for i in range(len(seq) - 2)), seq
    # Only English in slot 2 or 3 breaks Maths up, so the rule really applied.
    assert seq[1] == eng.id or seq[2] == eng.id

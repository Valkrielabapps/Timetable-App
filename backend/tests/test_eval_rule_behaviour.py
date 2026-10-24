"""The behaviour eval (scripts/eval_rule_behaviour.py) must tell a right
reading from a wrong one - otherwise every OK it prints means nothing."""
import importlib.util
import pathlib

import pytest

from app.services.constraint_ir import rule_from_dict
from app.services.constraint_ir_checker import Placement, check_rules
from app.services.constraint_ir_compiler import SchoolIndex

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "eval_rule_behaviour.py"


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("eval_rule_behaviour", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    db, sid = mod.build_school()
    index, periods = mod._index(db, sid)
    return mod, db, sid, index, periods


def _no_pe_in(orders):
    return rule_from_dict({"form": "count", "scope": [], "selector": {"subjects": ["PE"], "period_orders": orders},
                           "relation": "==", "value": 0})


def test_the_same_reading_is_ok(ev):
    mod, db, sid, index, periods = ev
    assert mod.compare(db, sid, [_no_pe_in([5])], [_no_pe_in([5])], index, periods)[0] == "OK"


def test_the_wrong_period_is_caught(ev):
    """'No PE right after lunch' read as period 4 instead of 5."""
    mod, db, sid, index, periods = ev
    assert mod.compare(db, sid, [_no_pe_in([4])], [_no_pe_in([5])], index, periods)[0] == "DIFFERENT"


def test_a_narrower_reading_is_looser(ev):
    """'No PE in periods 5 and 6' read as only period 5."""
    mod, db, sid, index, periods = ev
    assert mod.compare(db, sid, [_no_pe_in([5])], [_no_pe_in([5, 6])], index, periods)[0] == "LOOSER"


def test_a_day_off_counts_as_a_light_day_for_the_checker():
    """'Every teacher gets a day off': a teacher with nothing on Tuesday keeps it."""
    rule = rule_from_dict({"form": "count", "scope": ["teacher", "day"], "exists_over": ["day"], "selector": {},
                           "relation": "<=", "value": 0})
    index = SchoolIndex(subject_ids={"Maths": 1}, teacher_ids={"Rao": 7}, class_group_ids={},
                        orders_by_day={0: [1, 2], 1: [1, 2]}, first_order_by_day={0: 1, 1: 1},
                        last_order_by_day={0: 2, 1: 2})
    monday_only = [Placement(entry_id=1, class_group_id=1, subject_id=1, teacher_id=7, period_id=1,
                             day_of_week=0, order=1)]
    assert check_rules(monday_only, [(None, rule)], index) == []
    both_days = monday_only + [Placement(entry_id=2, class_group_id=1, subject_id=1, teacher_id=7, period_id=3,
                                         day_of_week=1, order=1)]
    assert len(check_rules(both_days, [(None, rule)], index)) == 1

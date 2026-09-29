"""
Tests for "the first period" and "the last period" as positions.

A period NUMBER is not the same thing. The 8th period is only the last one on
days that have eight, and a school with a half-day Saturday has two different
answers - which is catalogue trap T006, and which a model asked only for
numbers works around by sending -1.

Also covers the relation encoding. The third evaluation run lost 8 rules to
values like '&lt;=' and '<="': the model had read each rule correctly and could
not get the operator characters through intact, so the schema now asks for
words and this keeps the mangled forms working anyway.
"""
import pytest
from ortools.sat.python import cp_model

from app.services.constraint_ir import IRError, rule_from_dict
from app.services.constraint_ir_compiler import Atom, SchoolIndex, compile_rule
from app.services.constraint_ir_english import render
from app.services.llm_ir_parser import _clean, _rule_payload

SUBJECTS = {"Maths": 1}
TEACHERS = {"Rao": 10}
CLASS_GROUPS = {"Grade 8": [100]}

# Monday runs to period 4; Saturday stops at 2. The whole point of positions.
DAY_LENGTHS = {0: 4, 5: 2}
INDEX = SchoolIndex(
    subject_ids=SUBJECTS, teacher_ids=TEACHERS, class_group_ids=CLASS_GROUPS,
    first_order_by_day={day: 1 for day in DAY_LENGTHS},
    last_order_by_day=dict(DAY_LENGTHS),
)


class ShortWeek:
    """One class, one subject, one teacher, over a full day and a half day."""

    def __init__(self):
        self.model = cp_model.CpModel()
        self.penalties: list = []
        self.atoms: list[Atom] = []
        self.by_slot: dict[tuple[int, int], Atom] = {}
        for day, last in DAY_LENGTHS.items():
            for order in range(1, last + 1):
                var = self.model.NewBoolVar(f"x_{day}_{order}")
                atom = Atom(var=var, requirement_id=1, class_group_id=100, subject_id=1,
                            teacher_id=10, period_id=day * 10 + order,
                            day_of_week=day, order=order)
                self.atoms.append(atom)
                self.by_slot[(day, order)] = atom

    def add(self, rule_dict):
        compile_rule(self.model, self.penalties, self.atoms,
                     rule_from_dict(rule_dict), INDEX, "t")

    def allows(self, day, order):
        m = self.model.Clone()
        m.Add(self.by_slot[(day, order)].var == 1)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        return solver.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


# ---------------------------------------------------------------------------
# Positions resolve per day
# ---------------------------------------------------------------------------


def test_last_period_means_each_days_own_last():
    """R021 "Don't give the same teacher the last period every day". Monday's
    last is period 4 and Saturday's is period 2 - a rule written as a number
    would get one of them wrong."""
    b = ShortWeek()
    b.add({"form": "count", "scope": [], "selector": {"period_positions": ["last"]},
           "relation": "==", "value": 0})
    assert not b.allows(0, 4), "Monday's last period should be blocked"
    assert not b.allows(5, 2), "Saturday's last period should be blocked"
    assert b.allows(0, 3), "Monday period 3 is not the last and should be free"
    assert b.allows(5, 1), "Saturday period 1 is not the last and should be free"


def test_a_period_number_is_not_a_position():
    """Period 4 blocks Monday's last and leaves Saturday's alone - the exact
    difference the position exists to express."""
    b = ShortWeek()
    b.add({"form": "count", "scope": [], "selector": {"period_orders": [4]},
           "relation": "==", "value": 0})
    assert not b.allows(0, 4)
    assert b.allows(5, 2), "Saturday's last period is 2, so a rule about 4 misses it"


def test_first_period_resolves_the_same_way():
    b = ShortWeek()
    b.add({"form": "count", "scope": [], "selector": {"period_positions": ["first"]},
           "relation": "==", "value": 0})
    assert not b.allows(0, 1)
    assert not b.allows(5, 1)
    assert b.allows(0, 2)


def test_both_positions_can_be_named_at_once():
    b = ShortWeek()
    b.add({"form": "count", "scope": [],
           "selector": {"period_positions": ["first", "last"]},
           "relation": "==", "value": 0})
    assert not b.allows(0, 1)
    assert not b.allows(0, 4)
    assert b.allows(0, 2)


# ---------------------------------------------------------------------------
# Validation and mapping
# ---------------------------------------------------------------------------


def test_only_first_and_last_are_positions():
    with pytest.raises(IRError, match="'first' or 'last'"):
        rule_from_dict({"form": "count", "scope": [],
                        "selector": {"period_positions": ["middle"]},
                        "relation": "==", "value": 0})


def test_minus_one_is_read_as_the_last_period():
    """A model sending -1 has read "the last period" and guessed at the
    notation. Refusing it loses a rule the model got right."""
    notes: list[str] = []
    rule = rule_from_dict(_clean(_rule_payload({
        "form": "count", "scope": ["teacher"],
        "selector": {"teachers": ["Rao"], "period_orders": [-1]},
        "relation": "at_most", "value": 2, "description": "x"}, notes)))
    assert rule.form.selector.period_positions == ("last",)
    assert rule.form.selector.period_orders is None
    assert any("-1" in n for n in notes)


def test_a_mix_of_numbers_and_minus_one_keeps_both_meanings():
    notes: list[str] = []
    rule = rule_from_dict(_clean(_rule_payload({
        "form": "count", "scope": ["teacher"],
        "selector": {"period_orders": [1, -1]},
        "relation": "at_most", "value": 2, "description": "x"}, notes)))
    assert rule.form.selector.period_orders == (1,)
    assert rule.form.selector.period_positions == ("last",)


def test_the_rendered_sentence_says_of_the_day_not_of_the_week():
    """An admin reading "the last period" needs to know it means each day's
    own - otherwise they will read it as one slot a week."""
    rule = rule_from_dict({"form": "count", "scope": ["teacher"],
                           "selector": {"teachers": ["Rao"], "period_positions": ["last"]},
                           "relation": "<=", "value": 2, "strength": "preference"})
    assert render(rule) == (
        "Where it can be arranged, Rao has at most 2 periods in the last period "
        "of the day."
    )


# ---------------------------------------------------------------------------
# Relations that arrive mangled
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mangled,expected", [
    ("&lt;=", "<="),            # HTML-escaped, seen in run 3
    ('<="', "<="),              # stray quote, seen in run 3
    ('=="', "=="),              # likewise
    ('{"<=":"value"}', "<="),   # a whole object where a string was expected
    ("at_most", "<="),          # what the schema now asks for
    ("<=", "<="),               # and the operator, still accepted
    ("&gt;=", ">="),
])
def test_a_mangled_relation_is_still_understood(mangled, expected):
    """Eight of thirteen invalid rules in run 3 were this. The model had read
    each rule correctly and could not spell the operator, which is the worst
    possible reason to throw a rule away."""
    rule = rule_from_dict(_clean(_rule_payload({
        "form": "count", "scope": ["teacher", "day"],
        "relation": mangled, "value": 6, "description": "x"}, [])))
    assert rule.form.relation == expected


def test_a_relation_that_means_nothing_is_still_refused():
    """Being generous about spelling is not the same as guessing at meaning."""
    with pytest.raises(IRError, match="relation must be one of"):
        rule_from_dict(_clean(_rule_payload({
            "form": "count", "scope": ["teacher"],
            "relation": "roughly", "value": 6, "description": "x"}, [])))

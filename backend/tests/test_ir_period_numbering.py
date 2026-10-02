"""
"Period 5" means the fifth period of the day, whatever the database calls it.

Reported from a real school: "Mrs. Kamini Chandra has no periods in periods 5,
6, 7 or 8" was confirmed, saved, and the generated timetable gave her Monday
period 5 anyway.

Nothing was wrong with the parse. The school's Period rows are numbered from
zero, the timetable grid renders `Period {order + 1}`, and the prompt tells the
model the periods are "numbered 1 to 8" - a count, not the stored values. So
every layer a person sees is 1-based and the stored `order` is 0-based, and the
compiler was matching the model's 1-based answer against raw `order`. The rule
blocked orders 5, 6, 7, which the admin reads as periods 6, 7 and 8, and left
the period they were actually asking about free.

`order` is entered by hand when a school is set up, so it cannot be assumed to
start at zero either. A position is therefore resolved against that day's own
sorted periods: the fifth period is the fifth one there is, whatever it is
called and however many the day has.
"""
import pytest
from ortools.sat.python import cp_model

from app.services.constraint_ir import rule_from_dict
from app.services.constraint_ir_compiler import Atom, SchoolIndex, compile_rule

SUBJECTS = {"Hindi": 1}
TEACHERS = {"Mrs. Kamini Chandra": 10}
CLASS_GROUPS = {"Grade 8": [100]}


def _index(orders_by_day):
    return SchoolIndex(
        subject_ids=SUBJECTS, teacher_ids=TEACHERS, class_group_ids=CLASS_GROUPS,
        orders_by_day=orders_by_day,
        first_order_by_day={d: o[0] for d, o in orders_by_day.items()},
        last_order_by_day={d: o[-1] for d, o in orders_by_day.items()},
    )


class School:
    """One teacher, one day, with the period numbering the school really uses."""

    def __init__(self, orders):
        self.model = cp_model.CpModel()
        self.penalties: list = []
        self.orders = orders
        self.atoms = []
        self.by_order = {}
        for order in orders:
            var = self.model.NewBoolVar(f"x_{order}")
            atom = Atom(var=var, requirement_id=1, class_group_id=100, subject_id=1,
                        teacher_id=10, period_id=order, day_of_week=0, order=order)
            self.atoms.append(atom)
            self.by_order[order] = atom
        self.index = _index({0: list(orders)})

    def add(self, rule_dict):
        compile_rule(self.model, self.penalties, self.atoms,
                     rule_from_dict(rule_dict), self.index, "t")

    def allows(self, order):
        m = self.model.Clone()
        m.Add(self.by_order[order].var == 1)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        return solver.Solve(m) in (cp_model.OPTIMAL, cp_model.FEASIBLE)


KAMINI_AFTER_FOUR = {
    "form": "count", "scope": [],
    "selector": {"teachers": ["Mrs. Kamini Chandra"], "period_orders": [5, 6, 7, 8]},
    "relation": "==", "value": 0,
}


def test_the_reported_bug_a_zero_based_school_blocks_the_right_periods():
    """Periods stored 0-7, displayed 1-8. "Periods 5-8" must block the four the
    admin can see as 5, 6, 7 and 8 - stored 4, 5, 6 and 7."""
    school = School(range(0, 8))
    school.add(KAMINI_AFTER_FOUR)
    assert not school.allows(4), "stored order 4 is displayed Period 5 - this is the bug"
    assert not school.allows(5)
    assert not school.allows(6)
    assert not school.allows(7)


def test_a_zero_based_school_leaves_the_earlier_periods_alone():
    school = School(range(0, 8))
    school.add(KAMINI_AFTER_FOUR)
    for order in (0, 1, 2, 3):
        assert school.allows(order), f"stored order {order} is before Period 5"


def test_the_same_rule_on_a_one_based_school_means_the_same_periods():
    """`order` is typed in by hand at setup, so a school numbering from 1 is
    just as likely. A position has to mean the same thing in both."""
    school = School(range(1, 9))
    school.add(KAMINI_AFTER_FOUR)
    for order in (5, 6, 7, 8):
        assert not school.allows(order)
    for order in (1, 2, 3, 4):
        assert school.allows(order)


def test_a_position_past_the_end_of_a_short_day_matches_nothing():
    """A half-day Saturday has no fifth period. The rule should quietly not
    apply there rather than matching whatever happens to be last."""
    school = School(range(0, 4))  # four periods, displayed 1-4
    school.add(KAMINI_AFTER_FOUR)
    for order in range(0, 4):
        assert school.allows(order), "a 4-period day has no periods 5-8 to block"


def test_gaps_in_the_numbering_do_not_shift_the_positions():
    """Periods deleted and re-added leave holes in `order`. The third period is
    still the third one there is."""
    school = School([0, 1, 5, 6])  # displayed as periods 1, 2, 3, 4
    school.add({"form": "count", "scope": [],
                "selector": {"teachers": ["Mrs. Kamini Chandra"], "period_orders": [3, 4]},
                "relation": "==", "value": 0})
    assert school.allows(0) and school.allows(1)
    assert not school.allows(5), "the third period here is stored as order 5"
    assert not school.allows(6)


def test_first_and_last_still_resolve_per_day():
    """period_positions already worked this way; the two must agree now that
    both resolve against the same table."""
    school = School(range(0, 8))
    school.add({"form": "count", "scope": [],
                "selector": {"teachers": ["Mrs. Kamini Chandra"],
                             "period_positions": ["last"]},
                "relation": "==", "value": 0})
    assert not school.allows(7)
    assert school.allows(6)


@pytest.mark.parametrize("position,expected_order", [(1, 0), (2, 1), (5, 4), (8, 7)])
def test_each_position_maps_to_the_period_the_grid_shows(position, expected_order):
    """The grid renders `Period {order + 1}`, so position N is stored order
    N-1 in a zero-based school. This is the mapping the whole bug came down
    to."""
    school = School(range(0, 8))
    school.add({"form": "count", "scope": [],
                "selector": {"teachers": ["Mrs. Kamini Chandra"],
                             "period_orders": [position]},
                "relation": "==", "value": 0})
    assert not school.allows(expected_order)

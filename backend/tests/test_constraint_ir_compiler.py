"""
Tests for compiling IR rules into CP-SAT constraints.

These build a small model directly rather than going through the solver, so a
rule's effect is visible as "this assignment is possible / impossible" without a
school, a database or a generated timetable in the way.

The shape of every test is the same, and it is the shape that caught the min_gap
off-by-one earlier: set up a board where the rule biting is the difference
between feasible and infeasible. A test with room to spare can pass against a
rule that does nothing, which is the exact failure the IR is meant to end.
"""
import pytest
from ortools.sat.python import cp_model

from app.services.constraint_ir import rule_from_dict
from app.services.constraint_ir_compiler import (
    Atom,
    SchoolIndex,
    UnknownName,
    compile_rule,
    compile_rules,
)

# One school: two classes, three subjects, two teachers, 4 periods x 2 days.
SUBJECTS = {"Maths": 1, "PE": 2, "Art": 3}
TEACHERS = {"Rao": 10, "Khan": 11}
CLASS_GROUPS = {"Grade 8": [100, 101], "Grade 8 - A": [100], "Grade 8 - B": [101]}
INDEX = SchoolIndex(subject_ids=SUBJECTS, teacher_ids=TEACHERS, class_group_ids=CLASS_GROUPS)

DAYS = (0, 1)
ORDERS = (1, 2, 3, 4)


class Board:
    """A model where every (class, subject, teacher, slot) is a free choice.

    Nothing is required to happen, so a rule's whole effect is what it forbids -
    which is what `assert_possible` and `assert_impossible` read.
    """

    def __init__(self, class_ids=(100,), subject_ids=(1,), teacher_ids=(10,)):
        self.model = cp_model.CpModel()
        self.penalties: list = []
        self.atoms: list[Atom] = []
        self.by_key: dict[tuple, Atom] = {}
        req = 0
        for cg in class_ids:
            for subject in subject_ids:
                req += 1
                for teacher in teacher_ids:
                    for day in DAYS:
                        for order in ORDERS:
                            var = self.model.NewBoolVar(f"x_{cg}_{subject}_{teacher}_{day}_{order}")
                            atom = Atom(
                                var=var, requirement_id=req, class_group_id=cg,
                                subject_id=subject, teacher_id=teacher,
                                period_id=day * 10 + order, day_of_week=day, order=order,
                            )
                            self.atoms.append(atom)
                            self.by_key[(cg, subject, teacher, day, order)] = atom

    def add(self, rule_dict, tag="t"):
        compile_rule(self.model, self.penalties, self.atoms,
                     rule_from_dict(rule_dict), INDEX, tag)

    def _solve_with(self, placements):
        for key in placements:
            self.model.Add(self.by_key[key].var == 1)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        return solver.Solve(self.model)

    def assert_possible(self, *placements):
        status = self._solve_with(placements)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), \
            f"expected these to be schedulable together: {placements}"

    def assert_impossible(self, *placements):
        status = self._solve_with(placements)
        assert status == cp_model.INFEASIBLE, \
            f"expected these to clash, but the solver placed them: {placements}"

    def _solve_exactly(self, placements):
        """Pin the whole timetable: these placements and nothing else.

        Needed by any rule the solver could satisfy by ADDING a lesson rather
        than moving one. "All this teacher's periods within a span of 2" is
        broken by lessons in periods 1 and 4 - but only if 2 and 3 stay empty,
        and left free the solver will simply fill them and satisfy the rule.
        The same is true of must_follow, which is happy to schedule a second
        lesson in the period it needs rather than move the one that is there.

        assert_impossible on a partly-free board silently passes for those
        rules whether or not they reached the model.
        """
        wanted = set(placements)
        for key, atom in self.by_key.items():
            self.model.Add(atom.var == (1 if key in wanted else 0))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5
        return solver.Solve(self.model)

    def assert_exactly_possible(self, *placements):
        status = self._solve_exactly(placements)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE), \
            f"expected this exact timetable to be allowed: {placements}"

    def assert_exactly_impossible(self, *placements):
        status = self._solve_exactly(placements)
        assert status == cp_model.INFEASIBLE, \
            f"expected this exact timetable to be refused, but it was allowed: {placements}"


# ---------------------------------------------------------------------------
# count
# ---------------------------------------------------------------------------


def test_count_zero_forbids_the_slot_it_names():
    """R041 "No PE on Fridays", here day 1."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["PE"], "days": [1]}, "relation": "==", "value": 0})
    b.assert_impossible((100, 2, 10, 1, 1))


def test_count_zero_leaves_the_other_days_alone():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["PE"], "days": [1]}, "relation": "==", "value": 0})
    b.assert_possible((100, 2, 10, 0, 1))


def test_count_caps_a_teachers_day_without_touching_the_next():
    """R012 "No teacher should teach more than 6 periods in a day", scaled to a
    4-period day: at most 2 means a third on the same day is impossible, and the
    same three across two days is fine."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 2})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 0, 3))


def test_the_same_load_spread_over_two_days_is_allowed():
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 2})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 1, 1))


def test_a_weekly_cap_counts_across_days():
    """Same rule, scope without `day` - the distinction that made "Priya at most
    28 a week" and "no teacher more than 6 a day" one form."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher"], "relation": "<=", "value": 2})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 1, 1))


def test_scope_separates_teachers_from_each_other():
    b = Board(subject_ids=(1, 2, 3), teacher_ids=(10, 11))
    b.add({"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 1})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 11, 0, 2))


def test_a_grade_label_covers_every_section_in_it():
    """"Grade 8" names both sections; "Grade 8 - A" names one. A rule that
    silently applied to only one section would be a different rule."""
    b = Board(class_ids=(100, 101), subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["PE"], "class_groups": ["Grade 8"]},
           "relation": "==", "value": 0})
    b.assert_impossible((101, 2, 10, 0, 1))


def test_a_section_label_leaves_the_other_section_alone():
    b = Board(class_ids=(100, 101), subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["PE"], "class_groups": ["Grade 8 - A"]},
           "relation": "==", "value": 0})
    b.assert_possible((101, 2, 10, 0, 1))


def test_not_subjects_selects_everything_else():
    """R111 "no more than 3 theory periods in a row" - theory is defined by
    what it isn't, so the negation has to select rather than filter out."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["class_group", "day"],
           "selector": {"not_subjects": ["PE"]}, "relation": "<=", "value": 1})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 3, 10, 0, 2))
    b2 = Board(subject_ids=(1, 2, 3))
    b2.add({"form": "count", "scope": ["class_group", "day"],
            "selector": {"not_subjects": ["PE"]}, "relation": "<=", "value": 1})
    b2.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))


def test_a_require_rule_does_not_apply_to_groups_it_never_mentioned():
    """"Grade 8 - A must have Maths in period 1" must not make Grade 8 - B
    infeasible for having no Maths there. Group membership ignores the time
    filter precisely so this holds."""
    b = Board(class_ids=(100, 101), subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"], "class_groups": ["Grade 8 - A"],
                        "period_orders": [1]}, "relation": ">=", "value": 1})
    b.assert_possible((101, 2, 10, 0, 3))


def test_a_require_rule_still_forces_the_group_it_did_mention():
    b = Board(class_ids=(100,), subject_ids=(1,))
    b.add({"form": "count", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"], "period_orders": [1]},
           "relation": ">=", "value": 1})
    solver = cp_model.CpSolver()
    # Forbid Maths in period 1 on both days; the rule then cannot be met.
    for day in DAYS:
        b.model.Add(b.by_key[(100, 1, 10, day, 1)].var == 0)
    assert solver.Solve(b.model) == cp_model.INFEASIBLE


def test_distinct_counts_kinds_not_periods():
    """R107 "max 6 different subjects a day". Two periods of one subject is one
    subject; two subjects is two - and a plain count cannot tell them apart."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["class_group", "day"],
           "relation": "<=", "value": 1, "distinct": "subject"})
    b.assert_possible((100, 1, 10, 0, 1), (100, 1, 10, 0, 2))
    b2 = Board(subject_ids=(1, 2, 3))
    b2.add({"form": "count", "scope": ["class_group", "day"],
            "relation": "<=", "value": 1, "distinct": "subject"})
    b2.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def test_max_consecutive_forbids_the_run_and_allows_a_gap():
    """R049 "Not more than 2 Maths periods in a row"."""
    b = Board(subject_ids=(1,))
    b.add({"form": "run", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"]}, "max_consecutive": 2})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 1, 10, 0, 2), (100, 1, 10, 0, 3))


def test_max_consecutive_allows_the_same_count_split_by_a_free_period():
    b = Board(subject_ids=(1,))
    b.add({"form": "run", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"]}, "max_consecutive": 2})
    b.assert_possible((100, 1, 10, 0, 1), (100, 1, 10, 0, 2), (100, 1, 10, 0, 4))


def test_max_consecutive_of_one_forbids_a_double():
    """R050 "Never two English periods one after another" - the catalogue trap
    where min_gap would have been reached for instead."""
    b = Board(subject_ids=(1,))
    b.add({"form": "run", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"]}, "max_consecutive": 1})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 1, 10, 0, 2))


def test_a_block_rule_refuses_a_lone_period():
    """R051 "Chemistry practicals need two periods together": one on its own,
    with its neighbours empty, is what the rule exists to prevent."""
    b = Board(subject_ids=(1,))
    b.add({"form": "run", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"]}, "block_size": 2})
    for order in (1, 3):
        b.model.Add(b.by_key[(100, 1, 10, 0, order)].var == 0)
    b.assert_impossible((100, 1, 10, 0, 2))


def test_a_block_rule_accepts_a_pair():
    b = Board(subject_ids=(1,))
    b.add({"form": "run", "scope": ["class_group"],
           "selector": {"subjects": ["Maths"]}, "block_size": 2})
    b.assert_possible((100, 1, 10, 0, 2), (100, 1, 10, 0, 3))


# ---------------------------------------------------------------------------
# adjacency
# ---------------------------------------------------------------------------


def test_directional_adjacency_forbids_one_order_only():
    """R054 "Maths can't come right after PE". The reverse was never asked
    about, and forbidding it too would be a stricter rule the admin didn't
    confirm - the distinction the legacy min_gap collapsed."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["PE"]}, "second": {"subjects": ["Maths"]},
           "directional": True, "min_gap": 1})
    b.assert_impossible((100, 2, 10, 0, 1), (100, 1, 10, 0, 2))


def test_directional_adjacency_permits_the_reverse_order():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["PE"]}, "second": {"subjects": ["Maths"]},
           "directional": True, "min_gap": 1})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))


def test_symmetric_adjacency_forbids_both_orders():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "min_gap": 1})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))
    b2 = Board(subject_ids=(1, 2))
    b2.add({"form": "adjacency", "scope": ["class_group"],
            "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
            "min_gap": 1})
    b2.assert_impossible((100, 2, 10, 0, 1), (100, 1, 10, 0, 2))


def test_min_gap_of_one_still_allows_two_periods_apart():
    """The off-by-one that once made min_gap=1 a complete no-op while the UI
    called it enforced. Periods 1 and 3 are separated by one period, so the
    rule is satisfied - and periods 1 and 2 are not."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "min_gap": 1})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 3))


def test_a_wider_gap_pushes_them_further_apart():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "min_gap": 2})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 3))


def test_adjacency_does_not_reach_across_days():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "min_gap": 1})
    b.assert_possible((100, 1, 10, 0, 4), (100, 2, 10, 1, 1))


def test_must_follow_requires_the_next_period():
    """R055 "Physics practical right after Physics theory" - the positive
    direction, which had no legacy type at all."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "must_follow": True})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))
    b2 = Board(subject_ids=(1, 2))
    b2.add({"form": "adjacency", "scope": ["class_group"],
            "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
            "must_follow": True})
    for day in DAYS:
        for order in ORDERS:
            b2.model.Add(b2.by_key[(100, 2, 10, day, order)].var == 0)
    b2.assert_impossible((100, 1, 10, 0, 1))


# ---------------------------------------------------------------------------
# bucket
# ---------------------------------------------------------------------------


def test_different_days_keeps_two_subjects_apart():
    """R057 "Keep Physics and Chemistry on different days"."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "bucket", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "dimension": "day", "relation": "different"})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


def test_different_days_allows_them_on_separate_days():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "bucket", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "dimension": "day", "relation": "different"})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 1, 1))


def test_same_period_schedules_two_groups_together():
    """R066: electives in parallel. Placing one side forces the other into the
    same slot, which is what makes stream blocks expressible."""
    b = Board(class_ids=(100, 101), subject_ids=(1, 2))
    b.add({"form": "bucket", "scope": [],
           "first": {"subjects": ["Maths"], "class_groups": ["Grade 8 - A"]},
           "second": {"subjects": ["PE"], "class_groups": ["Grade 8 - B"]},
           "dimension": "period", "relation": "same"})
    # 8A has Maths in day 0 period 1, and 8B's PE is barred from that slot.
    b.model.Add(b.by_key[(101, 2, 10, 0, 1)].var == 0)
    b.assert_impossible((100, 1, 10, 0, 1))


def test_same_period_is_satisfied_when_both_land_together():
    b = Board(class_ids=(100, 101), subject_ids=(1, 2))
    b.add({"form": "bucket", "scope": [],
           "first": {"subjects": ["Maths"], "class_groups": ["Grade 8 - A"]},
           "second": {"subjects": ["PE"], "class_groups": ["Grade 8 - B"]},
           "dimension": "period", "relation": "same"})
    b.assert_possible((100, 1, 10, 0, 1), (101, 2, 10, 0, 1))


# ---------------------------------------------------------------------------
# conditional
# ---------------------------------------------------------------------------


def test_a_conditional_bites_only_where_its_condition_holds():
    """R174-shaped: "if Priya has a Grade 12 period that day, at most N that
    day". Subject 3 stands in for the trigger."""
    rule = {
        "form": "conditional", "scope": ["teacher", "day"],
        "when": {"form": "count", "scope": ["teacher", "day"],
                 "selector": {"subjects": ["Art"]}, "relation": ">=", "value": 1},
        "then": {"form": "count", "scope": ["teacher", "day"],
                 "relation": "<=", "value": 2},
    }
    triggered = Board(subject_ids=(1, 2, 3))
    triggered.add(rule)
    triggered.assert_impossible((100, 3, 10, 0, 1), (100, 1, 10, 0, 2), (100, 2, 10, 0, 3))


def test_the_same_load_is_fine_on_a_day_the_condition_misses():
    rule = {
        "form": "conditional", "scope": ["teacher", "day"],
        "when": {"form": "count", "scope": ["teacher", "day"],
                 "selector": {"subjects": ["Art"]}, "relation": ">=", "value": 1},
        "then": {"form": "count", "scope": ["teacher", "day"],
                 "relation": "<=", "value": 2},
    }
    b = Board(subject_ids=(1, 2, 3))
    b.add(rule)
    for order in ORDERS:
        b.model.Add(b.by_key[(100, 3, 10, 0, order)].var == 0)  # no Art that day
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 1, 10, 0, 3))


# ---------------------------------------------------------------------------
# Soft rules and failure reporting
# ---------------------------------------------------------------------------


def test_a_preference_bends_instead_of_breaking():
    """The same rule that is impossible as a requirement stays solvable as a
    preference - relaxed by a penalised slack rather than dropped, so the
    solver still pulls towards it."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 2,
           "strength": "preference"})
    b.model.Minimize(sum(b.penalties))
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 0, 3))


def test_a_rule_naming_a_stranger_is_reported_by_name():
    """A rule that silently matches nothing looks exactly like one being
    honoured. That is the failure the IR exists to remove, so it raises."""
    b = Board()
    with pytest.raises(UnknownName, match="Verma"):
        b.add({"form": "count", "scope": [], "selector": {"teachers": ["Verma"]},
               "relation": "==", "value": 0})


def test_one_bad_rule_does_not_stop_the_others_being_applied():
    """A teacher who left should not stop a school generating a timetable - but
    the rule that went unapplied has to say so."""
    b = Board(subject_ids=(1, 2))
    rules = [
        ("bad", rule_from_dict({"form": "count", "scope": [],
                                "selector": {"teachers": ["Verma"]},
                                "relation": "==", "value": 0,
                                "description": "Verma is off on Mondays"})),
        ("good", rule_from_dict({"form": "count", "scope": ["class_group"],
                                 "selector": {"subjects": ["PE"], "days": [1]},
                                 "relation": "==", "value": 0})),
    ]
    problems = compile_rules(b.model, b.penalties, b.atoms, rules, INDEX)
    assert len(problems) == 1
    assert "Verma" in problems[0]
    assert "Verma is off on Mondays" in problems[0]
    b.assert_impossible((100, 2, 10, 1, 1))  # the good rule still applied

"""
Tests for the forms added after the second evaluation run.

Reading all 35 in-scope rules the parser still declined showed the five
original forms were three axes short, not three rule-families short:

  exists_over   a scope one group has to satisfy rather than all of them
  balance       a statement about groups relative to each other
  span          how stretched a day is, which no count can distinguish
  must_precede  ordering without adjacency

Same shape as the other compiler tests: the board is set up so the rule biting
is the difference between feasible and infeasible, and every "this is allowed"
test has a paired "this is not" so neither can pass against a rule that does
nothing.
"""
from ortools.sat.python import cp_model

from tests.test_constraint_ir_compiler import ORDERS, Board


# ---------------------------------------------------------------------------
# exists_over - satisfied by one group rather than all of them
# ---------------------------------------------------------------------------


def test_exists_over_is_satisfied_by_one_group():
    """R109 "every teacher needs at least one light day, 4 periods or less".
    Scaled to a cap of 1: two lessons on day 0 and one on day 1 leaves day 1
    light, so it passes."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "exists_over": ["day"],
           "relation": "<=", "value": 1})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 1, 1))


def test_without_exists_over_the_same_rule_binds_every_group():
    """The control. If these two behave alike, exists_over does nothing."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 1})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 1, 1))


def test_exists_over_still_fails_when_no_group_satisfies_it():
    """The indicator is reified both ways on purpose. One that could be true
    without the relation holding would let every teacher pass for free, and the
    rule would silently do nothing while reporting itself as enforced."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "count", "scope": ["teacher", "day"], "exists_over": ["day"],
           "relation": "<=", "value": 1})
    # Two lessons on each of the only two days: no light day exists anywhere.
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2),
                        (100, 1, 10, 1, 1), (100, 2, 10, 1, 2))


def test_exists_over_applies_per_outer_group_not_school_wide():
    """One teacher having a light day must not excuse another. The dimensions
    outside exists_over stay universal - that is the shape of the rule."""
    b = Board(subject_ids=(1, 2, 3), teacher_ids=(10, 11))
    b.add({"form": "count", "scope": ["teacher", "day"], "exists_over": ["day"],
           "relation": "<=", "value": 1})
    # Teacher 10 gets a light day; teacher 11 is loaded on both.
    b.assert_impossible((100, 1, 10, 0, 1),
                        (100, 1, 11, 0, 2), (100, 2, 11, 0, 3),
                        (100, 2, 11, 1, 1), (100, 3, 11, 1, 2))


# ---------------------------------------------------------------------------
# distinct over days
# ---------------------------------------------------------------------------


def test_distinct_days_limits_how_many_days_get_used():
    """R018 "try to give part-time teachers all their classes in 3 days".
    Counting days was left out of `distinct` for no reason that survived
    contact with the catalogue."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["teacher"], "distinct": "day",
           "relation": "<=", "value": 1})
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 1, 1))


def test_distinct_days_allows_the_same_lessons_on_one_day():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "count", "scope": ["teacher"], "distinct": "day",
           "relation": "<=", "value": 1})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))


# ---------------------------------------------------------------------------
# balance
# ---------------------------------------------------------------------------


def _empty_day(board, day, subject_ids, teacher_id=10, class_id=100):
    for subject in subject_ids:
        for order in ORDERS:
            board.model.Add(board.by_key[(class_id, subject, teacher_id, day, order)].var == 0)


def test_balance_refuses_a_lopsided_week():
    """R016 "spread Mr. Khan's classes evenly through the week". Three lessons
    on one day and none on the other is a spread of 3."""
    b = Board(subject_ids=(1, 2, 3))
    b.add({"form": "balance", "scope": ["teacher"], "across": ["day"], "max_spread": 1})
    _empty_day(b, 1, (1, 2, 3))
    b.assert_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2), (100, 3, 10, 0, 3))


def test_balance_accepts_an_even_week():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "balance", "scope": ["teacher"], "across": ["day"], "max_spread": 0})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 1, 1))


def test_balance_counts_an_untouched_bucket_as_zero():
    """A teacher who could be given Friday lessons and is given none is exactly
    the imbalance "spread evenly" is about. Iterating only the buckets that
    have atoms would make that case invisible, which is the easy way to write
    this wrongly."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "balance", "scope": ["teacher"], "across": ["day"], "max_spread": 0})
    _empty_day(b, 1, (1, 2))
    b.assert_impossible((100, 1, 10, 0, 1))


def test_balance_treats_each_scope_group_on_its_own():
    """Two teachers, each even in their own right but on different days. A
    balance that pooled them would see an imbalance that nobody has."""
    b = Board(subject_ids=(1, 2), teacher_ids=(10, 11))
    b.add({"form": "balance", "scope": ["teacher"], "across": ["day"], "max_spread": 0})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 1, 1))


# ---------------------------------------------------------------------------
# span
# ---------------------------------------------------------------------------


def test_span_limits_how_far_a_day_stretches():
    """R106 "on the days he comes, all his periods within 4 continuous periods,
    which 4 doesn't matter". Periods 1 and 4 span 4, so a limit of 2 forbids
    it."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_span": 2})
    b.assert_exactly_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


def test_span_allows_a_compact_day():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_span": 2})
    b.assert_exactly_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 2))


def test_max_idle_counts_the_free_periods_in_between():
    """R017 "don't leave teachers with 3 free periods in the middle of the
    day". Periods 1 and 4 leave two idle."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_idle": 1})
    b.assert_exactly_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


def test_max_idle_allows_lessons_with_nothing_between_them():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_idle": 1})
    b.assert_exactly_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 3))


def test_max_idle_ignores_free_periods_outside_the_teaching_day():
    """Periods 3 and 4 leave 1 and 2 free, but those are before the teacher
    arrives - not idle time in the middle. Counting them would make this a
    rule about the whole day, which is a different and much stricter thing."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_idle": 0})
    b.assert_exactly_possible((100, 1, 10, 0, 3), (100, 2, 10, 0, 4))


def test_a_day_with_no_lessons_is_not_constrained_by_a_span():
    """A teacher who is not in has no span. A rule biting here would forbid
    days off, which is the opposite of what these rules are for."""
    b = Board(subject_ids=(1,))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_span": 2})
    b.assert_exactly_possible((100, 1, 10, 0, 1))


def test_span_separates_days_from_each_other():
    """Period 4 on Monday and period 1 on Tuesday are not a span of anything.
    Measuring across days would read from Monday morning to Friday afternoon."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_span": 1})
    b.assert_exactly_possible((100, 1, 10, 0, 4), (100, 2, 10, 1, 1))


# ---------------------------------------------------------------------------
# must_precede - ordering without adjacency
# ---------------------------------------------------------------------------


def test_must_precede_orders_without_forcing_adjacency():
    """R119 "if eng and math are both there that day, english must come before
    maths". must_follow would wrongly force them into neighbouring periods."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "must_precede": True})
    b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


def test_must_precede_forbids_the_wrong_order():
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "must_precede": True})
    b.assert_impossible((100, 2, 10, 0, 1), (100, 1, 10, 0, 4))


def test_must_precede_says_nothing_across_days():
    """"Both there that day" - a Maths on Tuesday does not constrain a PE on
    Monday."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "adjacency", "scope": ["class_group"],
           "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
           "must_precede": True})
    b.assert_possible((100, 2, 10, 0, 1), (100, 1, 10, 1, 1))


def test_must_precede_and_must_follow_are_not_the_same_rule():
    """The distinction the whole field exists for: must_follow demands the very
    next period, must_precede only demands "somewhere later"."""
    strict = Board(subject_ids=(1, 2))
    strict.add({"form": "adjacency", "scope": ["class_group"],
                "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
                "must_follow": True})
    strict.assert_exactly_impossible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))

    loose = Board(subject_ids=(1, 2))
    loose.add({"form": "adjacency", "scope": ["class_group"],
               "first": {"subjects": ["Maths"]}, "second": {"subjects": ["PE"]},
               "must_precede": True})
    loose.assert_exactly_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


# ---------------------------------------------------------------------------
# Soft versions
# ---------------------------------------------------------------------------


def test_the_new_forms_bend_as_preferences_rather_than_breaking():
    """Most rules of these shapes arrive hedged - "spread evenly", "try to
    keep", "as far as possible" - so the soft path matters more here than for
    the counting forms."""
    for rule in (
        {"form": "balance", "scope": ["teacher"], "across": ["day"], "max_spread": 0,
         "strength": "preference"},
        {"form": "span", "scope": ["teacher", "day"], "max_idle": 0,
         "strength": "preference"},
        {"form": "count", "scope": ["teacher", "day"], "exists_over": ["day"],
         "relation": "<=", "value": 0, "strength": "preference"},
    ):
        b = Board(subject_ids=(1, 2, 3))
        b.add(rule)
        b.model.Minimize(sum(b.penalties))
        _empty_day(b, 1, (1, 2, 3))
        b.assert_possible((100, 1, 10, 0, 1), (100, 2, 10, 0, 4))


def test_a_soft_rule_still_costs_something_when_broken():
    """Relaxed, not dropped. A preference with no penalty attached is a
    preference the solver has no reason to honour."""
    b = Board(subject_ids=(1, 2))
    b.add({"form": "span", "scope": ["teacher", "day"], "max_idle": 0,
           "strength": "preference"})
    assert b.penalties, "a soft span rule produced no penalty term"
    b.model.Minimize(sum(b.penalties))
    wanted = {(100, 1, 10, 0, 1), (100, 2, 10, 0, 4)}
    for key, atom in b.by_key.items():
        b.model.Add(atom.var == (1 if key in wanted else 0))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5
    assert solver.Solve(b.model) in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    assert solver.ObjectiveValue() > 0

"""
Tests for break periods.

A break occupies a slot in the day but is never taught in. The two things
worth asserting: nothing gets scheduled into one, and a break interrupts a
teacher's back-to-back run rather than being invisible to it.
"""
from app.services.llm_constraint_parser import _period_summary
from app.services.solver import _runs_by_day


class _P:
    """Stand-in for a Period row - _runs_by_day only reads these three."""

    def __init__(self, day, order, is_break=False):
        self.day_of_week = day
        self.order = order
        self.is_break = is_break

    def __repr__(self):
        return f"P{self.order}{'B' if self.is_break else ''}"


def test_a_break_splits_the_day_into_two_runs():
    day = [_P(0, 1), _P(0, 2), _P(0, 3), _P(0, 4, True), _P(0, 5), _P(0, 6)]
    assert [[p.order for p in run] for run in _runs_by_day(day)] == [[1, 2, 3], [5, 6]]


def test_a_day_without_breaks_is_one_run():
    """The previous behaviour, unchanged."""
    day = [_P(0, o) for o in range(1, 9)]
    assert len(_runs_by_day(day)) == 1


def test_leading_and_trailing_breaks_produce_no_empty_runs():
    day = [_P(0, 1, True), _P(0, 2), _P(0, 3), _P(0, 4, True)]
    runs = _runs_by_day(day)
    assert [[p.order for p in run] for run in runs] == [[2, 3]]
    assert all(run for run in runs)


def test_consecutive_breaks_do_not_produce_an_empty_run():
    day = [_P(0, 1), _P(0, 2, True), _P(0, 3, True), _P(0, 4)]
    assert [[p.order for p in run] for run in _runs_by_day(day)] == [[1], [4]]


def test_a_fully_broken_day_yields_no_runs():
    assert _runs_by_day([_P(0, 1, True), _P(0, 2, True)]) == []


def test_runs_are_per_day():
    periods = [_P(0, 1), _P(0, 2), _P(1, 1), _P(1, 2)]
    assert len(_runs_by_day(periods)) == 2


def test_breaks_reach_the_llm_prompt():
    """"After lunch" can only resolve if the model is told which slot lunch
    is - and that nothing is ever scheduled in it."""
    week = [(d, o, ("Lunch" if o == 4 else None), o == 4) for d in range(5) for o in range(1, 9)]
    summary = _period_summary(week)
    assert "Lunch" in summary
    assert "nothing is scheduled" in summary


def test_an_unlabelled_break_is_still_announced():
    week = [(0, o, None, o == 3) for o in range(1, 6)]
    summary = _period_summary(week)
    assert "Break" in summary

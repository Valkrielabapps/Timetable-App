"""
Tests for the timetable-structure summary sent to the LLM.

Its whole job is to make positional phrasing ("the last period", "period 3")
resolvable, so these assert on what actually lands in the prompt - and on it
staying compact, since a naive version enumerates 40 rows per call.
"""
from app.services.llm_constraint_parser import _grounding_system_prompt, _period_summary


def _week(days=5, per_day=8, label=lambda d, o: f"Period {o}", is_break=lambda d, o: False):
    return [(d, o, label(d, o), is_break(d, o)) for d in range(days) for o in range(1, per_day + 1)]


def test_states_the_period_range_so_first_and_last_resolve():
    summary = _period_summary(_week())
    assert "1 to 8" in summary
    assert '"first period" = 1' in summary
    assert '"last period" = 8' in summary


def test_is_compact_rather_than_one_line_per_period():
    """40 Period rows must not become 40 lines of prompt - that is several
    hundred tokens per parse to say what two sentences say."""
    summary = _period_summary(_week())
    assert len(summary) < 300
    assert summary.count("Period 1") == 0  # generic labels aren't worth listing


def test_named_periods_are_surfaced():
    """A period called "Lunch" is the only way a rule phrased around lunch can
    be resolved, so it has to reach the prompt."""
    week = _week(label=lambda d, o: "Lunch" if o == 4 else f"Period {o}")
    summary = _period_summary(week)
    assert '"Lunch"' in summary


def test_a_label_on_every_day_is_stated_once():
    week = _week(label=lambda d, o: "Lunch" if o == 4 else None)
    assert _period_summary(week).count("Lunch") == 1


def test_a_label_on_some_days_names_those_days():
    week = _week(label=lambda d, o: "Assembly" if (d == 0 and o == 1) else None)
    summary = _period_summary(week)
    assert "Assembly" in summary and "Monday" in summary


def test_irregular_weeks_get_a_per_day_breakdown():
    week = [(0, o, None, False) for o in range(1, 9)] + [(5, o, None, False) for o in range(1, 5)]
    summary = _period_summary(week)
    assert "Monday: 8" in summary and "Saturday: 4" in summary


def test_no_periods_yields_nothing():
    """A school that hasn't set up its timetable yet must not break parsing."""
    assert _period_summary([]) == ""


def test_grounding_prompt_omits_the_section_without_periods():
    """Callers that don't supply periods keep the previous prompt exactly."""
    prompt = _grounding_system_prompt(["Iyer"], ["Math"], ["Grade 8"])
    assert "Teaching days" not in prompt
    assert "Known teachers" in prompt


def test_grounding_prompt_includes_structure_when_given_periods():
    prompt = _grounding_system_prompt(["Iyer"], ["Math"], ["Grade 8"], _week())
    assert "Teaching days" in prompt
    assert "Known teachers" in prompt

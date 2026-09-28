"""
Tests for the IR parser's non-network parts: the prompt it sends and the way a
model's tool call is mapped onto the IR.

No API calls here. The parser's *accuracy* is measured against the whole
catalogue by backend/scripts/eval_constraint_parser.py, which costs money and
so is a script rather than a test. What is worth pinning in CI is the layer
between the two - a tool call that arrives correct and is then mangled on the
way in would look exactly like a model error, and would be chased in the wrong
place.
"""
import pytest

from app.services.constraint_ir import Adjacency, Bucket, Conditional, Count, IRError, Run, rule_from_dict
from app.services.constraint_ir_english import render
from app.services.llm_ir_parser import (
    _EXAMPLES,
    _RULE_TOOL,
    _UNCLEAR_TOOL,
    _clean,
    _rule_payload,
    _system_prompt,
)


def _from_tool_call(**flat):
    """What the router does with a record_rule tool call."""
    return rule_from_dict(_clean(_rule_payload(flat)))


# ---------------------------------------------------------------------------
# Mapping a tool call onto the IR
# ---------------------------------------------------------------------------


def test_nulls_for_unused_fields_do_not_break_a_valid_rule():
    """Models routinely spell out every field, including the ones they aren't
    using. The IR refuses unknown selector keys, so without stripping these a
    correct rule would be rejected as invalid."""
    rule = _from_tool_call(
        form="count", scope=["teacher", "day"],
        selector={"subjects": None, "teachers": ["Rao"], "days": None, "not_subjects": None},
        relation="<=", value=6, distinct=None, min_gap=None, dimension=None,
        description="Rao at most 6 a day",
    )
    assert isinstance(rule.form, Count)
    assert rule.form.selector.teachers == ("Rao",)
    assert rule.form.selector.subjects is None


def test_scope_is_carried_through_exactly():
    """Scope is what separates a daily cap from a weekly one, so a mapping bug
    here silently changes what the admin confirmed into a different rule."""
    daily = _from_tool_call(form="count", scope=["teacher", "day"], relation="<=",
                            value=6, description="x")
    weekly = _from_tool_call(form="count", scope=["teacher"], relation="<=",
                             value=6, description="x")
    assert daily.form.scope == ("teacher", "day")
    assert weekly.form.scope == ("teacher",)
    assert render(daily) != render(weekly)


def test_bucket_relation_is_kept_separate_from_count_relation():
    """Two fields rather than one: "different" and "<=" are both relations and
    a model that saw one field would mix them."""
    rule = _from_tool_call(
        form="bucket", scope=["class_group"],
        first={"subjects": ["Physics"]}, second={"subjects": ["Chemistry"]},
        dimension="day", bucket_relation="different", relation=None, description="x",
    )
    assert isinstance(rule.form, Bucket)
    assert rule.form.relation == "different"


def test_adjacency_defaults_to_a_gap_of_one_when_the_model_omits_it():
    rule = _from_tool_call(
        form="adjacency", scope=["class_group"],
        first={"subjects": ["PE"]}, second={"subjects": ["Maths"]},
        directional=True, min_gap=None, description="x",
    )
    assert isinstance(rule.form, Adjacency)
    assert rule.form.min_gap == 1
    assert rule.form.directional is True


def test_directional_false_is_not_read_as_missing():
    """`directional: false` and an absent field mean the same thing here, and
    both must give a symmetric rule rather than accidentally a directional one."""
    rule = _from_tool_call(
        form="adjacency", scope=["class_group"],
        first={"subjects": ["Maths"]}, second={"subjects": ["Science"]},
        directional=False, description="x",
    )
    assert rule.form.directional is False
    assert "in either order" in render(rule)


def test_a_conditional_nests_both_halves():
    rule = _from_tool_call(
        form="conditional", scope=["teacher", "day"],
        when={"scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"], "class_groups": ["Grade 12"]},
              "relation": ">=", "value": 1},
        then={"form": "count", "scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"]}, "relation": "<=", "value": 5},
        description="x",
    )
    assert isinstance(rule.form, Conditional)
    assert isinstance(rule.form.when, Count)
    assert rule.form.when.selector.class_groups == ("Grade 12",)
    assert isinstance(rule.form.then, Count)
    assert rule.form.then.value == 5


def test_a_conditions_when_defaults_to_a_count():
    """`when` is always a count, so the model isn't asked to repeat `form` on
    it - but the IR still requires one."""
    rule = _from_tool_call(
        form="conditional", scope=["teacher", "day"],
        when={"scope": ["teacher", "day"], "relation": ">=", "value": 7},
        then={"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 5},
        description="x",
    )
    assert isinstance(rule.form.when, Count)


def test_run_carries_whichever_of_the_two_limits_was_given():
    capped = _from_tool_call(form="run", scope=["class_group"],
                             selector={"subjects": ["Maths"]},
                             max_consecutive=2, block_size=None, description="x")
    blocked = _from_tool_call(form="run", scope=["class_group"],
                              selector={"subjects": ["Chemistry"]},
                              max_consecutive=None, block_size=2, description="x")
    assert isinstance(capped.form, Run)
    assert capped.form.max_consecutive == 2 and capped.form.block_size is None
    assert blocked.form.block_size == 2 and blocked.form.max_consecutive is None


def test_strength_defaults_to_required_when_the_model_leaves_it_out():
    assert _from_tool_call(form="count", scope=[], relation="==", value=0,
                           strength=None, description="x").strength == "required"


def test_an_invalid_tool_call_still_fails_validation():
    """The mapping must not paper over a genuinely broken rule - a run with no
    selector caps every lesson in the school back to back."""
    with pytest.raises(IRError):
        _from_tool_call(form="run", scope=["class_group"], max_consecutive=2, description="x")


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------


def test_both_tools_are_offered_so_the_model_can_decline():
    """With only record_rule, a model handed "make the timetable balanced and
    nice for everyone" invents a rule instead of asking. Offering somewhere
    honest to go is what keeps a confident guess out of the timetable."""
    assert _RULE_TOOL["name"] == "record_rule"
    assert _UNCLEAR_TOOL["name"] == "report_unclear"
    assert set(_UNCLEAR_TOOL["input_schema"]["properties"]["reason"]["enum"]) == {
        "ambiguous", "too_vague", "unknown_reference", "not_a_rule", "contradictory"
    }


def test_the_prompt_teaches_the_daily_versus_weekly_distinction():
    """Scope is the field most likely to be got wrong and hardest to notice
    when it is, so both sides of it are shown as worked examples."""
    assert "'day'" in _SCOPE_DESCRIPTION()
    assert "6 periods in a DAY" in _SCOPE_DESCRIPTION()
    # Both sides shown as worked examples, and explicitly contrasted - the
    # difference between them is one word in `scope` and nothing else.
    assert 'scope=["teacher","day"]' in _EXAMPLES
    assert 'scope=["teacher"] selector={teachers:["Priya"]}' in _EXAMPLES
    assert "daily and a weekly cap" in _EXAMPLES


def _SCOPE_DESCRIPTION():
    return _RULE_TOOL["input_schema"]["properties"]["scope"]["description"]


def test_the_prompt_grounds_on_the_schools_own_names():
    prompt = _system_prompt(["Mrs. Rao"], ["Maths"], ["Grade 8"], None)
    assert "Mrs. Rao" in prompt and "Maths" in prompt and "Grade 8" in prompt
    assert "verbatim" in prompt


def test_the_prompt_carries_the_trap_readings():
    """The same school-independent traps the legacy parser was given - reused
    rather than re-written, so the two can't drift apart on how "only comes on
    Monday" is read."""
    prompt = _system_prompt(["Rao"], ["Maths"], ["Grade 8"], None)
    assert "How to read the sentence:" in prompt
    assert "UNAVAILABILITY rule for every" in prompt


def test_the_prompt_stays_affordable():
    """This rides on every parse. A page or two of examples is worth it; a
    catalogue dump is not, and would want retrieval instead."""
    prompt = _system_prompt(
        [f"Teacher {i}" for i in range(40)],
        [f"Subject {i}" for i in range(20)],
        [f"Grade {i}" for i in range(12)],
        [(d, o, None, False) for d in range(5) for o in range(1, 9)],
    )
    assert len(prompt) < 9000

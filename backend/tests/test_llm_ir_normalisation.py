"""
Tests for absorbing what a model actually sends, rather than only what the
schema asks for.

A JSON schema says what is allowed; it does not stop a model sending something
near it. The second evaluation run lost 16 rules to the validator, several of
them verbatim worked examples from the parser's own prompt - the clearest
possible sign that refusing a near-miss is the wrong response to one.

So the IR stays strict and this layer translates. Each test names the wording
it rescues, and asserts on a note being recorded: the value of this is not the
saved rule so much as learning which words the model reaches for, so the schema
can eventually be renamed to match instead of translated forever.
"""
import pytest

from app.services.constraint_ir import Adjacency, Count, IRError, Run, rule_from_dict
from app.services.constraint_ir_english import render
from app.services.llm_ir_parser import _clean, _rule_payload


def _parse(**flat):
    notes: list[str] = []
    rule = rule_from_dict(_clean(_rule_payload(flat, notes)))
    return rule, notes


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


def test_a_week_in_scope_is_dropped_rather_than_refused():
    """There is no "week" dimension - the absence of "day" already means the
    week. A model reaching for it has understood the rule and guessed at the
    vocabulary, so dropping it gives exactly what was meant."""
    rule, notes = _parse(form="count", scope=["teacher", "week"],
                         relation="<=", value=28, description="x")
    assert rule.form.scope == ("teacher",)
    assert render(rule) == "Every teacher has at most 28 periods in the week."
    assert any("week" in n for n in notes)


def test_section_and_grade_are_read_as_class_group():
    for word in ("section", "grade", "class", "classes"):
        rule, notes = _parse(form="count", scope=[word, "day"],
                             relation="<=", value=6, description="x")
        assert rule.form.scope == ("class_group", "day"), word
        assert notes


def test_plural_scope_dimensions_are_singularised():
    rule, _ = _parse(form="count", scope=["teachers", "days"],
                     relation="<=", value=6, description="x")
    assert rule.form.scope == ("teacher", "day")


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


def test_singular_selector_keys_are_renamed():
    rule, notes = _parse(form="count", scope=[],
                         selector={"subject": ["PE"], "day": [4]},
                         relation="==", value=0, description="x")
    assert rule.form.selector.subjects == ("PE",)
    assert rule.form.selector.days == (4,)
    assert len(notes) == 2


def test_period_is_read_as_period_orders():
    rule, _ = _parse(form="count", scope=["class_group"],
                     selector={"grades": ["Grade 10"], "subject": ["Maths"], "period": [1]},
                     relation=">=", value=1, description="x")
    assert rule.form.selector.period_orders == (1,)
    assert rule.form.selector.class_groups == ("Grade 10",)


def test_a_single_name_sent_unwrapped_is_wrapped():
    """One name without brackets is unambiguous. Refusing a rule over a pair of
    brackets is exactly the over-strictness that lost 16 rules."""
    rule, _ = _parse(form="count", scope=[],
                     selector={"teachers": "Mrs. Rao", "days": 5},
                     relation="==", value=0, description="x")
    assert rule.form.selector.teachers == ("Mrs. Rao",)
    assert rule.form.selector.days == (5,)


def test_the_nulls_a_model_pads_with_are_dropped():
    rule, _ = _parse(form="count", scope=["teacher", "day"],
                     selector={"subjects": None, "teachers": ["Rao"], "days": [],
                               "not_subjects": ""},
                     relation="<=", value=6, description="x")
    assert rule.form.selector.teachers == ("Rao",)
    assert rule.form.selector.subjects is None


# ---------------------------------------------------------------------------
# Relations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("word,expected", [
    ("at_most", "<="), ("max", "<="), ("no_more_than", "<="),
    ("at_least", ">="), ("minimum", ">="),
    ("exactly", "=="), ("equals", "=="),
])
def test_a_relation_written_as_a_word_is_read_as_the_operator(word, expected):
    rule, notes = _parse(form="count", scope=["teacher", "day"],
                         relation=word, value=6, description="x")
    assert rule.form.relation == expected
    assert notes


def test_a_bucket_relation_naming_its_dimension_is_understood():
    rule, notes = _parse(form="bucket", scope=["class_group"],
                         first={"subjects": ["Physics"]}, second={"subjects": ["Chemistry"]},
                         dimension="day", bucket_relation="different_day", description="x")
    assert rule.form.relation == "different"
    assert notes


# ---------------------------------------------------------------------------
# Fields the model reaches for with the wrong meaning
# ---------------------------------------------------------------------------


def test_a_block_of_one_is_read_as_forbidding_doubles():
    """block_size=1 is not a block, it is the opposite of one. A model sending
    it has read "no double English" and reached for the wrong field; the IR
    would refuse it outright."""
    rule, notes = _parse(form="run", scope=["class_group"],
                         selector={"subjects": ["English"]}, block_size=1, description="x")
    assert isinstance(rule.form, Run)
    assert rule.form.max_consecutive == 1 and rule.form.block_size is None
    assert "no two English periods are back to back" in render(rule)
    assert any("block" in n for n in notes)


def test_a_gap_of_zero_is_read_as_ordering():
    """A gap of zero forbids nothing, so nobody means it literally. It comes
    from reading "A must come before B" - ordering rather than distance."""
    rule, notes = _parse(form="adjacency", scope=["class_group"],
                         first={"subjects": ["English"]}, second={"subjects": ["Maths"]},
                         min_gap=0, directional=True, description="x")
    assert isinstance(rule.form, Adjacency)
    assert rule.form.must_precede is True
    assert "earlier in the day" in render(rule)
    assert any("min_gap" in n for n in notes)


def test_an_explicit_must_precede_is_left_alone():
    rule, notes = _parse(form="adjacency", scope=["class_group"],
                         first={"subjects": ["English"]}, second={"subjects": ["Maths"]},
                         must_precede=True, description="x")
    assert rule.form.must_precede is True
    assert not notes


# ---------------------------------------------------------------------------
# What must still be refused
# ---------------------------------------------------------------------------


def test_normalising_does_not_make_a_meaningless_rule_valid():
    """Being generous about wording is not the same as guessing at meaning. A
    run with no selector still caps every lesson in the school back to back."""
    with pytest.raises(IRError):
        _parse(form="run", scope=["class_group"], max_consecutive=2, description="x")


def test_a_genuinely_unknown_scope_dimension_is_still_refused():
    """"room" is not a near-miss for anything - it is a capability that does
    not exist, and silently dropping it would apply a much wider rule than was
    asked for."""
    with pytest.raises(IRError, match="scope cannot group by"):
        _parse(form="count", scope=["room"], relation="<=", value=3, description="x")


def test_exists_over_cannot_swallow_the_whole_scope():
    """Every dimension existential means "somewhere in the school this holds
    once", which no rule means and almost any timetable satisfies."""
    with pytest.raises(IRError, match="cannot cover the whole scope"):
        _parse(form="count", scope=["day"], exists_over=["day"],
               relation="<=", value=4, description="x")


def test_the_ir_itself_refuses_exists_over_outside_scope():
    """Checked against rule_from_dict directly: the stored shape has to stay
    coherent whatever the mapping layer accepts on the way in."""
    with pytest.raises(IRError, match="only name dimensions that are in scope"):
        rule_from_dict({"form": "count", "scope": ["teacher"], "exists_over": ["day"],
                        "relation": "<=", "value": 4})


def test_a_dimension_named_only_in_exists_over_is_added_to_scope():
    """R124 arrived this way. Naming a dimension as existential while leaving
    it out of scope says the rule is grouped by it - that is what "at least one
    day" means - so repairing it keeps a rule the model read correctly."""
    rule, notes = _parse(form="count", scope=["teacher"], exists_over=["day"],
                         relation="at_most", value=4, description="x")
    assert rule.form.scope == ("teacher", "day")
    assert rule.form.exists_over == ("day",)
    assert any("exists_over" in n for n in notes)


def test_a_balance_cannot_even_out_what_it_also_groups_by():
    with pytest.raises(IRError, match="remove it from one of scope or across"):
        _parse(form="balance", scope=["teacher", "day"], across=["day"],
               max_spread=1, description="x")


def test_a_span_has_to_be_measured_within_a_day():
    """A span across days would measure from Monday's first period to Friday's
    last, which is not a thing anyone limits."""
    with pytest.raises(IRError, match="scope must include 'day'"):
        _parse(form="span", scope=["teacher"], max_span=4, description="x")


def test_a_rule_cannot_both_demand_the_next_period_and_only_a_later_one():
    with pytest.raises(IRError, match="pick one"):
        _parse(form="adjacency", scope=["class_group"],
               first={"subjects": ["A"]}, second={"subjects": ["B"]},
               must_follow=True, must_precede=True, description="x")


# ---------------------------------------------------------------------------
# The new forms survive the flat tool shape
# ---------------------------------------------------------------------------


def test_balance_maps_from_the_flat_tool_call():
    rule, _ = _parse(form="balance", scope=["teacher"], across=["day"],
                     selector={"teachers": ["Mr. Khan"]}, max_spread=1,
                     strength="preference", description="x")
    assert rule.form.across == ("day",)
    assert rule.form.max_spread == 1
    assert "spread across the days of the week" in render(rule)


def test_span_maps_from_the_flat_tool_call():
    rule, _ = _parse(form="span", scope=["teacher", "day"], max_idle=2,
                     strength="preference", description="x")
    assert rule.form.max_idle == 2 and rule.form.max_span is None
    assert "free periods between the first and the last" in render(rule)


def test_exists_over_maps_from_the_flat_tool_call():
    rule, _ = _parse(form="count", scope=["teacher", "day"], exists_over=["day"],
                     selector={"days": [0, 1, 2, 3, 4]}, relation="<=", value=4,
                     strength="preference", description="x")
    assert isinstance(rule.form, Count)
    assert rule.form.exists_over == ("day",)
    assert "at least one day" in render(rule)

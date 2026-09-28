"""
Tests for the constraint IR: what it accepts, what it refuses, and what it says.

The rendering tests matter more than they look. Once rules go through the IR the
parser nearly always produces something well-formed, so the "doesn't fit a type"
signal that used to make a misreading visible is gone, and the rendered sentence
is the only thing left between a misread rule and a wrong timetable. A filter
that silently fails to appear in the English is therefore a real defect, not a
cosmetic one - which is why several tests here assert on the presence of a
clause rather than on whole sentences.

Encodings are taken from docs/research/constraint-catalogue.tsv and cited by id,
so a change to a form can be checked against the rule it was built for.
"""
import pytest

from app.services.constraint_ir import (
    Count,
    IRError,
    Rule,
    referenced_names,
    rule_from_dict,
    rule_to_dict,
)
from app.services.constraint_ir_english import render


def _r(**form):
    return rule_from_dict(form)


def _english(**form):
    return render(rule_from_dict(form))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_form_is_refused_by_name():
    with pytest.raises(IRError, match="unknown form"):
        _r(form="placement", scope=[], relation="==", value=0)


def test_placement_is_a_count_of_zero_not_its_own_form():
    """The catalogue's bans and requirements are counts, which is why there is
    no placement form. R041 "No PE on Fridays" is == 0."""
    rule = _r(form="count", scope=["class_group"],
              selector={"subjects": ["PE"], "days": [4]}, relation="==", value=0)
    assert isinstance(rule.form, Count)
    assert rule.form.value == 0


def test_scope_cannot_group_by_something_that_is_not_a_dimension():
    with pytest.raises(IRError, match="scope cannot group by"):
        _r(form="count", scope=["room"], relation="<=", value=3)


def test_unknown_selector_field_is_refused_rather_than_ignored():
    """A model inventing `rooms` must fail loudly. Dropping the field would
    apply a wider rule than was asked for, with nothing to show for it."""
    with pytest.raises(IRError, match="unknown field"):
        _r(form="count", scope=[], selector={"rooms": ["Lab 1"]}, relation="==", value=0)


def test_a_selector_cannot_include_and_exclude_the_same_subject():
    with pytest.raises(IRError, match="both includes and excludes"):
        _r(form="count", scope=[], selector={"subjects": ["PE"], "not_subjects": ["PE"]},
           relation="==", value=0)


def test_days_outside_the_week_are_refused():
    with pytest.raises(IRError, match="outside the allowed range"):
        _r(form="count", scope=[], selector={"days": [9]}, relation="==", value=0)


def test_a_clock_time_answered_as_a_period_is_caught():
    """A model answering "12:30" as period 1230 would otherwise match nothing
    and silently become a rule with no effect."""
    with pytest.raises(IRError, match="outside the allowed range"):
        _r(form="count", scope=[], selector={"period_orders": [1230]}, relation="==", value=0)


def test_a_run_needs_to_say_which_lessons_form_the_run():
    """Without a selector this caps every lesson of every kind back to back,
    which no rule means and which would make most timetables infeasible."""
    with pytest.raises(IRError, match="needs a selector"):
        _r(form="run", scope=["class_group"], max_consecutive=2)


def test_a_block_cannot_be_larger_than_the_run_that_contains_it():
    with pytest.raises(IRError, match="cannot fit under"):
        _r(form="run", scope=["class_group"], selector={"subjects": ["Chemistry"]},
           block_size=3, max_consecutive=2)


def test_adjacency_needs_both_sides_named():
    with pytest.raises(IRError, match="both sides"):
        _r(form="adjacency", scope=["class_group"], first={"subjects": ["PE"]}, second={})


def test_conditionals_do_not_nest():
    """Representable, but nothing in the catalogue needs one and the echo-back
    stops being readable - which is the only defence against a misreading."""
    inner = {"form": "conditional", "scope": [],
             "when": {"form": "count", "scope": [], "relation": ">=", "value": 1},
             "then": {"form": "count", "scope": [], "relation": "<=", "value": 2}}
    with pytest.raises(IRError, match="cannot contain another conditional"):
        _r(form="conditional", scope=[],
           when={"form": "count", "scope": [], "relation": ">=", "value": 1}, then=inner)


def test_strength_defaults_to_required():
    """A rule nobody hedged is a rule. The catalogue's PREFERENCE rows all
    carry hedging language; a flat statement is a requirement."""
    assert _r(form="count", scope=[], relation="<=", value=5).strength == "required"


def test_round_trips_through_its_stored_shape():
    """Constraint.parameters holds this dict, so a rule that cannot survive the
    trip would change meaning between being confirmed and being solved."""
    original = {
        "form": "adjacency", "scope": ["class_group"],
        "first": {"subjects": ["PE"]}, "second": {"subjects": ["Maths"]},
        "min_gap": 2, "directional": True, "must_follow": False,
        "strength": "preference",
    }
    once = rule_from_dict(original)
    twice = rule_from_dict(rule_to_dict(once))
    assert once.form == twice.form
    assert once.strength == twice.strength


def test_referenced_names_reaches_into_both_sides_and_conditionals():
    """These are checked against the school before a rule is saved, so a name
    missed here is a rule that silently matches nothing at solve time."""
    rule = _r(
        form="conditional", scope=["teacher", "day"],
        when={"form": "count", "scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"], "class_groups": ["Grade 12"]},
              "relation": ">=", "value": 1},
        then={"form": "adjacency", "scope": ["class_group"],
              "first": {"subjects": ["PE"]}, "second": {"not_subjects": ["Art"]}},
    )
    found = referenced_names(rule)
    assert found["teacher"] == {"Priya"}
    assert found["class_group"] == {"Grade 12"}
    assert found["subject"] == {"PE", "Art"}


# ---------------------------------------------------------------------------
# Rendering - the echo-back
# ---------------------------------------------------------------------------


def test_r012_teacher_daily_cap():
    """"No teacher should teach more than 6 periods in a day" - the shape with
    no type of its own today, and 15 catalogue rules behind it."""
    assert _english(form="count", scope=["teacher", "day"], relation="<=", value=6) == (
        "Every teacher has at most 6 periods on any day."
    )


def test_r001_whole_day_off():
    assert _english(form="count", scope=[],
                    selector={"teachers": ["Mrs. Rao"], "days": [5]},
                    relation="==", value=0) == "Mrs. Rao has no periods on Saturday."


def test_r041_a_universal_ban_reads_as_a_ban():
    """"Every class has no PE periods" is grammatical and unreadable; the
    negative belongs on the subject."""
    assert _english(form="count", scope=["class_group"],
                    selector={"subjects": ["PE"], "days": [4]},
                    relation="==", value=0) == "No class has PE periods on Friday."


def test_r003_a_period_scoped_block_says_both_the_period_and_the_day():
    assert _english(form="count", scope=[],
                    selector={"teachers": ["Mr. Khan"], "days": [1], "period_orders": [1]},
                    relation="==", value=0) == "Mr. Khan has no periods in period 1 on Tuesday."


def test_a_scope_subject_is_not_also_repeated_as_a_possessive():
    """R066: "For Grade 11, Grade 11's Biology periods and Grade 11's Computer
    Science periods" reads as two different groups."""
    sentence = _english(
        form="bucket", scope=[],
        first={"subjects": ["Biology"], "class_groups": ["Grade 11"]},
        second={"subjects": ["Computer Science"], "class_groups": ["Grade 11"]},
        dimension="period", relation="same",
    )
    assert sentence == (
        "For Grade 11, Biology periods and Computer Science periods are "
        "scheduled at the same time."
    )


def test_a_filter_the_scope_did_not_consume_still_appears():
    """R172. The scope groups by teacher, so "Priya" is the subject - but the
    condition is about her Grade 12 periods specifically, and a sentence that
    drops "Grade 12" describes a different and much wider rule."""
    sentence = _english(
        form="conditional", scope=["teacher", "day"],
        when={"form": "count", "scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"], "class_groups": ["Grade 12"]},
              "relation": ">=", "value": 1},
        then={"form": "count", "scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"]}, "relation": "<=", "value": 5},
        strength="preference",
    )
    assert "Grade 12" in sentence
    assert sentence == (
        "Where it can be arranged, wherever Priya has at least 1 Grade 12 period "
        "on any day, Priya has at most 5 periods."
    )


def test_directional_and_symmetric_adjacency_do_not_read_alike():
    """The distinction the legacy types got wrong often enough to need its own
    field. "Maths can't follow PE" forbids one order; "not next to each other"
    forbids both, and confirming the wrong one is invisible in the timetable."""
    directional = _english(form="adjacency", scope=["class_group"],
                           first={"subjects": ["PE"]}, second={"subjects": ["Maths"]},
                           directional=True)
    symmetric = _english(form="adjacency", scope=["class_group"],
                         first={"subjects": ["Maths"]}, second={"subjects": ["Science"]})
    assert directional == (
        "For every class, Maths periods never come in the period straight after "
        "PE periods."
    )
    assert "in either order" in symmetric
    assert directional != symmetric


def test_a_required_block_and_a_capped_run_do_not_read_alike():
    block = _english(form="run", scope=["class_group"],
                     selector={"subjects": ["Chemistry"]}, block_size=2)
    capped = _english(form="run", scope=["class_group"],
                      selector={"subjects": ["Chemistry"]}, max_consecutive=2)
    assert "blocks of 2 consecutive periods" in block
    assert "no more than 2" in capped
    assert block != capped


def test_negated_subjects_are_spelled_out():
    """R111: "no more than 3 theory periods in a row" only means anything if
    the admin can see which subjects count as theory."""
    sentence = _english(form="run", scope=["class_group"],
                        selector={"not_subjects": ["PE", "Art", "Music", "Library"],
                                  "class_groups": ["Grade 10"]},
                        max_consecutive=3, strength="preference")
    assert "periods other than PE, Art, Music or Library" in sentence
    assert "Grade 10" in sentence


def test_strength_is_said_in_words_not_left_to_a_badge():
    """An admin confirming a rule has to see that it can be broken. A
    preference silently treated as a requirement is exactly the misreading this
    sentence exists to catch."""
    hard = _english(form="count", scope=["class_group"],
                    selector={"subjects": ["PE"], "days": [4]}, relation="==", value=0)
    soft = _english(form="count", scope=["class_group"],
                    selector={"subjects": ["PE"], "days": [4]}, relation="==", value=0,
                    strength="preference")
    assert not hard.startswith("Where it can be arranged")
    assert soft.startswith("Where it can be arranged")


def test_distinct_counts_read_as_counts_of_kinds():
    """R107: "max 6 different subjects a day" counts kinds, not periods, and
    the two must not render alike."""
    distinct = _english(form="count", scope=["class_group", "day"],
                        selector={"class_groups": ["Grade 6"]},
                        relation="<=", value=6, distinct="subject")
    plain = _english(form="count", scope=["class_group", "day"],
                     selector={"class_groups": ["Grade 6"]}, relation="<=", value=6)
    assert distinct == "Grade 6 has at most 6 different subjects on any day."
    assert plain == "Grade 6 has at most 6 periods on any day."


def test_every_rendered_sentence_is_a_sentence():
    """Whatever the combination, the admin gets something capitalised and
    terminated - never a fragment, and never an empty string they would
    confirm without reading."""
    forms = [
        {"form": "count", "scope": [], "relation": "==", "value": 0},
        {"form": "count", "scope": ["teacher", "day"], "relation": "<=", "value": 6},
        {"form": "run", "scope": ["class_group"], "selector": {"subjects": ["X"]},
         "max_consecutive": 1},
        {"form": "adjacency", "scope": [], "first": {"subjects": ["A"]},
         "second": {"subjects": ["B"]}, "min_gap": 3},
        {"form": "bucket", "scope": [], "first": {"subjects": ["A"]},
         "second": {"subjects": ["B"]}, "dimension": "day", "relation": "different"},
    ]
    for f in forms:
        sentence = render(rule_from_dict(f))
        assert sentence and sentence[0].isupper() and sentence.endswith(".")


def test_two_different_rules_never_render_the_same_way():
    """The property the whole echo-back rests on. If a confirmed sentence maps
    to more than one rule, confirming it proves nothing."""
    variants = [
        {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
         "relation": "<=", "value": 2},
        {"form": "count", "scope": ["class_group", "day"], "selector": {"subjects": ["Maths"]},
         "relation": "<=", "value": 2},
        {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
         "relation": ">=", "value": 2},
        {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
         "relation": "==", "value": 2},
        {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "days": [0]},
         "relation": "<=", "value": 2},
        {"form": "count", "scope": ["teacher"], "selector": {"subjects": ["Maths"]},
         "relation": "<=", "value": 2},
        {"form": "run", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
         "max_consecutive": 2},
        {"form": "run", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
         "block_size": 2},
    ]
    rendered = [render(rule_from_dict(v)) for v in variants]
    assert len(set(rendered)) == len(rendered), [s for s in rendered]


def test_a_rule_with_no_description_still_renders():
    """description is what the admin confirmed, but it is filled in *from* this
    renderer, so rendering cannot depend on it."""
    assert render(Rule(form=rule_from_dict(
        {"form": "count", "scope": [], "relation": "==", "value": 0}).form))

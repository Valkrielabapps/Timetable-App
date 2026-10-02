"""
Tests for the misreadings found by reading the fifth evaluation run's sentences.

Four runs measured whether a rule came out. The fifth was the first to ask
whether it was the RIGHT rule, by rendering each one back into English and
reading it against what was typed. About a third of the valid rules were wrong -
and the valuable part is that nearly every one of them was *visibly* wrong in
the rendered sentence, which is the echo-back doing its job.

Two causes were worth fixing in code rather than only in the prompt:

  - Both sides of a two-sided form collapsing onto the same lessons, which is
    never a rule anyone means.
  - The renderer dropping filters, so a correct rule read as a much wider one.
    The second is the more dangerous: a reader rejecting a good rule, or
    accepting a sentence that does not describe what was stored.
"""
import pytest

from app.services.constraint_ir import IRError, rule_from_dict
from app.services.constraint_ir_english import render


def _say(**form):
    return render(rule_from_dict(form))


# ---------------------------------------------------------------------------
# Two-sided forms need two different sides
# ---------------------------------------------------------------------------


def test_an_adjacency_against_itself_is_refused():
    """R046 "PE shouldn't be on two days in a row" came back as PE against PE,
    rendering as "PE periods and PE periods are never back to back" - nonsense,
    and about positions in a day rather than which days are adjacent."""
    with pytest.raises(IRError, match="DIFFERENT lessons"):
        rule_from_dict({"form": "adjacency", "scope": ["class_group"],
                        "first": {"subjects": ["PE"]}, "second": {"subjects": ["PE"]}})


def test_a_bucket_against_itself_is_refused():
    """R065 "8A and 8B have PE together" named 8A on both sides."""
    with pytest.raises(IRError, match="DIFFERENT lessons"):
        rule_from_dict({"form": "bucket", "scope": [],
                        "first": {"subjects": ["PE"], "class_groups": ["Grade 8 - A"]},
                        "second": {"subjects": ["PE"], "class_groups": ["Grade 8 - A"]},
                        "dimension": "period", "relation": "same"})


def test_the_same_rule_written_properly_is_accepted():
    """The sides differ by section, which is the entire content of the rule."""
    sentence = _say(form="bucket", scope=[],
                    first={"subjects": ["PE"], "class_groups": ["Grade 8 - A"]},
                    second={"subjects": ["PE"], "class_groups": ["Grade 8 - B"]},
                    dimension="period", relation="same")
    assert sentence == (
        "Grade 8 - A PE periods and Grade 8 - B PE periods are scheduled at the "
        "same time."
    )


def test_the_error_says_what_to_reach_for_instead():
    """A refusal that only says no sends the model round the same loop."""
    with pytest.raises(IRError, match="run rule"):
        rule_from_dict({"form": "adjacency", "scope": ["class_group"],
                        "first": {"subjects": ["PE"]}, "second": {"subjects": ["PE"]}})


# ---------------------------------------------------------------------------
# The renderer must not drop what distinguishes the two sides
# ---------------------------------------------------------------------------


def test_a_side_that_differs_is_named_even_when_the_scope_used_that_field():
    """The skip set is computed from `first`; applying it to `second` as well
    hid 8B, so a correct rule rendered exactly like the broken one above. Two
    different rules reading the same way is the one thing the echo-back cannot
    survive."""
    sentence = _say(form="bucket", scope=[],
                    first={"subjects": ["PE"], "class_groups": ["Grade 8 - A"]},
                    second={"subjects": ["PE"], "class_groups": ["Grade 8 - B"]},
                    dimension="period", relation="same")
    assert "Grade 8 - A" in sentence and "Grade 8 - B" in sentence


def test_a_field_both_sides_share_is_not_repeated():
    """Shared fields belong to the sentence's subject, not to each side."""
    sentence = _say(form="bucket", scope=[],
                    first={"subjects": ["Biology"], "class_groups": ["Grade 11"]},
                    second={"subjects": ["Computer Science"], "class_groups": ["Grade 11"]},
                    dimension="period", relation="same")
    assert sentence.count("Grade 11") == 1
    assert sentence == (
        "For Grade 11, Biology periods and Computer Science periods are "
        "scheduled at the same time."
    )


# ---------------------------------------------------------------------------
# A distinct count has to say what it is counting over
# ---------------------------------------------------------------------------


def test_a_distinct_count_names_the_lessons_it_counts_across():
    """R025 "the same teacher should take Science for all of Grade 9" rendered
    as "Grade 9 has at most 1 different teacher" - which is a rule about the
    whole of Grade 9's timetable, not about its Science. Correct rule, wrong
    sentence, and a reader would rightly reject it."""
    sentence = _say(form="count", scope=[],
                    selector={"subjects": ["Science"], "class_groups": ["Grade 9"]},
                    distinct="teacher", relation="<=", value=1)
    assert "Science" in sentence
    assert sentence == (
        "Grade 9 has at most 1 different teacher across its Science periods in "
        "the week."
    )


def test_a_distinct_count_over_everything_does_not_pad_the_sentence():
    """With no narrowing, "across its periods" says nothing - the count is
    already over everything."""
    sentence = _say(form="count", scope=["class_group", "day"],
                    selector={"class_groups": ["Grade 6"]},
                    distinct="subject", relation="<=", value=6)
    assert sentence == "Grade 6 has at most 6 different subjects on any day."


def test_distinct_period_order_keeps_its_subject():
    """R038 "Grade 1 should have English in the same period every day"."""
    sentence = _say(form="count", scope=["class_group"],
                    selector={"subjects": ["English"], "class_groups": ["Grade 1"]},
                    distinct="period_order", relation="<=", value=1,
                    strength="preference")
    assert "English" in sentence


# ---------------------------------------------------------------------------
# The sentences the run got wrong, written correctly
# ---------------------------------------------------------------------------


def test_a_morning_preference_reads_as_the_afternoon_being_empty():
    """R007 "Mrs. Rao would like her classes in the morning if possible" came
    back as a span rule about 4 consecutive periods - unrelated. There is no
    "morning" field; the timetable structure says where lunch falls, so it is
    the periods after it being empty."""
    sentence = _say(form="count", scope=[],
                    selector={"teachers": ["Mrs. Rao"], "period_orders": [6, 7, 8]},
                    relation="==", value=0, strength="preference")
    assert sentence == (
        "Where it can be arranged, Mrs. Rao has no periods in periods 6, 7 or 8."
    )


def test_an_exception_reads_as_the_classes_it_applies_to():
    """R090 "No PE in the first period, except for Grade 12" - the run got this
    right by listing the other grades, and the sentence has to show that list
    or the exception is invisible."""
    grades = [f"Grade {g}" for g in range(1, 12)]
    sentence = _say(form="count", scope=["class_group"],
                    selector={"subjects": ["PE"], "class_groups": grades,
                              "period_positions": ["first"]},
                    relation="==", value=0)
    assert "Grade 11" in sentence
    assert "Grade 12" not in sentence

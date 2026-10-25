"""Example retrieval and reading aids for the rule parser."""
import json
import pathlib

from app.services import llm_ir_parser as P
from app.services.rule_text_hints import sentence_hints

TEACHERS = ["Mrs. Rao", "Mr. Menon", "Mr. Iyer", "Ms. Das", "Mr. Khan", "Coach Biju", "Ms. Mary"]
SUBJECTS = ["English", "Maths", "Science", "Hindi", "Social Studies", "PE", "Art", "Physics", "Chemistry",
            "Computer", "Computer Science"]
LABELS = ["Grade 6", "Grade 9", "Grade 6 - A", "Grade 6 - B", "Grade 9 - A"]


def hints(text):
    return sentence_hints(text, TEACHERS, SUBJECTS, LABELS)


# --- reading aids ----------------------------------------------------------

def test_nicknames_become_the_schools_names():
    assert "'rao maam' = Mrs. Rao" in hints("rao maam is off on fridays")
    assert "'khan sir' = Mr. Khan" in hints("khan sir doesnt come on tuesdays")
    assert "'biju sir' = Coach Biju" in hints("biju sir only after lunch")


def test_a_short_name_needs_a_title_next_to_it():
    """'das' alone could be anything; 'das miss' is Ms. Das."""
    assert "'das miss' = Ms. Das" in hints("das miss cant take 1st period")
    assert not any("Ms. Das" in h for h in hints("das is a word"))


def test_class_references():
    assert "'6th std' = Grade 6" in hints("hindi atleast once on monday for 6th std")
    assert "'9a' = Grade 9 - A" in hints("9A should have physics on wednesday")
    assert "'class vi' = Grade 6" in hints("class VI no art on friday")


def test_a_period_number_is_not_a_class():
    assert hints("no maths in the 6th period") == []
    assert hints("max 6 periods a day") == []


def test_subject_aliases_and_ambiguity():
    assert "'pt' = PE" in hints("pt shouldnt be after lunch")
    assert "'games' = PE" in hints("no games in the last period")
    # Two candidates: no hint, the parser asks.
    assert not any(h.startswith("'comp'") for h in hints("comp twice a week"))


def test_names_already_written_properly_get_no_hint():
    assert not any("Mrs. Rao" in h for h in hints("Mrs. Rao max 3 a day"))
    assert not any(h.startswith("'maths'") for h in hints("maths max 2 per day"))


def test_informal_spellings():
    assert "'atleast' = at least" in hints("atleast one maths period")


# --- examples --------------------------------------------------------------

def test_every_core_example_is_in_the_stable_prompt_and_retrieved_ones_are_not():
    prompt = P._system_prompt(TEACHERS, SUBJECTS, LABELS, None)
    for ex in P._LIBRARY.core:
        assert ex.body in prompt
    retrieved = [e for e in P._LIBRARY.rest if e.body in prompt]
    assert retrieved == []


def test_the_closest_examples_are_the_relevant_ones():
    typed = [e.typed for e in P._LIBRARY.closest("pt shouldnt be after lunch", 4)]
    assert "No PE right after lunch" in typed
    typed = [e.typed for e in P._LIBRARY.closest("every teacher should get one day off in the week", 4)]
    assert "Every teacher gets at least one full day off" in typed


def test_retrieval_is_deterministic():
    a = [e.typed for e in P._LIBRARY.closest("khan sir doesnt come on tuesdays", 12)]
    b = [e.typed for e in P._LIBRARY.closest("khan sir doesnt come on tuesdays", 12)]
    assert a == b


def test_the_per_sentence_part_carries_hints_and_examples():
    ctx = P._sentence_context("rao maam is off on fridays", TEACHERS, SUBJECTS, LABELS)
    assert "'rao maam' = Mrs. Rao" in ctx
    assert "closest to this sentence" in ctx
    assert len(ctx) < 6_000


def test_held_out_eval_sentences_are_never_worked_examples():
    """Their score only means something while the parser has never seen them."""
    cases = json.loads((pathlib.Path(__file__).resolve().parents[2] / "docs" / "research"
                        / "behaviour-cases.json").read_text(encoding="utf-8"))["cases"]
    library = {e.typed.lower() for e in P._LIBRARY.examples}
    leaked = [c["id"] for c in cases if str(c.get("split", "")).startswith("held_out") and c["typed"].lower() in library]
    assert leaked == []


# --- deterministic checks after parsing ------------------------------------

from app.services.constraint_ir import rule_from_dict  # noqa: E402
from app.services.constraint_ir_english import render  # noqa: E402

WEEK = [(d, o, None, False) for d in range(6) for o in range(1, 7)]


def _parsed(rule_dict):
    rule = rule_from_dict(rule_dict)
    return P.IRParse(rule=rule, sentence=render(rule))


def test_days_named_includes_ranges():
    assert P._days_named("only available Monday to Thursday") == {0, 1, 2, 3}
    assert P._days_named("comes only on Mon Wed Fri") == {0, 2, 4}
    assert P._days_named("no PE after lunch") == set()


def test_an_only_ban_on_the_named_days_is_flipped():
    wrong = _parsed({"form": "count", "scope": [], "selector": {"teachers": ["Ms. Mary"], "days": [1, 2, 3, 4, 5]},
                     "relation": "==", "value": 0})
    fixed = P._sanity(wrong, "Mary maam comes only on Mon Wed Fri", WEEK)
    assert fixed.rule.form.selector.days == (1, 3, 5)
    assert "Tuesday" in fixed.sentence and "Wednesday" not in fixed.sentence


def test_a_correct_only_ban_is_left_alone():
    right = _parsed({"form": "count", "scope": [], "selector": {"teachers": ["Mrs. Rao"], "days": [4, 5]},
                     "relation": "==", "value": 0})
    assert P._sanity(right, "Rao ma'am is only available Monday to Thursday", WEEK) is right


def test_a_rule_is_required_unless_the_sentence_softens_it():
    soft = {"form": "count", "scope": [], "selector": {"subjects": ["Physics"], "days": [2]},
            "relation": ">=", "value": 1, "strength": "preference"}
    assert P._sanity(_parsed(soft), "9A should have physics on wednesday", WEEK).rule.strength == "required"
    kept = _parsed(soft)
    assert P._sanity(kept, "would be nice if physics is on wednesday", WEEK).rule.strength == "preference"
    assert P._sanity(kept, "try to put physics on wednesday", WEEK).rule.strength == "preference"


def test_evening_out_rules_keep_their_strength():
    spread = _parsed({"form": "balance", "scope": ["teacher"], "across": ["day"], "selector": {},
                      "max_spread": 1, "strength": "preference"})
    assert P._sanity(spread, "Spread classes evenly", WEEK).rule.strength == "preference"


def test_the_reading_lessons_are_always_sent():
    prompt = P._system_prompt(TEACHERS, SUBJECTS, LABELS, None)
    assert '"ONLY" names what is ALLOWED' in prompt
    assert "classes\", \"lessons\" and \"periods\" as a count mean periods" in prompt


# Six lessons a day, short break after 2, lunch after 4 - the eval school.
LUNCH_WEEK = [
    (d, o, label, is_break)
    for d in range(6)
    for o, label, is_break in [(1, None, False), (2, None, False), (3, "Short break", True), (4, None, False),
                               (5, None, False), (6, "Lunch", True), (7, None, False), (8, None, False)]
]


def test_the_week_layout_is_read_in_lesson_numbers():
    assert P._lesson_layout(LUNCH_WEEK) == ([1, 2, 3, 4, 5, 6], [5, 6])


def test_only_in_the_first_periods_bans_the_rest():
    wrong = _parsed({"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "period_orders": [1, 2, 3]},
                     "relation": ">=", "value": 1})
    fixed = P._sanity(wrong, "Maths should only be in the first 3 periods", LUNCH_WEEK)
    f = fixed.rule.form
    assert f.selector.period_orders == (4, 5, 6) and f.relation == "==" and f.value == 0


def test_a_correct_only_periods_rule_is_left_alone():
    right = _parsed({"form": "count", "scope": [], "selector": {"teachers": ["Mrs. Pillai"], "period_orders": [1, 2]},
                     "relation": "==", "value": 0})
    assert P._sanity(right, "mrs pillai can teach only periods 3 to 6", LUNCH_WEEK) is right


def test_after_lunch_means_every_period_after_it():
    narrow = _parsed({"form": "count", "scope": [], "selector": {"subjects": ["PE"], "period_orders": [5]},
                      "relation": "==", "value": 0})
    assert P._sanity(narrow, "pt shouldnt be after lunch", LUNCH_WEEK).rule.form.selector.period_orders == (5, 6)
    assert P._sanity(narrow, "No PE right after lunch", LUNCH_WEEK) is narrow


def test_classes_are_periods_unless_the_sentence_says_different():
    distinct = {"form": "count", "scope": ["teacher", "day"], "selector": {}, "relation": "<=", "value": 4,
                "distinct": "class_group"}
    assert P._sanity(_parsed(distinct), "nobody should teach more than 4 classes in a day", LUNCH_WEEK).rule.form.distinct is None
    kept = _parsed(distinct)
    assert P._sanity(kept, "no teacher should take more than 4 different classes in a day", LUNCH_WEEK) is kept


def test_a_same_subject_run_is_grouped_by_subject_without_a_retry():
    class Block:
        name = "record_rule"
        input = {"form": "run", "scope": ["class_group"], "selector": {}, "max_consecutive": 1}
    out = P._read_block(Block(), "No section should have the same subject twice in a row", None)
    assert out.invalid is None and "subject" in out.rule.form.scope

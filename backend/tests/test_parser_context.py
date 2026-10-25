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
    leaked = [c["id"] for c in cases if c.get("split") == "held_out" and c["typed"].lower() in library]
    assert leaked == []

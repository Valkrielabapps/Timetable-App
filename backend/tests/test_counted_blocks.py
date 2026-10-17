"""
"Once a week Physics gets a double, the other days single periods only."

A rule a school gave verbatim, which the reader understood and could not save:
the only way to say "a double" was block_size, which forces EVERY lesson into
one, so the model paired it with "never more than one in a row" and the
validator rightly refused the contradiction. Run gained `blocks`: how many
blocks a week, with single periods otherwise.

Covered here end to end: the rule format, the solver, the check that flags a
hand-edited timetable, the sentence read back to the admin, the mapping of the
model's tool call - and the one retry the reader now gets when a rule it sent
is refused.
"""
from types import SimpleNamespace

import pytest

from app.models.school import ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher
from app.schemas.timetable_structure import TimetableStructure
from app.services.constraint_ir import IRError, Run, rule_from_dict, rule_to_dict
from app.services.constraint_ir_checker import Placement, check_rule
from app.services.constraint_ir_compiler import SchoolIndex
from app.services.constraint_ir_english import render
from app.services import llm_ir_parser
from app.services.llm_ir_parser import _clean, _rule_payload
from app.services.solver import generate_school_timetable
from app.services.timetable_structure import apply, lesson_numbers

DOUBLE_ONCE = {"form": "run", "scope": ["class_group"], "selector": {"subjects": ["Physics"]},
               "block_size": 2, "blocks": 1, "strength": "required"}


# ---------------------------------------------------------------------------
# The rule format
# ---------------------------------------------------------------------------


def test_a_counted_block_round_trips():
    rule = rule_from_dict(DOUBLE_ONCE)
    assert rule.form == Run(scope=("class_group",), selector=rule.form.selector, block_size=2, blocks=1,
                            blocks_relation="==")
    assert rule_from_dict(rule_to_dict(rule)) == rule


@pytest.mark.parametrize("change, words", [
    ({"block_size": None}, "needs block_size"),
    ({"max_consecutive": 1}, "leave max_consecutive out"),
    ({"scope": ["class_group", "day"]}, "counted across the week"),
    ({"blocks": 0}, "between 1 and 7"),
    ({"blocks_relation": "about"}, "blocks_relation"),
])
def test_impossible_shapes_are_refused(change, words):
    data = {**DOUBLE_ONCE, **change}
    if data.get("block_size") is None:
        data.pop("block_size")
    with pytest.raises(IRError, match=words):
        rule_from_dict(data)


def test_a_conditional_cannot_count_blocks():
    with pytest.raises(IRError, match="cannot count blocks"):
        rule_from_dict({"form": "conditional", "scope": ["class_group"],
                        "when": {"form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"]},
                                 "relation": ">=", "value": 1},
                        "then": {k: v for k, v in DOUBLE_ONCE.items() if k != "strength"}})


# ---------------------------------------------------------------------------
# What the admin is shown
# ---------------------------------------------------------------------------


def test_the_sentence_says_how_many_and_what_happens_otherwise():
    """"Blocks of 2" alone reads as every lesson being a double - the exact
    misreading this exists to avoid - so the count and the rest are said."""
    assert render(rule_from_dict(DOUBLE_ONCE)) == (
        "For every class, Physics periods come as exactly one double a week (2 back to back), "
        "with no more than one on any other day."
    )


def test_the_sentence_for_at_least_two_triples():
    rule = rule_from_dict({**DOUBLE_ONCE, "block_size": 3, "blocks": 2, "blocks_relation": ">="})
    assert "at least two triples a week (3 back to back)" in render(rule)


# ---------------------------------------------------------------------------
# The solver
# ---------------------------------------------------------------------------


@pytest.fixture
def school(orm_db):
    s = School(name="Test School")
    orm_db.add(s)
    orm_db.commit()
    section = ClassGroup(school_id=s.id, grade="Grade 11", name="A")
    physics = Subject(school_id=s.id, name="Physics")
    english = Subject(school_id=s.id, name="English")
    orm_db.add_all([section, physics, english])
    orm_db.commit()
    rao = Teacher(school_id=s.id, name="Mrs. Rao", qualified_subject_ids=[physics.id])
    khan = Teacher(school_id=s.id, name="Mr. Khan", qualified_subject_ids=[english.id])
    orm_db.add_all([rao, khan])
    orm_db.commit()
    return {"db": orm_db, "school": s, "section": section, "physics": physics, "english": english, "rao": rao}


def _setup(w, structure, physics, english=0, rule=DOUBLE_ONCE, strength="required"):
    db = w["db"]
    apply(db, w["school"].id, TimetableStructure(**structure))
    db.add(SubjectRequirement(class_group_id=w["section"].id, subject_id=w["physics"].id, periods_per_week=physics))
    if english:
        db.add(SubjectRequirement(class_group_id=w["section"].id, subject_id=w["english"].id, periods_per_week=english))
    db.add(Constraint(school_id=w["school"].id, type="ir", is_hard=strength == "required",
                      parameters={**rule, "strength": strength}, description="double once"))
    db.commit()


def _physics_by_day(w, result):
    periods = {p.id: p for p in w["db"].query(Period).all()}
    numbers = lesson_numbers(periods.values())
    out: dict[int, list[int]] = {}
    for a in result.assignments:
        if a["subject_id"] == w["physics"].id:
            p = periods[a["period_id"]]
            out.setdefault(p.day_of_week, []).append(numbers[p.id])
    return {d: sorted(n) for d, n in out.items()}


def test_one_double_and_singles_the_other_days(school):
    """Four Physics periods over three days: the only shape that fits is one
    double and two singles - and the double is back to back."""
    _setup(school, {"days": [0, 1, 2], "periods_per_day": 4}, physics=4)
    result = generate_school_timetable(school["db"], school["school"].id)
    assert result.status in ("optimal", "feasible"), result.errors
    days = _physics_by_day(school, result)
    assert sorted(len(v) for v in days.values()) == [1, 1, 2]
    double = next(v for v in days.values() if len(v) == 2)
    assert double[1] - double[0] == 1


def test_more_than_fits_is_impossible(school):
    """Five periods over three days would need a second double or two singles
    on one day - both of which the rule rules out."""
    _setup(school, {"days": [0, 1, 2], "periods_per_day": 4}, physics=5)
    assert generate_school_timetable(school["db"], school["school"].id).status not in ("optimal", "feasible")


def test_without_the_rule_the_same_week_is_fine(school):
    """So the refusal above is the rule's doing, not the school's."""
    _setup(school, {"days": [0, 1, 2], "periods_per_day": 4}, physics=5,
           rule={**DOUBLE_ONCE, "blocks": 3, "blocks_relation": "<="})
    assert generate_school_timetable(school["db"], school["school"].id).status in ("optimal", "feasible")


def test_a_double_does_not_straddle_lunch(school):
    """Lunch after period 1: periods 1 and 2 are not back to back. With
    Mrs. Rao unable to take period 3, the only adjacent pair left is gone, so
    the week can't satisfy the rule."""
    _setup(school, {"days": [0], "periods_per_day": 3, "breaks": [{"after": 1, "label": "Lunch"}]}, physics=2)
    db = school["db"]
    numbers = lesson_numbers(db.query(Period).all())
    third = next(pid for pid, n in numbers.items() if n == 3)
    school["rao"].unavailable_period_ids = [third]
    db.commit()
    assert generate_school_timetable(db, school["school"].id).status not in ("optimal", "feasible")


def test_a_day_with_no_room_for_a_double_still_gets_one_period_at_most(school):
    """Lunch splits the day into single periods, so no double fits - and two
    singles either side of lunch are still two on one day, which "single
    periods otherwise" rules out."""
    _setup(school, {"days": [0], "periods_per_day": 2, "breaks": [{"after": 1, "label": "Lunch"}]}, physics=2,
           rule={**DOUBLE_ONCE, "blocks_relation": "<="})
    assert generate_school_timetable(school["db"], school["school"].id).status not in ("optimal", "feasible")


def test_a_preference_bends_rather_than_breaks(school):
    """As a preference, an impossible week still gets a timetable."""
    _setup(school, {"days": [0, 1, 2], "periods_per_day": 4}, physics=5, strength="preference")
    assert generate_school_timetable(school["db"], school["school"].id).status in ("optimal", "feasible")


def test_at_least_two_doubles(school):
    _setup(school, {"days": [0, 1, 2], "periods_per_day": 4}, physics=4,
           rule={**DOUBLE_ONCE, "blocks": 2, "blocks_relation": ">="})
    result = generate_school_timetable(school["db"], school["school"].id)
    assert sorted(len(v) for v in _physics_by_day(school, result).values()) == [2, 2]


# ---------------------------------------------------------------------------
# Checking a hand-edited timetable
# ---------------------------------------------------------------------------


INDEX = SchoolIndex(subject_ids={"Physics": 1}, teacher_ids={}, class_group_ids={})


def _lessons(*slots):
    """(day, order) per Physics lesson in one section."""
    return [Placement(entry_id=i, class_group_id=7, subject_id=1, teacher_id=3, period_id=100 + i,
                      day_of_week=d, order=o) for i, (d, o) in enumerate(slots)]


def _check(*slots):
    return [v.detail for v in check_rule(_lessons(*slots), rule_from_dict(DOUBLE_ONCE), INDEX)]


def test_a_timetable_that_keeps_the_rule_is_clean():
    assert _check((0, 1), (0, 2), (1, 3), (2, 5)) == []


def test_two_on_a_day_apart_is_flagged():
    assert _check((0, 1), (0, 3), (1, 2)) == [
        "2 on Monday, but not back to back",
        "0 blocks of 2 this week, but the rule says exactly 1",
    ]


def test_three_on_a_day_is_flagged():
    assert "3 on Monday, but the rule allows a block of 2 or a single period" in _check((0, 1), (0, 2), (0, 3))


def test_two_doubles_are_flagged():
    assert _check((0, 1), (0, 2), (1, 4), (1, 5)) == ["2 blocks of 2 this week, but the rule says exactly 1"]


# ---------------------------------------------------------------------------
# Reading the model's tool call
# ---------------------------------------------------------------------------


def _from_tool_call(**flat):
    return rule_from_dict(_clean(_rule_payload(flat)))


def test_the_tool_call_maps_onto_counted_blocks():
    rule = _from_tool_call(form="run", scope=["class_group"], selector={"subjects": ["Physics"]},
                           block_size=2, blocks=1, blocks_relation="exactly", description="x")
    assert (rule.form.block_size, rule.form.blocks, rule.form.blocks_relation) == (2, 1, "==")


def test_relation_defaults_to_exactly():
    rule = _from_tool_call(form="run", scope=["class_group"], selector={"subjects": ["Physics"]},
                           block_size=2, blocks=1, description="x")
    assert rule.form.blocks_relation == "=="


def test_a_restated_single_period_cap_is_dropped_not_refused():
    """"Doubles once, singles otherwise" sent with max_consecutive=1 as well is
    the model restating the second half - not a contradiction to refuse."""
    rule = _from_tool_call(form="run", scope=["class_group"], selector={"subjects": ["Physics"]},
                           block_size=2, blocks=1, max_consecutive=1, blocks_relation="at_most",
                           description="x")
    assert rule.form.max_consecutive is None and rule.form.blocks_relation == "<="


def test_the_prompt_teaches_this_exact_sentence():
    assert "Once in a week, physics must be given 2 lectures consecutively" in llm_ir_parser._EXAMPLES


# ---------------------------------------------------------------------------
# One retry when a rule is refused
# ---------------------------------------------------------------------------


def _tool(name, **data):
    return SimpleNamespace(type="tool_use", name=name, id=f"tool_{name}", input=data)


def _response(block):
    return SimpleNamespace(content=[block], usage=SimpleNamespace(
        input_tokens=10, output_tokens=5, cache_read_input_tokens=100, cache_creation_input_tokens=0))


BROKEN = _tool("record_rule", form="run", scope=["class_group"], selector={"subjects": ["Physics"]},
               block_size=2, max_consecutive=1, description="x")
FIXED = _tool("record_rule", form="run", scope=["class_group"], selector={"subjects": ["Physics"]},
              block_size=2, blocks=1, description="x")


@pytest.fixture
def fake_client(monkeypatch):
    calls = []
    replies = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return _response(reply)

    class Client:
        def __init__(self, **_):
            self.messages = Messages()

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", Client)
    monkeypatch.setattr(llm_ir_parser.settings, "anthropic_api_key", "test-key")
    return calls, replies


def _parse():
    return llm_ir_parser.parse_rule_llm("physics double once a week", [], ["Physics"], [], [])


def test_a_refused_rule_is_sent_back_once_and_the_fix_is_used(fake_client):
    calls, replies = fake_client
    replies.extend([BROKEN, FIXED])
    result = _parse()
    assert result.rule is not None and result.rule.form.blocks == 1
    assert len(calls) == 2
    # The model is told why, against the rule it sent.
    feedback = calls[1]["messages"][-1]["content"][0]
    assert feedback["type"] == "tool_result" and feedback["is_error"] is True
    assert feedback["tool_use_id"] == BROKEN.id
    assert "cannot fit under a maximum run" in feedback["content"]
    # Both calls' tokens are counted.
    assert result.usage == (20, 10, 200, 0)


def test_the_model_can_answer_the_retry_by_saying_what_it_cannot_express(fake_client):
    calls, replies = fake_client
    replies.extend([BROKEN, _tool("report_unclear", reason="not_supported", explanation="Can't count those.")])
    result = _parse()
    assert result.unclear is not None and result.unclear.explanation == "Can't count those."


def test_refused_twice_is_reported_as_refused(fake_client):
    calls, replies = fake_client
    replies.extend([BROKEN, BROKEN])
    result = _parse()
    assert result.invalid is not None and result.rule is None
    assert len(calls) == 2


def test_a_good_first_answer_is_not_retried(fake_client):
    calls, replies = fake_client
    replies.append(FIXED)
    assert _parse().rule is not None
    assert len(calls) == 1


def test_an_unclear_first_answer_is_not_retried(fake_client):
    calls, replies = fake_client
    replies.append(_tool("report_unclear", reason="ambiguous", explanation="Which class?"))
    assert _parse().unclear is not None
    assert len(calls) == 1


def test_a_failed_retry_keeps_the_first_answer(fake_client):
    calls, replies = fake_client
    replies.extend([BROKEN, RuntimeError("network")])
    result = _parse()
    assert result.invalid is not None

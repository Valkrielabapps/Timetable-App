"""
Who and what a saved rule is about.

The Constraints tab groups rules by this, so the property under test is that a
rule lands under what it actually constrains - worked out from the stored rule,
the same fields the solver reads, never from its wording.
"""
import pytest

from app.core.database import SessionLocal
from app.models.school import ClassGroup, Subject, Teacher
from app.services.constraint_about import about
from tests.conftest import create_school, signup


def ir(**form):
    return about("ir", {"strength": "required", **form}, {}, {}, {})


# ---------------------------------------------------------------------------
# Rules in the general form
# ---------------------------------------------------------------------------


def test_a_rule_naming_a_teacher_is_about_that_teacher():
    """Grouped per teacher by the solver, but about her alone - not every teacher."""
    got = ir(form="count", scope=["teacher", "day"], selector={"teachers": ["Mrs. Rao"]},
             relation="<=", value=6)
    assert got == {"teachers": ["Mrs. Rao"], "subjects": [], "class_groups": [], "every": []}


def test_a_rule_naming_nobody_is_about_everyone_it_ranges_over():
    """"No teacher teaches more than 6 periods a day." """
    got = ir(form="count", scope=["teacher", "day"], selector={}, relation="<=", value=6)
    assert got["every"] == ["teacher"]
    assert got["teachers"] == []


def test_when_a_rule_applies_is_not_who_it_is_about():
    """Day and period scopes say when, so "every day" is not a group."""
    got = ir(form="count", scope=["day"], selector={"subjects": ["PE"]}, relation="<=", value=2)
    assert got["every"] == []
    assert got["subjects"] == ["PE"]


def test_excluded_subjects_are_not_what_a_rule_is_about():
    """"Theory periods" means not PE or Art. Filing it under PE would point
    someone at exactly the subject it leaves alone."""
    got = ir(form="run", scope=["class_group"], selector={"not_subjects": ["PE", "Art"]},
             max_consecutive=3)
    assert got["subjects"] == []
    assert got["every"] == ["class_group"]


def test_both_sides_of_a_two_subject_rule_count():
    got = ir(form="adjacency", scope=["class_group"], first={"subjects": ["PE"]},
             second={"subjects": ["Maths"]}, min_gap=1, directional=True)
    assert got["subjects"] == ["Maths", "PE"]


def test_both_halves_of_a_conditional_count():
    """"On days Priya teaches Grade 12, she teaches at most 5 periods." """
    got = ir(
        form="conditional", scope=["teacher", "day"],
        when={"form": "count", "scope": ["teacher", "day"],
              "selector": {"class_groups": ["Grade 12"]}, "relation": ">=", "value": 1},
        then={"form": "count", "scope": ["teacher", "day"],
              "selector": {"teachers": ["Priya"]}, "relation": "<=", "value": 5},
    )
    assert got["teachers"] == ["Priya"]
    assert got["class_groups"] == ["Grade 12"]
    assert got["every"] == []


def test_a_rule_that_no_longer_reads_is_about_nothing():
    """Rather than raising and taking the whole list down with it."""
    assert ir(form="nonsense") == {"teachers": [], "subjects": [], "class_groups": [], "every": []}


# ---------------------------------------------------------------------------
# The older, named rule types
# ---------------------------------------------------------------------------


TEACHERS = {1: "Mrs. Rao"}
SUBJECTS = {10: "PE", 11: "Maths"}
SECTIONS = {100: "Grade 11 - A", 101: "Grade 11 - B"}


def legacy(constraint_type, **parameters):
    return about(constraint_type, parameters, TEACHERS, SUBJECTS, SECTIONS)


def test_a_teacher_rule_names_the_teacher():
    assert legacy("availability", teacher_id=1, day_of_week=4)["teachers"] == ["Mrs. Rao"]


def test_a_two_subject_rule_names_both():
    got = legacy("min_gap_between_subjects", first_subject_id=10, second_subject_id=11, min_gap=1)
    assert got["subjects"] == ["Maths", "PE"]


def test_a_scoped_rule_names_its_sections():
    got = legacy("no_subject_period", subject_id=10, position="first", class_group_ids=[101, 100])
    assert got["class_groups"] == ["Grade 11 - A", "Grade 11 - B"]
    assert got["subjects"] == ["PE"]


def test_an_id_that_no_longer_exists_is_left_out_rather_than_shown_as_a_number():
    got = legacy("workload_limit", teacher_id=99, max_periods_per_week=30)
    assert got["teachers"] == []


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


@pytest.fixture
def school(client):
    _, headers = signup(client)
    s = create_school(client, headers)
    db = SessionLocal()
    try:
        rao = Teacher(school_id=s["id"], name="Mrs. Rao", qualified_subject_ids=[])
        pe = Subject(school_id=s["id"], name="PE")
        a = ClassGroup(school_id=s["id"], grade="Grade 11", name="A")
        db.add_all([rao, pe, a])
        db.commit()
        ids = {"school": s["id"], "rao": rao.id, "pe": pe.id, "a": a.id}
    finally:
        db.close()
    return ids, headers


def test_the_list_says_what_each_rule_is_about(client, school):
    ids, h = school
    client.post("/api/constraints", json={
        "school_id": ids["school"], "type": "no_subject_period",
        "parameters": {"subject_id": ids["pe"], "position": "first", "class_group_ids": [ids["a"]]},
    }, headers=h)
    client.post("/api/constraints", json={
        "school_id": ids["school"], "type": "ir",
        "parameters": {"form": "count", "scope": ["teacher", "day"],
                       "selector": {"teachers": ["Mrs. Rao"]}, "relation": "<=", "value": 6,
                       "strength": "required"},
    }, headers=h)
    rows = client.get(f"/api/constraints?school_id={ids['school']}", headers=h).json()
    by_type = {r["type"]: r["about"] for r in rows}
    assert by_type["no_subject_period"] == {
        "teachers": [], "subjects": ["PE"], "class_groups": ["Grade 11 - A"], "every": [],
    }
    assert by_type["ir"]["teachers"] == ["Mrs. Rao"]


def test_a_single_rule_response_says_too(client, school):
    """Creating or rewording returns one rule, and the page files it straight away."""
    ids, h = school
    r = client.post("/api/constraints", json={
        "school_id": ids["school"], "type": "availability",
        "parameters": {"teacher_id": ids["rao"], "day_of_week": 4},
    }, headers=h)
    assert r.json()["about"]["teachers"] == ["Mrs. Rao"]

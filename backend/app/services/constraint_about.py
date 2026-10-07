"""
Who and what a saved rule is about, so the Constraints tab can group rules
the way an admin looks for them: "what did I set for Mrs. Rao?", "what applies
to Grade 11?".

Worked out from the stored rule itself, never from its wording - the same
fields the solver reads - so a rule can't be filed under a teacher it does not
actually constrain.

    teachers / subjects / class_groups
        Names the rule singles out. "Mrs. Rao is free on Fridays" names Mrs.
        Rao; "no PE in period 1" names PE.
    every
        What the rule applies to one at a time without naming any: "no teacher
        teaches more than 6 periods a day" is about every teacher, and names
        none.

Excluded subjects ("theory periods, i.e. not PE or Art") are not counted as
what a rule is about: such a rule is about all the other subjects, and filing
it under PE would point someone at exactly the subject it leaves alone.
"""
from __future__ import annotations

from app.services.constraint_ir import (
    Adjacency, Balance, Bucket, Conditional, Count, IRError, Run, Selector, Span, rule_from_dict,
)

# Scope dimensions an "every ..." can be about. day / period are when a rule
# applies, not who it is about.
_PEOPLE_DIMENSIONS = ("teacher", "class_group", "subject")


def _empty() -> dict[str, list[str]]:
    return {"teachers": [], "subjects": [], "class_groups": [], "every": []}


def _ir_about(parameters: dict) -> dict[str, list[str]]:
    try:
        rule = rule_from_dict(parameters)
    except IRError:
        return _empty()

    teachers: set[str] = set()
    subjects: set[str] = set()
    class_groups: set[str] = set()
    scoped: set[str] = set()

    def take(sel: Selector) -> None:
        teachers.update(sel.teachers or ())
        subjects.update(sel.subjects or ())
        class_groups.update(sel.class_groups or ())

    def visit(form) -> None:
        scoped.update(form.scope)
        if isinstance(form, (Count, Run, Balance, Span)):
            take(form.selector)
        elif isinstance(form, (Adjacency, Bucket)):
            take(form.first)
            take(form.second)
        elif isinstance(form, Conditional):
            visit(form.when)
            visit(form.then)

    visit(rule.form)
    named = {"teacher": teachers, "class_group": class_groups, "subject": subjects}
    return {
        "teachers": sorted(teachers),
        "subjects": sorted(subjects),
        "class_groups": sorted(class_groups),
        # "Every teacher" only when the rule names none: "Mrs. Rao teaches at
        # most 6 a day" is grouped per teacher by the solver but is about her.
        "every": [d for d in _PEOPLE_DIMENSIONS if d in scoped and not named[d]],
    }


def about(constraint_type: str, parameters: dict, teacher_names: dict[int, str],
          subject_names: dict[int, str], class_group_labels: dict[int, str]) -> dict[str, list[str]]:
    """{teachers, subjects, class_groups, every} for one saved constraint.

    The legacy types store ids rather than names; the maps turn them into the
    names the page shows. An id that no longer resolves is left out rather
    than shown as a number.
    """
    p = parameters or {}
    if constraint_type == "ir":
        return _ir_about(p)

    out = _empty()
    if p.get("teacher_id") in teacher_names:
        out["teachers"].append(teacher_names[p["teacher_id"]])
    for key in ("subject_id", "first_subject_id", "second_subject_id"):
        name = subject_names.get(p.get(key))
        if name and name not in out["subjects"]:
            out["subjects"].append(name)
    out["class_groups"] = [
        class_group_labels[i] for i in (p.get("class_group_ids") or []) if i in class_group_labels
    ]
    out["subjects"].sort()
    out["class_groups"].sort()
    return out

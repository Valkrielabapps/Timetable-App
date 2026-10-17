"""A section keeps the same teacher for a subject all week.

Before this the teacher was picked lesson by lesson, so with two qualified
teachers a section's English could be split between them - legal by every
other rule, and not how any school runs."""
from collections import defaultdict

import pytest

from app.core.config import settings
from app.models.school import Teacher
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _require, _school, _subject, _teacher, db  # noqa: F401


def _teachers_per_subject(result):
    seen = defaultdict(set)
    for a in result.assignments:
        seen[(a["class_group_id"], a["subject_id"], a.get("batch"))].add(a["teacher_id"])
    return seen


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_every_lesson_of_a_subject_has_the_same_teacher(db, monkeypatch, seed):  # noqa: F811
    monkeypatch.setattr(settings, "solver_random_seed", seed)
    school = _school(db, days=5, per_day=6)
    english = _subject(db, school, "English")
    maths = _subject(db, school, "Maths")
    for name in ("Rao", "Iyer", "Khan"):
        _teacher(db, school, name, [english.id, maths.id])
    for n in ("A", "B", "C"):
        cg = _class_group(db, school, name=n)
        _require(db, cg, english, 6)
        _require(db, cg, maths, 6)

    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    assert all(len(t) == 1 for t in _teachers_per_subject(result).values())


def test_a_load_that_only_fits_by_splitting_is_refused(db):  # noqa: F811
    """Two sections need 4 English each; the teachers can give 3 and 5.
    8 periods fit 3 + 5 only by splitting one section between them, which is
    no longer allowed - so there is no timetable."""
    school = _school(db, days=2, per_day=4)
    english = _subject(db, school, "English")
    a = _teacher(db, school, "Rao", [english.id])
    b = _teacher(db, school, "Iyer", [english.id])
    for t, cap in ((a, 3), (b, 5)):
        db.get(Teacher, t.id).max_periods_per_week = cap
    db.commit()
    for n in ("A", "B"):
        _require(db, _class_group(db, school, name=n), english, 4)

    result = generate_school_timetable(db, school.id)
    assert result.status not in ("optimal", "feasible")

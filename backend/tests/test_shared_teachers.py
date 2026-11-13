"""A subject given to two named teachers in a section is shared out evenly
between them - unless a teacher's limit makes that impossible."""
from collections import Counter

from app.models.school import SubjectRequirement
from app.services.solver import generate_school_timetable
from tests.test_ir_end_to_end import _class_group, _school, _subject, _teacher, db  # noqa: F401


def _shared(db, school, periods, cap=None):  # noqa: F811
    bs = _subject(db, school, "Business Studies")
    subha = _teacher(db, school, "Subha", [bs.id])
    matthew = _teacher(db, school, "Matthew", [bs.id])
    if cap is not None:
        subha.max_periods_per_week = cap
        db.commit()
    cg = _class_group(db, school, grade="Grade 12", name="C")
    db.add(SubjectRequirement(class_group_id=cg.id, subject_id=bs.id, periods_per_week=periods,
                              allowed_teacher_ids=[subha.id, matthew.id]))
    db.commit()
    return subha, matthew


def test_nine_periods_between_two_teachers_is_five_and_four(db):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    subha, matthew = _shared(db, school, 9)
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    counts = Counter(a["teacher_id"] for a in result.assignments)
    assert sorted([counts[subha.id], counts[matthew.id]]) == [4, 5]


def test_a_teachers_limit_wins_over_an_even_split(db):  # noqa: F811
    school = _school(db, days=5, per_day=4)
    subha, matthew = _shared(db, school, 8, cap=2)
    result = generate_school_timetable(db, school.id)
    assert result.status in ("optimal", "feasible"), result.errors
    counts = Counter(a["teacher_id"] for a in result.assignments)
    assert counts[subha.id] <= 2 and counts[subha.id] + counts[matthew.id] == 8
    assert counts[subha.id] == 2  # as many as her limit allows, the rest to Matthew

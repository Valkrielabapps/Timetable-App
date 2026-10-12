"""
Setting a school's week up once instead of period by period.

The admin says how many periods a day, which days, where the breaks fall,
and whether there is a class teacher period and a zero period; the periods
are made from that. The properties under test:

  - the day comes out as described, with only lessons numbered, so "period 1"
    is the first lesson whatever comes before it;
  - changing the structure keeps every period that still has a place in it,
    so what points at periods - teacher unavailability, timetables, rules -
    keeps pointing at the same lesson, and whatever has to go is reported;
  - reading the structure back gives what was saved.
"""
import pytest

from app.models.school import (
    ClassGroup, Constraint, Period, School, Teacher, Timetable, TimetableEntry, ZeroPeriod, Subject,
)
from app.schemas.timetable_structure import TimetableStructure
from app.services.timetable_structure import StructureError, apply, infer, lesson_numbers


def cfg(**kw):
    base = {"days": [0, 1, 2, 3, 4], "periods_per_day": 8}
    return TimetableStructure(**{**base, **kw})


@pytest.fixture
def school(orm_db):
    s = School(name="Test School")
    orm_db.add(s)
    orm_db.commit()
    for grade, name in (("Grade 6", "A"), ("Grade 6", "B"), ("Grade 7", "A")):
        orm_db.add(ClassGroup(school_id=s.id, grade=grade, name=name))
    orm_db.commit()
    return s


def day(db, school, day_of_week=0):
    """One day as (kind, number, label) tuples in order."""
    periods = db.query(Period).filter(Period.school_id == school.id).all()
    numbers = lesson_numbers(periods)
    return [
        (p.kind, numbers.get(p.id), p.label)
        for p in sorted(periods, key=lambda p: p.order) if p.day_of_week == day_of_week
    ]


def lesson(db, school, day_of_week, number):
    periods = db.query(Period).filter(Period.school_id == school.id).all()
    numbers = lesson_numbers(periods)
    return next(p for p in periods if p.day_of_week == day_of_week and numbers.get(p.id) == number)


def reservations(db, school):
    periods = db.query(Period).filter(Period.school_id == school.id).all()
    numbers = lesson_numbers(periods)
    by_id = {p.id: p for p in periods}
    return sorted(
        (by_id[z.period_id].day_of_week, numbers[z.period_id], z.grade)
        for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school.id).all()
    )


# ---------------------------------------------------------------------------
# Laying out the day
# ---------------------------------------------------------------------------


def test_the_same_periods_every_working_day(orm_db, school):
    apply(orm_db, school.id, cfg())
    for d in range(5):
        assert day(orm_db, school, d) == [("lesson", n, None) for n in range(1, 9)]
    assert day(orm_db, school, 5) == []


def test_breaks_sit_between_numbers(orm_db, school):
    apply(orm_db, school.id, cfg(breaks=[{"after": 3, "label": "Recess"}, {"after": 6, "label": "Lunch"}]))
    assert day(orm_db, school) == [
        ("lesson", 1, None), ("lesson", 2, None), ("lesson", 3, None), ("break", None, "Recess"),
        ("lesson", 4, None), ("lesson", 5, None), ("lesson", 6, None), ("break", None, "Lunch"),
        ("lesson", 7, None), ("lesson", 8, None),
    ]


def test_a_class_teacher_period_at_the_start_does_not_shift_period_1(orm_db, school):
    apply(orm_db, school.id, cfg(class_teacher_period={"enabled": True}))
    assert day(orm_db, school)[:2] == [("class_teacher", None, None), ("lesson", 1, None)]
    assert len(day(orm_db, school)) == 9


def test_a_class_teacher_period_can_come_later(orm_db, school):
    apply(orm_db, school.id, cfg(class_teacher_period={"enabled": True, "after": 2}))
    assert [k for k, _, _ in day(orm_db, school)][:4] == ["lesson", "lesson", "class_teacher", "lesson"]


def test_a_shorter_day(orm_db, school):
    apply(orm_db, school.id, cfg(days=[0, 1, 2, 3, 4, 5], short_days={5: 4},
                                 breaks=[{"after": 3}, {"after": 6}]))
    assert [n for k, n, _ in day(orm_db, school, 5) if k == "lesson"] == [1, 2, 3, 4]
    # The break after 3 falls inside the short day; the one after 6 doesn't.
    assert [k for k, _, _ in day(orm_db, school, 5)].count("break") == 1


def test_a_shorter_day_does_not_end_on_a_break(orm_db, school):
    """A break after period 4 is lunch on a full day and just the end of a
    four-period Saturday - there is nothing after it to break from."""
    apply(orm_db, school.id, cfg(days=[0, 5], short_days={5: 4}, breaks=[{"after": 4, "label": "Lunch"}],
                                 class_teacher_period={"enabled": True, "after": 4}))
    assert [k for k, _, _ in day(orm_db, school, 5)] == ["lesson"] * 4
    assert "break" in [k for k, _, _ in day(orm_db, school, 0)]


def test_a_whole_school_zero_period_at_a_fixed_point_takes_no_number(orm_db, school):
    """Nobody is taught in it, so it is a slot like a break - and the eight
    periods keep their numbers."""
    apply(orm_db, school.id, cfg(zero_period={"enabled": True, "scope": "school",
                                               "placements": [{"every_day": 5}]}))
    kinds = day(orm_db, school)
    assert kinds[4] == ("zero", None, None)
    assert [n for k, n, _ in kinds if k == "lesson"] == list(range(1, 9))
    assert reservations(orm_db, school) == []


def test_a_zero_period_that_moves_between_days_is_a_numbered_slot_kept_free(orm_db, school):
    """Some days it's period 2, others period 7 - so each day has nine
    numbered periods, and the zero one is kept free rather than unnumbered."""
    apply(orm_db, school.id, cfg(days=[0, 1], zero_period={
        "enabled": True, "scope": "school", "placements": [{"by_day": {0: 2, 1: 7}}]}))
    assert [n for k, n, _ in day(orm_db, school, 0) if k == "lesson"] == list(range(1, 10))
    assert reservations(orm_db, school) == [(0, 2, None), (1, 7, None)]


def test_zero_periods_per_grade(orm_db, school):
    apply(orm_db, school.id, cfg(days=[0], zero_period={"enabled": True, "scope": "grade", "placements": [
        {"grade": "Grade 6", "every_day": 1}, {"grade": "Grade 7", "every_day": 9}]}))
    assert reservations(orm_db, school) == [(0, 1, "Grade 6"), (0, 9, "Grade 7")]


@pytest.mark.parametrize("bad, words", [
    ({"days": []}, "at least one working day"),
    ({"short_days": {0: 8}}, "between 1 and 7"),
    ({"short_days": {6: 4}}, "isn't a working day"),
    ({"breaks": [{"after": 8}]}, "after a period between 1 and 7"),
    ({"breaks": [{"after": 3}, {"after": 3}]}, "two breaks after period 3"),
    ({"class_teacher_period": {"enabled": True, "after": 8}}, "class teacher period"),
    ({"zero_period": {"enabled": True, "scope": "school", "placements": []}}, "where the zero period goes"),
    ({"zero_period": {"enabled": True, "scope": "grade",
                      "placements": [{"grade": "Grade 12", "every_day": 1}]}}, "Grade 12"),
    ({"zero_period": {"enabled": True, "scope": "school",
                      "placements": [{"every_day": 1, "by_day": {0: 1}}]}}, "not both"),
    ({"zero_period": {"enabled": True, "scope": "school", "placements": [{"every_day": 10}]}}, "period 10"),
])
def test_impossible_structures_are_refused_with_a_reason(orm_db, school, bad, words):
    with pytest.raises(StructureError, match=words):
        apply(orm_db, school.id, cfg(**bad))
    assert orm_db.query(Period).count() == 0


# ---------------------------------------------------------------------------
# Changing it later
# ---------------------------------------------------------------------------


def test_saving_the_same_structure_changes_nothing(orm_db, school):
    structure = cfg(breaks=[{"after": 4, "label": "Lunch"}], class_teacher_period={"enabled": True})
    apply(orm_db, school.id, structure)
    before = {(p.id, p.order, p.kind) for p in orm_db.query(Period).all()}
    report = apply(orm_db, school.id, structure)
    assert report.changed is False
    assert {(p.id, p.order, p.kind) for p in orm_db.query(Period).all()} == before


def test_adding_a_class_teacher_period_keeps_every_lesson_where_it_was(orm_db, school):
    """Teacher unavailability and timetables point at periods by id, so a
    lesson must stay the same row when something is added around it."""
    apply(orm_db, school.id, cfg(breaks=[{"after": 4}]))
    ids = {n: lesson(orm_db, school, 0, n).id for n in range(1, 9)}
    report = apply(orm_db, school.id, cfg(breaks=[{"after": 4}], class_teacher_period={"enabled": True}))
    assert report.changed is True
    assert report.periods_added == 5 and report.periods_removed == 0
    assert {n: lesson(orm_db, school, 0, n).id for n in range(1, 9)} == ids


def test_dropping_a_period_reports_what_went_with_it(orm_db, school):
    apply(orm_db, school.id, cfg())
    eighth = lesson(orm_db, school, 0, 8)
    third = lesson(orm_db, school, 0, 3)
    teacher = Teacher(school_id=school.id, name="Mrs. Rao", qualified_subject_ids=[],
                      unavailable_period_ids=[eighth.id, third.id])
    subject = Subject(school_id=school.id, name="Maths")
    orm_db.add_all([teacher, subject])
    tt = Timetable(school_id=school.id, status="draft")
    orm_db.add(tt)
    orm_db.commit()
    section = orm_db.query(ClassGroup).first()
    orm_db.add(TimetableEntry(timetable_id=tt.id, class_group_id=section.id, subject_id=subject.id,
                              teacher_id=teacher.id, period_id=eighth.id))
    orm_db.add(Constraint(school_id=school.id, type="ir", description="No Maths in period 8.", parameters={
        "form": "count", "scope": ["class_group"], "selector": {"subjects": ["Maths"], "period_orders": [8]},
        "relation": "==", "value": 0}))
    orm_db.commit()

    report = apply(orm_db, school.id, cfg(periods_per_day=7))
    orm_db.expire_all()
    assert report.periods_removed == 5
    assert report.timetable_entries_removed == 1
    assert report.unavailability_removed == ["Mrs. Rao: 1 unavailable period no longer exists"]
    assert orm_db.get(Teacher, teacher.id).unavailable_period_ids == [third.id]
    assert len(report.rules_out_of_range) == 1 and "period 8" in report.rules_out_of_range[0]
    assert report.timetable_outdated is True


def test_sections_without_a_class_teacher_are_named(orm_db, school):
    teacher = Teacher(school_id=school.id, name="Mrs. Rao", qualified_subject_ids=[])
    orm_db.add(teacher)
    orm_db.commit()
    first = orm_db.query(ClassGroup).filter(ClassGroup.grade == "Grade 6", ClassGroup.name == "A").one()
    first.class_teacher_id = teacher.id
    orm_db.commit()
    report = apply(orm_db, school.id, cfg(class_teacher_period={"enabled": True}))
    assert report.sections_without_class_teacher == ["Grade 6 - B", "Grade 7 - A"]


def test_no_timetable_means_nothing_is_outdated(orm_db, school):
    apply(orm_db, school.id, cfg())
    assert apply(orm_db, school.id, cfg(periods_per_day=6)).timetable_outdated is False


def test_turning_a_zero_period_off_frees_its_slot(orm_db, school):
    apply(orm_db, school.id, cfg(days=[0], zero_period={"enabled": True, "scope": "grade",
                                                        "placements": [{"grade": "Grade 6", "every_day": 2}]}))
    report = apply(orm_db, school.id, cfg(days=[0]))
    assert reservations(orm_db, school) == []
    assert report.periods_removed == 1  # the ninth numbered slot


# ---------------------------------------------------------------------------
# Reading it back
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("structure", [
    cfg(),
    cfg(days=[0, 1, 2, 3, 4, 5], short_days={5: 4}, breaks=[{"after": 3, "label": "Recess"},
                                                         {"after": 6, "label": "Lunch"}]),
    cfg(class_teacher_period={"enabled": True}, breaks=[{"after": 4, "label": "Lunch"}]),
    cfg(class_teacher_period={"enabled": True, "after": 3}),
    cfg(zero_period={"enabled": True, "scope": "school", "placements": [{"every_day": 9}]}),
    cfg(zero_period={"enabled": True, "scope": "school", "placements": [{"every_day": 3}]}),
    cfg(days=[0, 1], zero_period={"enabled": True, "scope": "school",
                                  "placements": [{"by_day": {0: 2, 1: 7}}]}),
    cfg(zero_period={"enabled": True, "scope": "grade", "placements": [
        {"grade": "Grade 6", "every_day": 1}, {"grade": "Grade 7", "by_day": {0: 9, 2: 4}}]}),
])
def test_what_is_saved_is_what_is_read_back(orm_db, school, structure):
    apply(orm_db, school.id, structure)
    read, irregular = infer(orm_db, school.id)
    assert irregular is False
    assert read == structure


def test_a_school_with_no_periods_has_no_structure(orm_db, school):
    assert infer(orm_db, school.id) == (None, False)


def test_periods_made_by_hand_from_1_are_regular(orm_db, school):
    """Older schools typed their order in by hand, often from 1. That's a
    different count, not a different day."""
    for d in range(5):
        for o in range(1, 9):
            orm_db.add(Period(school_id=school.id, day_of_week=d, order=o))
    orm_db.commit()
    read, irregular = infer(orm_db, school.id)
    assert read == cfg()
    assert irregular is False


def test_days_that_differ_are_flagged(orm_db, school):
    """Lunch after 4 on Monday but after 5 on Tuesday can't be said as one
    structure; saving the one shown would change Tuesday, so say so."""
    for d, lunch in ((0, 4), (1, 5)):
        for o in range(9):
            orm_db.add(Period(school_id=school.id, day_of_week=d, order=o, kind="break" if o == lunch else "lesson"))
    orm_db.commit()
    read, irregular = infer(orm_db, school.id)
    assert irregular is True
    assert read.periods_per_day == 8

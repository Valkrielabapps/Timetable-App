"""
Checking a timetable against the tick-box rules on the Constraints page.

Typed rules are checked by constraint_ir_checker. The tick boxes have no rule
row to check against, so they are checked here - so a timetable made before a
box was ticked, or a lesson dragged onto a second Maths for the day, is
flagged like any broken rule rather than passing silently.

Only "Keep each subject to one period a day for every class" is checked: it
is exact (two Maths on Monday either happened or didn't), while spreading
teachers out and demanding subjects first are "where the timetable allows"
by design and would flag nearly every timetable.

Where the week has room for one a day (no more periods than the section has
school days), the box is a firm rule - the generator holds to it, see
_add_subject_once_a_day in app/services/solver.py - so a break is reported as
"required". A subject with more periods than days only needs its extras
spread as evenly as they go; missing that is reported as a preference - as is
two on a day for a subject whose teacher a rule keeps off some days, where
the generator only prefers one a day too. A section's subject the school gave
a double-period rule, put on particular days with a rule of its own, or
fixed to periods in Setup, is the school's call and isn't checked.
"""
from __future__ import annotations

from math import ceil

from sqlalchemy.orm import Session

from app.models.school import ClassGroup, Constraint, School, Subject, SubjectRequirement
from app.services import standard_rules
from app.services.constraint_ir import IRError, rule_from_dict
from app.services.constraint_ir_checker import Placement, Violation
from app.services.timetable_structure import grade_off_period_ids

ONE_A_DAY = "Keep each subject to one period a day for every class"
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class OneADay:
    """What checking one school needs, loaded once and reused for every
    "what if" a drag asks."""

    def __init__(self, db: Session, school_id: int, periods: dict, class_groups: dict, subjects: dict):
        from app.services.solver import _class_group_labels, _day_rule_pairs, _double_period_pairs, _teachers_kept_off_days

        school = db.get(School, school_id)
        self.on = bool(school) and standard_rules.for_school(school).subject_spread
        self.class_groups = class_groups
        self.subjects = subjects
        self.per_week: dict[tuple[int, int], int] = {}
        self.days_by_section: dict[int, int] = {}
        self.kept_off: set[int] = set()
        if not self.on:
            return
        requirements = (
            db.query(SubjectRequirement)
            .join(ClassGroup, ClassGroup.id == SubjectRequirement.class_group_id)
            .filter(ClassGroup.school_id == school_id)
            .all()
        )
        rules = []
        for c in db.query(Constraint).filter(Constraint.school_id == school_id, Constraint.type == "ir").all():
            try:
                rules.append(rule_from_dict(c.parameters or {}))
            except IRError:
                continue
        labels = _class_group_labels(list(class_groups.values()))
        from app.models.school import Teacher
        self.kept_off = _teachers_kept_off_days(rules, db.query(Teacher).filter(Teacher.school_id == school_id).all())
        exempt = (_double_period_pairs(rules, requirements, subjects, labels)
                  | _day_rule_pairs(rules, requirements, subjects, labels))
        # Fixed periods (Setup) say exactly when a subject is, two on a
        # Friday included: the school's call, as for a double-period rule.
        for fixed in school.fixed_periods or []:
            grades = set(fixed.get("grades") or [])
            exempt |= {(r.class_group_id, r.subject_id) for r in requirements
                       if r.subject_id == fixed.get("subject_id")
                       and getattr(class_groups.get(r.class_group_id), "grade", None) in grades}
        self.per_week = {
            (r.class_group_id, r.subject_id): r.periods_per_week
            for r in requirements if (r.class_group_id, r.subject_id) not in exempt
        }
        lesson_periods = [p for p in periods.values() if not p.is_break]
        off = grade_off_period_ids(lesson_periods, school.grade_day_limits)
        for cg in class_groups.values():
            gone = off.get(cg.grade, set()) if cg.grade else set()
            self.days_by_section[cg.id] = len({p.day_of_week for p in lesson_periods if p.id not in gone})

    def label(self, cid: int) -> str:
        cg = self.class_groups.get(cid)
        return (f"{cg.grade} {cg.name}" if cg.grade else cg.name) if cg else "A section"

    def check(self, placements: list[Placement], block_entry_ids: set[int] = frozenset()) -> list[Violation]:
        """Every section and subject breaking the box. Elective-block lessons
        (`block_entry_ids`) are left out: a block counts as one lesson
        whichever option a student is in."""
        if not self.on:
            return []
        by_day: dict[tuple[int, int], dict[int, list[Placement]]] = {}
        for p in placements:
            if p.entry_id in block_entry_ids:
                continue
            key = (p.class_group_id, p.subject_id)
            if key not in self.per_week:
                continue
            by_day.setdefault(key, {}).setdefault(p.day_of_week, []).append(p)
        out: list[Violation] = []
        for (cid, sid), days in sorted(by_day.items()):
            per_week = self.per_week[(cid, sid)]
            school_days = self.days_by_section.get(cid) or len(days)
            subject = self.subjects.get(sid)
            name = subject.name if subject else "a subject"
            # One per period, not per teacher: a lab split into batches is one lesson.
            count = {d: len({p.period_id for p in ps}) for d, ps in days.items()}
            # A teacher a rule keeps off some days: one a day is only a preference there.
            kept_off = any(p.teacher_id in self.kept_off for ps in days.values() for p in ps)
            if per_week <= school_days:
                strength, fair = ("preference" if kept_off else "required"), 1
            else:
                strength, fair = "preference", ceil(per_week / school_days)
            for d, n in sorted(count.items()):
                missing_day = per_week > school_days and len(count) < school_days and n > 1
                if n > fair or missing_day:
                    times = "twice" if n == 2 else f"{n} times"
                    out.append(Violation(
                        constraint_id=None, description=ONE_A_DAY, strength=strength,
                        entry_ids=[p.entry_id for p in days[d]],
                        detail=f"{self.label(cid)} has {name} {times} on {_DAYS[d] if 0 <= d < 7 else 'one day'}",
                    ))
        return out


def one_a_day_violations(db: Session, timetable, periods: dict, class_groups: dict | None = None,
                         subjects: dict | None = None) -> list[Violation]:
    """The box checked against a saved timetable's lessons."""
    school_id = timetable.school_id
    class_groups = class_groups or {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    subjects = subjects or {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id)}
    checker = OneADay(db, school_id, periods, class_groups, subjects)
    if not checker.on:
        return []
    placements = [
        Placement(entry_id=e.id, class_group_id=e.class_group_id, subject_id=e.subject_id,
                  teacher_id=e.teacher_id, period_id=e.period_id,
                  day_of_week=periods[e.period_id].day_of_week, order=periods[e.period_id].order)
        for e in timetable.entries if e.period_id in periods
    ]
    return checker.check(placements, {e.id for e in timetable.entries if e.elective_block_id is not None})


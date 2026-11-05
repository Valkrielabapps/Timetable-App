"""
Building a timetable by hand: the lessons a school has to place, who can take
each one, and what placing one by hand would do.

A lesson here is one section's subject (a SubjectRequirement) or one elective
block. The workspace on the Timetable page shows them as cards under a teacher,
so "who can take it" uses the same test as the solver: qualified for the subject
and the grade, narrowed by the plan's chosen teacher or shortlist.

Split labs aren't offered as cards. Each batch needs its own teacher at the same
moment, which one dragged card can't say, so Generate places them.
"""
from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.models.school import (
    ClassGroup, ElectiveBlock, Period, Room, Subject, SubjectRequirement, Teacher, Timetable, TimetableEntry,
)
from app.services.constraint_ir_checker import Placement
from app.services.slot_board import Board
from app.services.subject_freezing import frozen_lessons_index

# How long one forecast may take. It only adds amber to the drag colours, so a
# very large school gets part of the answer rather than a slow request.
FORECAST_BUDGET_SECONDS = 4.0


def _can_teach(teacher: Teacher, subject_id: int, grades: list[str | None]) -> bool:
    if subject_id not in (teacher.qualified_subject_ids or []):
        return False
    allowed = teacher.qualified_grades or []
    return not allowed or any(g in allowed for g in grades)


def lessons_for_school(db: Session, school_id: int) -> list[dict]:
    """Every lesson the school's plan asks for, with who can take it."""
    sections = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()}
    subjects = {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    teachers = db.query(Teacher).filter(Teacher.school_id == school_id).all()
    by_subject, by_block = frozen_lessons_index(db, school_id)

    out: list[dict] = []
    rows = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id.in_(list(sections))).all()
    for r in rows:
        subject = subjects.get(r.subject_id)
        if subject is None:
            continue
        grade = sections[r.class_group_id].grade
        if r.preferred_teacher_id is not None:
            eligible = [r.preferred_teacher_id]
        else:
            eligible = [t.id for t in teachers if _can_teach(t, r.subject_id, [grade])]
            if r.allowed_teacher_ids and len(r.allowed_teacher_ids) > 1:
                eligible = [t for t in eligible if t in r.allowed_teacher_ids]
        out.append({
            "key": f"r{r.id}",
            "kind": "subject",
            "class_group_id": r.class_group_id,
            "section_ids": [r.class_group_id],
            "subject_id": r.subject_id,
            "block_id": None,
            "label": subject.name,
            "detail": None,
            "periods_per_week": r.periods_per_week,
            "teacher_ids": eligible,
            "split": (subject.lab_batch_count or 1) > 1,
            "frozen": by_subject.get((r.class_group_id, r.subject_id)),
            "options": [],
        })

    for b in db.query(ElectiveBlock).filter(ElectiveBlock.school_id == school_id).all():
        ids = [i for i in b.section_ids if i in sections]
        if not ids:
            continue
        options, eligible = [], []
        for o in b.options:
            members = [i for i in o.group_section_ids if i in sections]
            grades = [sections[i].grade for i in members]
            who = [o.preferred_teacher_id] if o.preferred_teacher_id else [
                t.id for t in teachers if _can_teach(t, o.subject_id, grades)
            ]
            subject = subjects.get(o.subject_id)
            options.append({
                "option_id": o.id, "subject_id": o.subject_id, "subject_name": subject.name if subject else "?",
                "label": o.label, "section_ids": members, "preferred_teacher_id": o.preferred_teacher_id,
                "teacher_ids": who,
            })
            eligible.extend(t for t in who if t not in eligible)
        out.append({
            "key": f"b{b.id}",
            "kind": "block",
            "class_group_id": ids[0],
            "section_ids": ids,
            "subject_id": None,
            "block_id": b.id,
            "label": b.name,
            "detail": " / ".join(o["subject_name"] for o in options),
            "periods_per_week": b.periods_per_week,
            "teacher_ids": eligible,
            "split": False,
            "frozen": next((by_block[(i, b.id)] for i in ids if (i, b.id) in by_block), None),
            "options": options,
        })
    return out


def room_for(db: Session, timetable: Timetable, subject: Subject | None, section: ClassGroup, period_id: int,
             taken: set[int]) -> int | None:
    """A free room of the type the subject needs, as the solver's room pass
    would choose. Best effort like that pass: None when there isn't one, or the
    subject doesn't need one."""
    if subject is None or not subject.required_room_type:
        return None
    busy = {rid for (rid,) in db.query(TimetableEntry.room_id).filter(
        TimetableEntry.timetable_id == timetable.id, TimetableEntry.period_id == period_id,
        TimetableEntry.room_id.isnot(None),
    )} | taken
    rooms = db.query(Room).filter(
        Room.school_id == timetable.school_id, Room.room_type == subject.required_room_type,
    ).order_by(Room.name).all()
    for room in rooms:
        too_small = (room.capacity is not None and section.student_count is not None
                     and room.capacity < section.student_count)
        if room.id not in busy and not too_small:
            return room.id
    return None


def _placement(entry_id: int, section: int, subject_id: int, teacher_id: int | None, period: Period) -> Placement:
    return Placement(
        entry_id=entry_id, class_group_id=section, subject_id=subject_id, teacher_id=teacher_id,
        period_id=period.id, day_of_week=period.day_of_week, order=period.order,
        occupies_teacher=teacher_id is not None,
    )


def forecast(db: Session, timetable: Timetable, board: Board, teacher_id: int) -> dict:
    """What dropping this teacher's lessons in each period would break, worked
    out ahead of time so the colours are there the moment a lesson is picked
    up. Only periods that are otherwise free are judged: the browser works out
    double-bookings itself from the timetable it already holds.

        cards  lesson key -> period id -> {"status", "reason"}
        slots  "section:period" -> period id -> {"status", "reason"}

    Periods with nothing to say are left out. Nothing is saved.
    """
    started = time.monotonic()
    out: dict = {"cards": {}, "slots": {}, "partial": False}
    lesson_periods = [p for p in board.periods.values() if not p.is_break]
    if teacher_id not in board.teachers:
        return out

    def over_budget() -> bool:
        if time.monotonic() - started > FORECAST_BUDGET_SECONDS:
            out["partial"] = True
            return True
        return False

    def teacher_free(pid: int) -> bool:
        return not any(e.teacher_id == teacher_id for e in board.by_period.get(pid, []))

    if board.rules:
        for lesson in lessons_for_school(db, timetable.school_id):
            if teacher_id not in lesson["teacher_ids"] or lesson["split"]:
                continue
            if over_budget():
                return out
            here: dict = {}
            for p in lesson_periods:
                if not teacher_free(p.id) or any(board.at.get((sid, p.id)) for sid in lesson["section_ids"]):
                    continue
                if lesson["kind"] == "subject":
                    extra = [_placement(-1, lesson["class_group_id"], lesson["subject_id"], teacher_id, p)]
                else:
                    extra = [
                        _placement(-1 - n, sid, o["subject_id"], teacher_id if teacher_id in o["teacher_ids"] else None, p)
                        for n, o in enumerate(lesson["options"]) for sid in o["section_ids"]
                    ]
                names = board.rules_broken_by(extra)
                if names:
                    here[p.id] = {"status": "warn", "reason": "; ".join(names)}
            if here:
                out["cards"][lesson["key"]] = here

    slots = {(e.class_group_id, board.pid[e.id]) for e in board.entries if e.teacher_id == teacher_id}
    for section, src in sorted(slots):
        if over_budget():
            return out
        here = {}
        for p in lesson_periods:
            if p.id == src or board.at.get((section, p.id)):
                continue
            verdict = board.judge(section, src, p.id)
            if verdict.status != "ok":
                here[p.id] = {"status": verdict.status, "reason": verdict.reason}
        if here:
            out["slots"][f"{section}:{src}"] = here
    return out

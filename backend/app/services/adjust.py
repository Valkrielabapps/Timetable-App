"""
Small changes to a timetable without rebuilding it.

Mid-year a teacher leaves, a section gets one more Maths period, a subject
changes hands. Rebuilding the whole timetable for that moves every lesson in
the school and disturbs every teacher's routine. Instead:

  plan_changes()     what the plan now says that the timetable doesn't:
                     a subject with more or fewer periods than it has, a
                     lesson whose teacher is no longer the one planned or
                     can't be there then, a subject or section that's new
                     or gone. Each names the sections and teachers it
                     touches.

  replace_teacher()  "Ravi instead of Anil": the plan changes, and in the
                     timetable Ravi takes each of Anil's lessons where he is
                     free - straight away, nothing else moves. The lessons he
                     can't take at that time are left for an update.

  update (the generation job, app/routers/timetables.py) keeps every lesson
  that's still right (solver UPDATE_MODE), so only what changed is placed.
  If that can't fit, it frees just the sections and teachers the changes
  touch; only if that fails too is the timetable built again from scratch.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from sqlalchemy.orm import Session

from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Subject, SubjectRequirement, Teacher, Timetable, TimetableEntry,
)


def _label(cg: ClassGroup | None) -> str:
    if cg is None:
        return "a section"
    return f"{cg.grade} {cg.name}".strip() if cg.grade else cg.name


def plan_changes(db: Session, school_id: int, timetable: Timetable | None) -> dict:
    """{"changes": [{"text", "class_group_id", "teacher_ids"}], "sections": [...], "teachers": [...]}"""
    out = {"changes": [], "sections": [], "teachers": []}
    if timetable is None or timetable.status != "draft":
        return out
    groups = {g.id: g for g in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    subjects = {s.id: s.name for s in db.query(Subject).filter(Subject.school_id == school_id)}
    teachers = {t.id: t for t in db.query(Teacher).filter(Teacher.school_id == school_id)}
    reqs = (db.query(SubjectRequirement).join(ClassGroup, ClassGroup.id == SubjectRequirement.class_group_id)
            .filter(ClassGroup.school_id == school_id).all())
    blocks = db.query(ElectiveBlock).filter(ElectiveBlock.school_id == school_id).all()
    entries = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == timetable.id).all()
    sections: set[int] = set()
    touched: set[int] = set()

    def add(text: str, cg_id: int | None, teacher_ids=()):
        out["changes"].append({"text": text, "class_group_id": cg_id, "teacher_ids": [t for t in teacher_ids if t]})
        if cg_id:
            sections.add(cg_id)
        touched.update(t for t in teacher_ids if t)

    plain = [e for e in entries if e.elective_block_id is None]
    by_req = defaultdict(list)
    for e in plain:
        by_req[(e.class_group_id, e.subject_id)].append(e)
    planned = {(r.class_group_id, r.subject_id): r for r in reqs}

    for key, r in planned.items():
        have = by_req.get(key, [])
        cg = groups.get(r.class_group_id)
        name = subjects.get(r.subject_id, "A subject")
        # A split lab has one entry per batch for each lesson.
        lessons = len({e.period_id for e in have})
        if lessons != r.periods_per_week:
            teacher_ids = {e.teacher_id for e in have} | {r.preferred_teacher_id}
            if lessons == 0:
                add(f"{_label(cg)}: {name} is new ({r.periods_per_week} a week)", r.class_group_id, teacher_ids)
            else:
                add(f"{_label(cg)}: {name} {lessons} → {r.periods_per_week} periods a week", r.class_group_id, teacher_ids)
        allowed = ({r.preferred_teacher_id} if r.preferred_teacher_id else set(r.allowed_teacher_ids or [])) or None
        wrong = {e.teacher_id for e in have if e.teacher_id and allowed and e.teacher_id not in allowed}
        if wrong:
            new = teachers.get(r.preferred_teacher_id)
            add(f"{_label(cg)}: {name} now taught by "
                f"{new.name if new else ' or '.join(teachers[t].name for t in allowed if t in teachers)}"
                f" (was {', '.join(teachers[t].name for t in wrong if t in teachers)})",
                r.class_group_id, wrong | (allowed or set()))
        if any(e.teacher_id is None for e in have) and (r.preferred_teacher_id or r.allowed_teacher_ids):
            add(f"{_label(cg)}: {name} has a teacher now", r.class_group_id, allowed or ())
    for key, have in by_req.items():
        if key not in planned:
            cg = groups.get(key[0])
            add(f"{_label(cg)}: {subjects.get(key[1], 'a subject')} is no longer in the plan",
                key[0], {e.teacher_id for e in have})

    # Elective blocks: the right number of periods, and each group's teacher.
    block_entries = defaultdict(list)
    for e in entries:
        if e.elective_block_id is not None:
            block_entries[e.elective_block_id].append(e)
    for b in blocks:
        have = block_entries.get(b.id, [])
        n = len({e.period_id for e in have})
        if n != b.periods_per_week:
            add(f"{_label(groups.get(b.class_group_id))}: {b.name} {n} → {b.periods_per_week} periods a week",
                b.class_group_id, {e.teacher_id for e in have} | {o.preferred_teacher_id for o in b.options})
        planned_teacher = {o.id: o.preferred_teacher_id for o in b.options}
        wrong = {e.teacher_id for e in have
                 if e.elective_option_id in planned_teacher and planned_teacher[e.elective_option_id]
                 and e.teacher_id != planned_teacher[e.elective_option_id]}
        if wrong:
            add(f"{_label(groups.get(b.class_group_id))}: {b.name} has a new teacher", b.class_group_id,
                wrong | set(planned_teacher.values()))

    # A teacher now away when one of their lessons is.
    for e in entries:
        t = teachers.get(e.teacher_id)
        if t and e.period_id in set(t.unavailable_period_ids or []):
            add(f"{t.name} is no longer free when they teach {_label(groups.get(e.class_group_id))} "
                f"{subjects.get(e.subject_id, '')}".rstrip(), e.class_group_id, {t.id})

    with_lessons = {e.class_group_id for e in entries}
    for g in groups.values():
        if g.id not in with_lessons and any(r.class_group_id == g.id for r in reqs):
            add(f"{_label(g)} is a new section", g.id)

    # One line per change is enough: the same text from two lessons is one.
    seen, uniq = set(), []
    for c in out["changes"]:
        if c["text"] not in seen:
            seen.add(c["text"])
            uniq.append(c)
    out["changes"] = uniq
    out["sections"] = sorted(sections)
    out["teachers"] = sorted(touched)
    return out


def replace_teacher(db: Session, school_id: int, old_id: int, new_id: int, timetable: Timetable | None,
                    class_group_ids: list[int] | None = None) -> dict:
    """Put `new` in `old`'s place in the plan (for these sections, or all),
    and in the timetable wherever `new` is free then. Commits.
    Returns {"swapped": n, "left": n, "plan": n}."""
    old, new = db.get(Teacher, old_id), db.get(Teacher, new_id)
    if not old or not new or old.school_id != school_id or new.school_id != school_id or old.id == new.id:
        raise ValueError("Choose two different teachers of this school.")
    only = set(class_group_ids or [])
    groups = {g.id: g for g in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}

    def in_scope(cg_id):
        return not only or cg_id in only

    def qualify(subject_id, grade):
        ids = list(new.qualified_subject_ids or [])
        if subject_id not in ids:
            new.qualified_subject_ids = ids + [subject_id]
        gs = list(new.qualified_grades or [])
        if gs and grade and grade not in gs:
            new.qualified_grades = gs + [grade]

    plan_changes_made = 0
    reqs = (db.query(SubjectRequirement).join(ClassGroup, ClassGroup.id == SubjectRequirement.class_group_id)
            .filter(ClassGroup.school_id == school_id).all())
    for r in reqs:
        if not in_scope(r.class_group_id):
            continue
        hit = False
        if r.preferred_teacher_id == old.id:
            r.preferred_teacher_id = new.id
            hit = True
        if r.allowed_teacher_ids and old.id in r.allowed_teacher_ids:
            ids = [new.id if t == old.id else t for t in r.allowed_teacher_ids]
            r.allowed_teacher_ids = list(dict.fromkeys(ids))
            if len(r.allowed_teacher_ids) == 1:
                r.preferred_teacher_id, r.allowed_teacher_ids = r.allowed_teacher_ids[0], None
            hit = True
        if r.assistant_teacher_id == old.id:
            r.assistant_teacher_id = new.id
        if hit:
            qualify(r.subject_id, groups[r.class_group_id].grade)
            plan_changes_made += 1
    for o in (db.query(ElectiveOption).join(ElectiveBlock, ElectiveBlock.id == ElectiveOption.block_id)
              .filter(ElectiveBlock.school_id == school_id, ElectiveOption.preferred_teacher_id == old.id).all()):
        if in_scope(o.block.class_group_id):
            o.preferred_teacher_id = new.id
            qualify(o.subject_id, groups[o.block.class_group_id].grade)
            plan_changes_made += 1
    for g in groups.values():
        if g.class_teacher_id == old.id and in_scope(g.id):
            g.class_teacher_id = new.id

    swapped = left = 0
    if timetable is not None and timetable.status == "draft":
        entries = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == timetable.id).all()
        busy = Counter(e.period_id for e in entries if e.teacher_id == new.id)
        away = set(new.unavailable_period_ids or [])
        for e in entries:
            if e.teacher_id != old.id or not in_scope(e.class_group_id):
                continue
            if busy[e.period_id] == 0 and e.period_id not in away:
                e.teacher_id = new.id
                busy[e.period_id] += 1
                swapped += 1
            else:
                left += 1
            if e.assistant_teacher_id == old.id:
                e.assistant_teacher_id = new.id
    db.commit()
    return {"swapped": swapped, "left": left, "plan": plan_changes_made}

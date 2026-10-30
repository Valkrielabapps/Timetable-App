"""
Freezing a subject: keeping one subject's lessons exactly where they are -
same periods, teachers and rooms - while everything else is regenerated
around them.

Where freezing a section (app/services/freezing.py) takes the section out of
the solve altogether, a frozen subject's sections are still solved: only
that subject's lessons in them are pinned, through the same machinery as a
locked lesson (generate_school_timetable in app/services/solver.py).

The scope is chosen when freezing - the whole school, some grades, or some
sections - and fixed then: a section added later gets the subject placed
normally. A section that is itself frozen is kept whole, so a subject freeze
doesn't touch it.

A subject taught in an elective block can be frozen on its own (its lessons,
and so the block's periods, are kept; the other subjects' teachers can
change) or with its whole block (every subject in the block kept).

What was frozen is checked against the plan as it is now:
  - more periods a week than when frozen: the frozen lessons are kept and
    the extra ones placed around them, with a note;
  - fewer periods, a different teacher, the subject gone from the section,
    lessons lost to a change of the week's structure, a teacher removed:
    the freeze is out of date. It is not quietly changed - generating says
    so and asks for it to be unfrozen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session, object_session

from app.models.school import ClassGroup, Subject, SubjectFreeze, Teacher, Timetable, TimetableEntry
from app.services.elective_sections import blocks_for_sections, options_for_section
from app.services.freezing import FreezeError, section_label
from app.services.naming import name_sort_key

SCOPES = ("school", "grades", "sections")
BLOCK_MODES = ("subject", "block")


def _plan(cg: ClassGroup, subject_id: int) -> dict | None:
    """What the section's plan says about the subject, or None if it has none."""
    for r in cg.requirements:
        if r.subject_id == subject_id:
            return {"periods": r.periods_per_week, "teacher": r.preferred_teacher_id, "block_id": None}
    # Blocks the section joins count too, but only the groups its own students
    # are in.
    session = object_session(cg)
    blocks = blocks_for_sections(session, [cg.id]) if session is not None else list(cg.elective_blocks)
    for b in blocks:
        for o in options_for_section(b, cg.id):
            if o.subject_id == subject_id:
                return {
                    "periods": b.periods_per_week, "teacher": o.preferred_teacher_id, "block_id": b.id,
                    "block_options": sorted([op.subject_id, op.preferred_teacher_id or 0] for op in b.options),
                }
    return None


def _kept(entries, cg_id: int, subject_id: int, block_id: int | None, block_mode: str) -> list[TimetableEntry]:
    """The section's lessons a freeze keeps, out of a version's entries."""
    if block_id is not None and block_mode == "block":
        return [e for e in entries if e.class_group_id == cg_id and e.elective_block_id == block_id]
    return [e for e in entries if e.class_group_id == cg_id and e.subject_id == subject_id]


def _sections_in_scope(db: Session, school_id: int, scope: str, grades, class_group_ids) -> list[ClassGroup]:
    sections = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    if scope == "school":
        return sections
    if scope == "grades":
        wanted = set(grades or [])
        if not wanted:
            raise FreezeError("Choose at least one grade.")
        return [cg for cg in sections if cg.grade in wanted]
    wanted = set(class_group_ids or [])
    if not wanted:
        raise FreezeError("Choose at least one section.")
    chosen = [cg for cg in sections if cg.id in wanted]
    if len(chosen) != len(wanted):
        raise LookupError("Section not found")
    return chosen


def _names(labels) -> str:
    labels = sorted(labels, key=name_sort_key)
    shown = ", ".join(labels[:6])
    return shown + (f" and {len(labels) - 6} more" if len(labels) > 6 else "")


def freeze_subject(
    db: Session, school_id: int, subject_id: int, scope: str = "school",
    grades: list[str] | None = None, class_group_ids: list[int] | None = None, block_mode: str = "subject",
) -> SubjectFreeze:
    """Freeze a subject's lessons in the current version. Commits."""
    from app.services.versions import current_version

    subject = db.get(Subject, subject_id)
    if subject is None or subject.school_id != school_id:
        raise LookupError("Subject not found")
    if scope not in SCOPES:
        raise FreezeError("Choose the whole school, some grades or some sections.")
    if block_mode not in BLOCK_MODES:
        raise FreezeError("Choose to freeze just the subject or its whole elective block.")
    source = current_version(db, school_id)
    if source is None:
        raise FreezeError("Generate a timetable before freezing - there's nothing to keep yet.")

    sections = [
        cg for cg in _sections_in_scope(db, school_id, scope, grades, class_group_ids)
        if _plan(cg, subject_id) is not None
    ]
    if not sections:
        raise FreezeError(f"None of the sections chosen have {subject.name}.")

    taken = {}
    for f in db.query(SubjectFreeze).filter(SubjectFreeze.school_id == school_id, SubjectFreeze.subject_id == subject_id):
        for cg_id in f.class_group_ids or []:
            taken[cg_id] = f
    already = [section_label(cg) for cg in sections if cg.id in taken]
    if already:
        raise FreezeError(
            f"{subject.name} is already frozen for {_names(already)}. Unfreeze it there first to freeze it again."
        )

    entries = list(source.entries)
    snapshot = {}
    empty = []
    for cg in sections:
        plan = _plan(cg, subject_id)
        kept = _kept(entries, cg.id, subject_id, plan["block_id"], block_mode)
        if not kept:
            empty.append(section_label(cg))
            continue
        snapshot[str(cg.id)] = {**plan, "lessons": len(kept)}
    if empty:
        raise FreezeError(
            f"{subject.name} has no lessons yet for {_names(empty)} in this version. "
            f"Generate a timetable for {'it' if len(empty) == 1 else 'them'} before freezing."
        )

    freeze = SubjectFreeze(
        school_id=school_id, subject_id=subject_id, scope=scope,
        grades=sorted(set(grades or []), key=name_sort_key) if scope == "grades" else None,
        class_group_ids=sorted(cg.id for cg in sections),
        block_mode=block_mode, from_timetable_id=source.id, frozen_at=datetime.now(timezone.utc),
        snapshot=snapshot,
    )
    db.add(freeze)
    db.commit()
    db.refresh(freeze)
    return freeze


def unfreeze_subject(db: Session, school_id: int, freeze_id: int) -> None:
    freeze = db.get(SubjectFreeze, freeze_id)
    if freeze is None or freeze.school_id != school_id:
        raise LookupError("Frozen subject not found")
    db.delete(freeze)
    db.commit()


@dataclass
class _Check:
    stale: list[str] = field(default_factory=list)   # "Grade 11 - A: its Physics went from 6 to 5 periods a week."
    notes: list[str] = field(default_factory=list)   # extra periods to be placed around the frozen ones
    kept: dict[int, list[TimetableEntry]] = field(default_factory=dict)  # class_group_id -> lessons to pin


def check(db: Session, freeze: SubjectFreeze, sections: dict[int, ClassGroup] | None = None,
          teacher_ids: set[int] | None = None) -> _Check:
    """The freeze against the plan as it is now: what's out of date, what's
    noted, and which lessons it keeps."""
    out = _Check()
    subject = db.get(Subject, freeze.subject_id)
    name = subject.name if subject else "The subject"
    source = db.get(Timetable, freeze.from_timetable_id)
    if source is None or source.school_id != freeze.school_id:
        out.stale.append("The version it was frozen from no longer exists.")
        return out
    if sections is None:
        sections = {cg.id: cg for cg in db.query(ClassGroup).filter(ClassGroup.school_id == freeze.school_id)}
    if teacher_ids is None:
        teacher_ids = {t.id for t in db.query(Teacher.id).filter(Teacher.school_id == freeze.school_id)}
    entries = list(source.entries)

    for cg_id_text, snap in (freeze.snapshot or {}).items():
        cg = sections.get(int(cg_id_text))
        if cg is None:
            continue  # the section was deleted; nothing left to keep
        if cg.frozen:
            continue  # kept whole as a frozen section
        label = section_label(cg)
        plan = _plan(cg, freeze.subject_id)
        if plan is None:
            out.stale.append(f"{label} no longer has {name}.")
            continue
        if plan["block_id"] != snap.get("block_id"):
            moved = (
                "into an elective block" if snap.get("block_id") is None
                else "out of its elective block" if plan["block_id"] is None
                else "to a different elective block"
            )
            out.stale.append(f"{label}'s {name} has moved {moved}.")
            continue
        if plan["periods"] < snap["periods"]:
            out.stale.append(f"{label}'s {name} went from {snap['periods']} to {plan['periods']} periods a week.")
            continue
        if plan["teacher"] != snap.get("teacher"):
            out.stale.append(f"{label}'s {name} teacher was changed.")
            continue
        if freeze.block_mode == "block" and plan["block_id"] is not None \
                and plan.get("block_options") != snap.get("block_options"):
            out.stale.append(f"The subjects or teachers in {label}'s elective block with {name} changed.")
            continue
        kept = _kept(entries, cg.id, freeze.subject_id, plan["block_id"], freeze.block_mode)
        if len(kept) < snap["lessons"]:
            out.stale.append(f"Some of {label}'s {name} lessons were removed when the week's structure changed.")
            continue
        if any(e.teacher_id is not None and e.teacher_id not in teacher_ids for e in kept):
            out.stale.append(f"A teacher of {label}'s frozen {name} lessons has been removed.")
            continue
        extra = plan["periods"] - snap["periods"]
        if extra > 0:
            out.notes.append(
                f"{label} now has {extra} more period{'' if extra == 1 else 's'} of {name} a week than when it "
                f"was frozen; {'it is' if extra == 1 else 'they are'} placed around the frozen ones."
            )
        out.kept[cg.id] = kept
    return out


@dataclass
class Pins:
    """What the solver pins for frozen subjects. See generate_school_timetable."""
    entries: list[TimetableEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # (class_group_id, subject_id) pairs and (class_group_id, block_id) pairs
    # the pins cover, so a lock on the same lessons doesn't pull the other way.
    pairs: set[tuple[int, int]] = field(default_factory=set)
    blocks: set[tuple[int, int]] = field(default_factory=set)


def pinned_lessons(db: Session, school_id: int) -> Pins:
    from app.services.versions import label as version_label

    pins = Pins()
    freezes = db.query(SubjectFreeze).filter(SubjectFreeze.school_id == school_id).order_by(SubjectFreeze.id).all()
    if not freezes:
        return pins
    sections = {cg.id: cg for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    teacher_ids = {t.id for t in db.query(Teacher.id).filter(Teacher.school_id == school_id)}
    for freeze in freezes:
        subject = db.get(Subject, freeze.subject_id)
        name = subject.name if subject else "A subject"
        result = check(db, freeze, sections, teacher_ids)
        if result.stale:
            pins.errors.append(
                f"{name} is frozen, but it has changed since: {' '.join(result.stale)} "
                f"Unfreeze {name} to regenerate it with the change."
            )
            continue
        pins.notes.extend(result.notes)
        for cg_id, kept in result.kept.items():
            pins.entries.extend(kept)
            pins.pairs.add((cg_id, freeze.subject_id))
            if freeze.block_mode == "block":
                pins.blocks.update((cg_id, e.elective_block_id) for e in kept if e.elective_block_id is not None)
        if result.kept:
            source = db.get(Timetable, freeze.from_timetable_id)
            n = len(result.kept)
            pins.notes.append(
                f"{name}{' and its elective blocks' if freeze.block_mode == 'block' and any(e.elective_block_id for k in result.kept.values() for e in k) else ''} "
                f"kept as frozen in {n} section{'' if n == 1 else 's'}, from {version_label(source)}."
            )
    return pins


def scope_label(db: Session, freeze: SubjectFreeze) -> str:
    if freeze.scope == "school":
        return "Whole school"
    if freeze.scope == "grades":
        return ", ".join(freeze.grades or [])
    sections = db.query(ClassGroup).filter(ClassGroup.id.in_(freeze.class_group_ids or [])).all()
    return _names([section_label(cg) for cg in sections])


def status(db: Session, school_id: int) -> list[dict]:
    from app.services.versions import label as version_label

    out = []
    sections = {cg.id: cg for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)}
    teacher_ids = {t.id for t in db.query(Teacher.id).filter(Teacher.school_id == school_id)}
    for freeze in db.query(SubjectFreeze).filter(SubjectFreeze.school_id == school_id).all():
        subject = db.get(Subject, freeze.subject_id)
        source = db.get(Timetable, freeze.from_timetable_id)
        result = check(db, freeze, sections, teacher_ids)
        in_blocks = any(snap.get("block_id") for snap in (freeze.snapshot or {}).values())
        out.append({
            "id": freeze.id,
            "subject_id": freeze.subject_id,
            "subject": subject.name if subject else "?",
            "scope": freeze.scope,
            "scope_label": scope_label(db, freeze),
            "grades": freeze.grades,
            "class_group_ids": [i for i in freeze.class_group_ids or [] if i in sections],
            "section_count": sum(1 for i in freeze.class_group_ids or [] if i in sections),
            "block_mode": freeze.block_mode,
            "in_blocks": in_blocks,
            "frozen_at": freeze.frozen_at,
            "frozen_from": version_label(source) if source else None,
            "frozen_from_timetable_id": freeze.from_timetable_id,
            "stale_reasons": result.stale,
            "notes": result.notes,
        })
    out.sort(key=lambda f: name_sort_key(f["subject"]))
    return out


def frozen_lessons_index(db: Session, school_id: int) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    """(class_group_id, subject_id) -> subject name, and (class_group_id,
    block_id) -> subject name, for every lesson a subject freeze keeps - so
    editing one can be refused with a reason."""
    by_subject: dict[tuple[int, int], str] = {}
    by_block: dict[tuple[int, int], str] = {}
    for freeze in db.query(SubjectFreeze).filter(SubjectFreeze.school_id == school_id):
        subject = db.get(Subject, freeze.subject_id)
        name = subject.name if subject else "This subject"
        for cg_id_text, snap in (freeze.snapshot or {}).items():
            by_subject[(int(cg_id_text), freeze.subject_id)] = name
            if freeze.block_mode == "block" and snap.get("block_id"):
                by_block[(int(cg_id_text), snap["block_id"])] = name
    return by_subject, by_block


def sources(db: Session, school_id: int) -> dict[int, list[str]]:
    """timetable id -> the subjects frozen from it, so the version is kept."""
    out: dict[int, list[str]] = {}
    for freeze in db.query(SubjectFreeze).filter(SubjectFreeze.school_id == school_id):
        subject = db.get(Subject, freeze.subject_id)
        out.setdefault(freeze.from_timetable_id, []).append(subject.name if subject else "a subject")
    return out

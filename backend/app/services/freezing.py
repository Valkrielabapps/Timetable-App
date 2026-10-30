"""
Freezing a section's timetable.

A school builds its timetable a grade at a time: settle the seniors, then fit
everyone else around them. Freezing is what makes that possible. A frozen
section's lessons are copied unchanged into every later generation as fixed
facts - its teachers busy, its rooms taken, every rule still counting them -
and the solver places only the sections that aren't frozen. See
generate_school_timetable in app/services/solver.py.

Freezing promises the timetable won't change, so when something it was built
from does change - a subject's periods, an elective block, a lesson lost when
the week's structure changed - the section is flagged as out of date rather
than quietly regenerated. Unfreezing is how it gets regenerated.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session, object_session

from app.models.school import ClassGroup, Timetable, TimetableEntry
from app.services.elective_sections import blocks_for_sections


class FreezeError(ValueError):
    """A freeze that can't be done, with a reason meant for a person."""


def section_label(cg: ClassGroup) -> str:
    return f"{cg.grade} - {cg.name}" if cg.grade else cg.name


def plan_signature(cg: ClassGroup) -> str:
    """A fingerprint of what the section's timetable is built from.

    Its subjects and how many periods each, who is pinned to teach them, and
    its elective blocks. Anything that would make the solver place the section
    differently changes this.
    """
    plan = {
        "requirements": sorted(
            (r.subject_id, r.periods_per_week, r.preferred_teacher_id, r.assistant_teacher_id)
            for r in cg.requirements
        ),
        "blocks": sorted(
            (b.periods_per_week, sorted((o.subject_id, o.preferred_teacher_id) for o in b.options))
            for b in cg.elective_blocks if len(b.section_ids) == 1
        ),
    }
    # Blocks shared with other sections, made here or joined: who else is in
    # them and which group each subject is changes this section's timetable too.
    session = object_session(cg)
    shared = [b for b in blocks_for_sections(session, [cg.id]) if len(b.section_ids) > 1] if session else []
    if shared:
        plan["shared_blocks"] = sorted(
            (b.periods_per_week, sorted(b.section_ids), sorted(
                (o.subject_id, o.preferred_teacher_id, o.label or "", sorted(o.group_section_ids))
                for o in b.options
            ))
            for b in shared
        )
    return hashlib.sha1(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()[:16]


def latest_draft(db: Session, school_id: int) -> Timetable | None:
    """The version on screen - the school's current version, which is the one a
    section is frozen from. See app/services/versions.py."""
    from app.services.versions import current_version
    return current_version(db, school_id)


def frozen_source(db: Session, cg: ClassGroup) -> Timetable | None:
    """The version a frozen section is kept from: the one it was frozen in,
    falling back to the current version for sections frozen before versions
    were tracked."""
    if cg.frozen_from_timetable_id:
        t = db.get(Timetable, cg.frozen_from_timetable_id)
        if t is not None and t.school_id == cg.school_id:
            return t
    return latest_draft(db, cg.school_id)


def _lesson_counts(db: Session, timetable: Timetable | None) -> dict[int, int]:
    if timetable is None:
        return {}
    rows = (
        db.query(TimetableEntry.class_group_id, func.count(TimetableEntry.id))
        .filter(TimetableEntry.timetable_id == timetable.id)
        .group_by(TimetableEntry.class_group_id)
        .all()
    )
    return dict(rows)


def staleness(db: Session, school_id: int, class_groups: list[ClassGroup]) -> dict[int, str]:
    """class_group_id -> why a frozen section is out of date, for those that are.

    Two things go out of date without anyone touching the timetable: the plan
    it was built from, and lessons removed when the week's structure changed
    (saving a structure deletes lessons in periods that no longer exist).
    """
    frozen = [cg for cg in class_groups if cg.frozen]
    if not frozen:
        return {}
    counts_by_source: dict = {}
    out: dict[int, str] = {}
    for cg in frozen:
        source = frozen_source(db, cg)
        key = source.id if source else None
        if key not in counts_by_source:
            counts_by_source[key] = _lesson_counts(db, source)
        counts = counts_by_source[key]
        if cg.frozen_signature and plan_signature(cg) != cg.frozen_signature:
            out[cg.id] = (
                "Its plan has changed since it was frozen - unfreeze it to regenerate it with the change."
            )
        elif cg.frozen_lessons is not None and counts.get(cg.id, 0) != cg.frozen_lessons:
            out[cg.id] = (
                "Some of its lessons were removed when the week's structure changed - unfreeze it "
                "to regenerate it."
            )
    return out


def set_frozen(db: Session, school_id: int, class_group_ids: list[int], frozen: bool) -> list[ClassGroup]:
    """Freeze or unfreeze these sections. Commits.

    Freezing needs a timetable to keep: a section with no lessons in the
    current timetable has nothing to freeze, and freezing it anyway would
    promise something the next generation can't keep.
    """
    sections = (
        db.query(ClassGroup)
        .filter(ClassGroup.school_id == school_id, ClassGroup.id.in_(class_group_ids))
        .all()
    )
    if len(sections) != len(set(class_group_ids)):
        raise LookupError("Section not found")

    if frozen:
        timetable = latest_draft(db, school_id)
        counts = _lesson_counts(db, timetable)
        empty = [section_label(cg) for cg in sections if not counts.get(cg.id)]
        if empty:
            raise FreezeError(
                f"Generate a timetable for {', '.join(sorted(empty))} before freezing "
                f"{'it' if len(empty) == 1 else 'them'} - there's nothing to keep yet."
            )
        now = datetime.now(timezone.utc)
        for cg in sections:
            # Freezing an already-frozen section keeps its original moment, so
            # re-applying "freeze grade" doesn't hide an out-of-date section.
            if cg.frozen:
                continue
            cg.frozen = True
            cg.frozen_at = now
            cg.frozen_signature = plan_signature(cg)
            cg.frozen_lessons = counts[cg.id]
            cg.frozen_from_timetable_id = timetable.id
    else:
        for cg in sections:
            cg.frozen = False
            cg.frozen_at = None
            cg.frozen_signature = None
            cg.frozen_lessons = None
            cg.frozen_from_timetable_id = None
    db.commit()
    for cg in sections:
        db.refresh(cg)
    return sections

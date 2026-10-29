"""
Timetable versions.

Every Generate makes a new version. The school always works from one of them,
its *current* version: the Timetable tab shows and edits it, exports and
substitutions read it, and the next generation takes its locked slots from it.
A new successful version becomes current; the admin can open any older one to
make it current again, rename versions, and delete them.

Frozen sections are kept from the version they were frozen in (see
app/services/freezing.py), so that version can't be deleted - or pruned -
while anything is frozen from it.

The newest KEEP_VERSIONS successful versions are kept automatically. Older
ones are removed after each generation, except the current version and any a
frozen section is kept from, which are always kept.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.school import ClassGroup, School, Timetable, TimetableEntry

KEEP_VERSIONS = 5
USABLE = ("draft", "published")


class VersionError(ValueError):
    """Something the admin asked for that can't be done, said for a person."""


def label(t: Timetable) -> str:
    base = f"Version {t.version_number}" if t.version_number else f"Version {t.id}"
    return f"{base} ({t.name})" if t.name else base


def current_version(db: Session, school_id: int) -> Timetable | None:
    """The version the school works from: the one it chose, if it still exists
    and finished, else the newest successful one."""
    school = db.get(School, school_id)
    if school is not None and school.current_timetable_id:
        t = db.get(Timetable, school.current_timetable_id)
        if t is not None and t.school_id == school_id and t.status in USABLE:
            return t
    return (
        db.query(Timetable)
        .filter(Timetable.school_id == school_id, Timetable.status.in_(USABLE))
        .order_by(Timetable.id.desc())
        .first()
    )


def next_version_number(db: Session, school_id: int) -> int:
    top = db.query(func.max(Timetable.version_number)).filter(Timetable.school_id == school_id).scalar()
    return int(top or 0) + 1


def frozen_sources(db: Session, school_id: int) -> dict[int, list[ClassGroup]]:
    """timetable id -> the frozen sections kept from it."""
    out: dict[int, list[ClassGroup]] = {}
    for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id, ClassGroup.frozen.is_(True)):
        if cg.frozen_from_timetable_id:
            out.setdefault(cg.frozen_from_timetable_id, []).append(cg)
    return out


def set_current(db: Session, timetable: Timetable) -> None:
    if timetable.status not in USABLE:
        raise VersionError("Only a finished timetable can be opened.")
    school = db.get(School, timetable.school_id)
    school.current_timetable_id = timetable.id
    db.commit()


def _section(cg: ClassGroup) -> str:
    return f"{cg.grade} - {cg.name}" if cg.grade else cg.name


def delete_version(db: Session, timetable: Timetable) -> None:
    """Delete one version and its lessons. Commits."""
    if timetable.status == "generating":
        raise VersionError("This version is still being generated. Wait for it to finish, then delete it.")
    from app.services import subject_freezing

    kept_from = [_section(cg) for cg in frozen_sources(db, timetable.school_id).get(timetable.id, [])]
    kept_from += subject_freezing.sources(db, timetable.school_id).get(timetable.id, [])
    if kept_from:
        names = ", ".join(sorted(set(kept_from)))
        raise VersionError(
            f"{names} {'is' if len(kept_from) == 1 else 'are'} frozen from this version. "
            f"Unfreeze {'it' if len(kept_from) == 1 else 'them'} first, or freeze from another version."
        )
    school = db.get(School, timetable.school_id)
    was_current = school is not None and school.current_timetable_id == timetable.id
    db.query(TimetableEntry).filter(TimetableEntry.timetable_id == timetable.id).delete(synchronize_session=False)
    db.delete(timetable)
    db.flush()
    if was_current:
        newest = (
            db.query(Timetable)
            .filter(Timetable.school_id == timetable.school_id, Timetable.status.in_(USABLE))
            .order_by(Timetable.id.desc())
            .first()
        )
        school.current_timetable_id = newest.id if newest else None
    db.commit()


def prune(db: Session, school_id: int) -> None:
    """Keep the newest KEEP_VERSIONS successful versions, plus the current one
    and any a frozen section is kept from. Failed runs are kept only while they
    are the newest thing the school did (so the reason can be read). Commits."""
    rows = (
        db.query(Timetable.id, Timetable.status)
        .filter(Timetable.school_id == school_id)
        .order_by(Timetable.id.desc())
        .all()
    )
    if not rows:
        return
    keep = {rows[0].id}
    keep.update([r.id for r in rows if r.status in USABLE][:KEEP_VERSIONS])
    current = current_version(db, school_id)
    if current is not None:
        keep.add(current.id)
    keep.update(frozen_sources(db, school_id))
    from app.services import subject_freezing
    keep.update(subject_freezing.sources(db, school_id))
    doomed = [r.id for r in rows if r.status in ("draft", "failed") and r.id not in keep]
    if not doomed:
        return
    db.query(TimetableEntry).filter(TimetableEntry.timetable_id.in_(doomed)).delete(synchronize_session=False)
    db.query(Timetable).filter(Timetable.id.in_(doomed)).delete(synchronize_session=False)
    db.commit()

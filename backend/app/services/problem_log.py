"""Record where schools get stuck, for the Timetablz admin page.

  generation_failed  Generate found no timetable (with the diagnosis shown)
  move_blocked       a drag or a fix that couldn't be made, and why
  setup_error        a setup-check problem certain to stop generation
  support_request    the school pressed "Send to Timetablz support"

Failed generations and support requests carry a snapshot of the school's
whole setup at that moment (see snapshot below), so a problem can be
reproduced after the school has changed things.

Strictly on the side, like app/services/rule_events.py: written in its own
session, every error swallowed after being logged, so recording a problem
can never become one. Repeats are collapsed - the same move refused, or the
same setup problem shown, for the same school within a day is one row.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

_MAX_TEXT = 2000
REPEAT_WINDOW = timedelta(hours=24)
_DEDUPED = {"move_blocked", "setup_error"}


def record(kind: str, summary: str | None, *, school_id: int | None = None, user_id: int | None = None,
           detail: dict | None = None, timetable_id: int | None = None, with_snapshot: bool = False) -> int | None:
    """Returns the new row's id, or None if nothing was written."""
    from app.models.problems import KINDS, ProblemEvent

    if kind not in KINDS or not (summary or "").strip():
        return None
    summary = summary.strip()[:_MAX_TEXT]
    db = None
    try:
        db = SessionLocal()
        if kind in _DEDUPED:
            since = datetime.now(timezone.utc) - REPEAT_WINDOW
            seen = db.query(ProblemEvent.id).filter(
                ProblemEvent.kind == kind, ProblemEvent.school_id == school_id,
                ProblemEvent.summary == summary, ProblemEvent.created_at >= since,
            ).first()
            if seen:
                return None
        row = ProblemEvent(
            kind=kind, summary=summary, school_id=school_id, user_id=user_id,
            detail=detail or None, timetable_id=timetable_id,
            snapshot=snapshot(db, school_id) if with_snapshot and school_id else None,
        )
        db.add(row)
        db.commit()
        return row.id
    except Exception:  # noqa: BLE001 - never let logging break the real request
        logger.exception("could not record problem %s", kind)
        if db is not None:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return None
    finally:
        if db is not None:
            db.close()


def _plain(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def _row(obj, skip=()) -> dict:
    return {c.name: _plain(getattr(obj, c.name)) for c in obj.__table__.columns if c.name not in skip}


def snapshot(db, school_id: int) -> dict:
    """The school's setup as plain data: enough to rebuild it and generate
    again. Timetables themselves aren't included (only which one was
    current), and neither is anything about people beyond teachers' names."""
    from app.models.school import (
        ClassGroup, Constraint, ElectiveBlock, Period, Room, School, Subject, SubjectRequirement, Teacher,
        ZeroPeriod,
    )

    school = db.get(School, school_id)
    if school is None:
        return {}
    cgs = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    cg_ids = [c.id for c in cgs]
    blocks = db.query(ElectiveBlock).filter(ElectiveBlock.school_id == school_id).all()
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "school": {k: _plain(getattr(school, k, None)) for k in (
            "id", "name", "institution_type", "grade_order", "grade_categories", "grade_day_limits",
            "standard_rules", "current_timetable_id", "plan",
        )},
        "periods": [_row(p) for p in db.query(Period).filter(Period.school_id == school_id).all()],
        "zero_periods": [_row(z) for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all()],
        "class_groups": [_row(c) for c in cgs],
        "requirements": [_row(r) for r in db.query(SubjectRequirement)
                         .filter(SubjectRequirement.class_group_id.in_(cg_ids)).all()] if cg_ids else [],
        "subjects": [_row(s) for s in db.query(Subject).filter(Subject.school_id == school_id).all()],
        "teachers": [_row(t, skip=("email",)) for t in db.query(Teacher).filter(Teacher.school_id == school_id).all()],
        "rooms": [_row(r) for r in db.query(Room).filter(Room.school_id == school_id).all()],
        "elective_blocks": [
            {**_row(b), "section_ids": list(b.section_ids), "options": [_row(o) for o in b.options]}
            for b in blocks
        ],
        "constraints": [_row(c) for c in db.query(Constraint).filter(Constraint.school_id == school_id).all()],
    }

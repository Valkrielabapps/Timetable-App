"""
Small changes without rebuilding the timetable - see app/services/adjust.py.

    GET  /api/timetable-updates/changes?school_id=   what the plan says that the timetable doesn't
    POST /api/timetable-updates/update?school_id=    a new version keeping every lesson still right
    POST /api/timetable-updates/replace-teacher      one teacher in another's place, in plan and timetable
"""
import threading
from collections import Counter

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import SessionLocal, get_db
from app.models.school import Timetable, TimetableEntry
from app.models.user import User
from app.routers import timetables as tt
from app.services import adjust, versions
from app.services.solver import KEEP_PLACED, UPDATE_MODE, generate_school_timetable

router = APIRouter(prefix="/api/timetable-updates", tags=["timetable updates"])

_OK = ("optimal", "feasible")


def _current(db: Session, school_id: int):
    return versions.current_version(db, school_id)


@router.get("/changes")
def changes(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    current = _current(db, school_id)
    return {"timetable_id": current.id if current else None, **adjust.plan_changes(db, school_id, current)}


def _key(e) -> tuple:
    return (e.class_group_id, e.subject_id, e.teacher_id, e.period_id, e.elective_block_id)


def _run_update_job(timetable_id: int, school_id: int) -> None:
    info: dict = {}

    def staged(db: Session):
        previous = _current(db, school_id)
        found = adjust.plan_changes(db, school_id, previous)
        info.update(previous_id=previous.id if previous else None, changes=[c["text"] for c in found["changes"]])
        keep = KEEP_PLACED.set(True)
        upd = UPDATE_MODE.set({"sections": set(), "teachers": set()})
        try:
            # 1. Keep every lesson that is still right; place only what changed.
            result, info["stage"] = generate_school_timetable(db, school_id), 1
            if result.status not in _OK and (found["sections"] or found["teachers"]):
                # 2. Free the sections and teachers the changes touch.
                UPDATE_MODE.set({"sections": set(found["sections"]), "teachers": set(found["teachers"])})
                result, info["stage"] = generate_school_timetable(db, school_id), 2
        finally:
            UPDATE_MODE.reset(upd)
            KEEP_PLACED.reset(keep)
        if result.status not in _OK:
            # 3. It can't be done around the rest: build it again.
            result, info["stage"] = generate_school_timetable(db, school_id), 3
        return result

    with tt._GENERATION_SLOTS:
        tt._generate(timetable_id, school_id, solve=staged)
    db = SessionLocal()
    try:
        timetable = db.get(Timetable, timetable_id)
        if timetable is None or timetable.status != "draft":
            return
        before = Counter(_key(e) for e in db.query(TimetableEntry).filter(
            TimetableEntry.timetable_id == info.get("previous_id")))
        after = Counter(_key(e) for e in db.query(TimetableEntry).filter(TimetableEntry.timetable_id == timetable_id))
        unchanged = sum((before & after).values())
        timetable.generation_notes = {
            **(timetable.generation_notes or {}),
            "update": {
                "stage": info.get("stage"),
                "changes": info.get("changes", [])[:30],
                "unchanged": unchanged,
                "placed": sum(after.values()) - unchanged,
                "total": sum(after.values()),
            },
        }
        db.commit()
    except Exception as exc:  # noqa: BLE001 - the timetable itself is saved
        sentry_sdk.capture_exception(exc)
        db.rollback()
    finally:
        db.close()


@router.post("/update", status_code=201)
def update(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """A new version made around the current one: every lesson that's still
    right stays where it is. Poll GET /api/timetables/{id} like a generation."""
    require_school_access(db, current_user, school_id, min_role="admin")
    if _current(db, school_id) is None:
        raise HTTPException(status_code=400, detail="There's no timetable to update yet. Generate one first.")
    tt._refuse_if_generating(db, school_id)
    timetable = Timetable(school_id=school_id, status="generating",
                          version_number=versions.next_version_number(db, school_id))
    db.add(timetable)
    db.commit()
    db.refresh(timetable)
    threading.Thread(target=_run_update_job, args=(timetable.id, school_id), daemon=True).start()
    return tt._to_timetable_out(db, timetable)


class ReplaceIn(BaseModel):
    school_id: int
    from_teacher_id: int
    to_teacher_id: int
    # Only in these sections; none = everywhere.
    class_group_ids: list[int] | None = None


@router.post("/replace-teacher")
def replace_teacher(payload: ReplaceIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    tt._refuse_if_generating(db, payload.school_id)
    current = _current(db, payload.school_id)
    try:
        done = adjust.replace_teacher(db, payload.school_id, payload.from_teacher_id, payload.to_teacher_id,
                                      current, payload.class_group_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    left = adjust.plan_changes(db, payload.school_id, current)
    return {**done, "changes": left["changes"]}

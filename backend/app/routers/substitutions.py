"""
Endpoints for logging same-day teacher substitutions (e.g. "Ms. Iyer is
out today, Mr. Rao is covering her Period 3 class"). See
app/models/school.py's SubstitutionLog docstring — this is a simple audit
log an admin fills in by hand, not something the solver reads.

Cover is saved per date and per part of the school (see
app/services/school_categories.py): saving the primary block's cover for a
date again replaces what was saved for it before. The summary puts a date's
saves together - see app/services/substitution_summary.py.

Note on the access-control pattern here vs. other routers:
require_school_access (app/core/access.py) is a plain function you call
inside a route body with an already-resolved db session and user, e.g.
`require_school_access(db, current_user, school_id)` — it is NOT itself a
FastAPI dependency, so it must never be wrapped in `Depends(...)`. Doing
that was a real bug in an earlier draft of this file: FastAPI tried to
resolve require_school_access's own `db: Session` parameter as request
input, which isn't a valid Pydantic field type, and crashed the whole app
at import time (backend wouldn't start at all, not just this endpoint).
Every other router in this codebase gets `db`/`current_user` from their
own real dependencies first, then calls require_school_access directly —
this file now follows that same pattern.
"""
from datetime import date as date_type
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import ClassGroup, School, SubstitutionLog
from app.models.user import User
from app.schemas.substitutions import SubstitutionLogCreate, SubstitutionLogOut, SubstitutionSummaryOut
from app.services.school_categories import CATEGORY_KEYS, category_of
from app.services.substitution_summary import build_summary, summary_pdf

router = APIRouter(prefix="/api/schools/{school_id}/substitutions", tags=["substitutions"])


def _check_category(category: str | None) -> None:
    if category is not None and category not in CATEGORY_KEYS:
        raise HTTPException(status_code=422, detail=f"Unknown part of the school: {category!r}.")


@router.get("", response_model=List[SubstitutionLogOut])
def list_substitutions(
    school_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all substitution logs for a school, the latest day first."""
    require_school_access(db, current_user, school_id)
    logs = db.query(SubstitutionLog).filter(SubstitutionLog.school_id == school_id).all()
    # Older records have no date; they belong to the day they were saved.
    return sorted(logs, key=lambda log: (log.date or log.created_at.date(), log.created_at), reverse=True)


@router.post("", response_model=SubstitutionLogOut, status_code=201)
def create_substitution(
    school_id: int,
    data: SubstitutionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a day's substitution log. Admin-only, same as every other
    write endpoint in this app (subjects, teachers, constraints, etc.) —
    a viewer can see substitution history but not add to it.

    With a date, this replaces whatever was saved before for the same date
    and part of the school."""
    require_school_access(db, current_user, school_id, min_role="admin")
    _check_category(data.category)
    school = db.get(School, school_id)
    overrides = school.grade_categories or {}
    grades = {
        cg.id: cg.grade
        for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id)
    }
    changes = []
    for change in data.changes:
        row = change.model_dump()
        row["category"] = category_of(grades.get(change.class_group_id), overrides)
        changes.append(row)
    day_of_week = data.date.weekday() if data.date is not None else data.day_of_week

    log = None
    if data.date is not None:
        log = (
            db.query(SubstitutionLog)
            .filter(
                SubstitutionLog.school_id == school_id,
                SubstitutionLog.date == data.date,
                SubstitutionLog.category.is_(None) if data.category is None
                else SubstitutionLog.category == data.category,
            )
            .order_by(SubstitutionLog.id.desc())
            .first()
        )
    if log is None:
        log = SubstitutionLog(school_id=school_id)
        db.add(log)
    log.date = data.date
    log.day_of_week = day_of_week
    log.category = data.category
    log.absences = [a.model_dump() for a in data.absences]
    log.changes = changes
    db.commit()
    db.refresh(log)
    return log


@router.get("/summary", response_model=SubstitutionSummaryOut)
def substitution_summary(
    school_id: int,
    date: date_type,
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """A date's cover - who is away, and who takes each of their lessons -
    for one part of the school, or (no category) the whole school."""
    require_school_access(db, current_user, school_id)
    _check_category(category)
    return build_summary(db, school_id, date, category)


@router.get("/summary.pdf")
def substitution_summary_pdf(
    school_id: int,
    date: date_type,
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The same summary as a PDF, to print or send."""
    require_school_access(db, current_user, school_id)
    _check_category(category)
    summary = build_summary(db, school_id, date, category)
    name = db.get(School, school_id).name
    part = category or "whole-school"
    return Response(
        content=summary_pdf(summary, name),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="substitutions-{date.isoformat()}-{part}.pdf"'},
    )

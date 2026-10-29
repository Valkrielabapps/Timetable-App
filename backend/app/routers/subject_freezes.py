"""
Freezing subjects: keeping one subject's lessons fixed in the sections
chosen while everything else is regenerated. See
app/services/subject_freezing.py.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.subject_freeze import SubjectFreezeCreate, SubjectFreezeOut
from app.services.freezing import FreezeError
from app.services.subject_freezing import freeze_subject, status, unfreeze_subject

router = APIRouter(prefix="/api/subject-freezes", tags=["subject freezes"])


@router.get("", response_model=list[SubjectFreezeOut])
def list_subject_freezes(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Every frozen subject, where it's frozen, the version it's kept from and
    whether it still matches the plan."""
    require_school_access(db, current_user, school_id)
    return status(db, school_id)


@router.post("", response_model=list[SubjectFreezeOut], status_code=201)
def create_subject_freeze(
    payload: SubjectFreezeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Freeze a subject's lessons in the current version. Returns every
    frozen subject."""
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    try:
        freeze_subject(
            db, payload.school_id, payload.subject_id, payload.scope, payload.grades, payload.class_group_ids,
            payload.block_mode,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except FreezeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return status(db, payload.school_id)


@router.delete("/{freeze_id}", response_model=list[SubjectFreezeOut])
def delete_subject_freeze(
    freeze_id: int, school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    """Unfreeze: the subject is placed freely again from the next generation."""
    require_school_access(db, current_user, school_id, min_role="admin")
    try:
        unfreeze_subject(db, school_id, freeze_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return status(db, school_id)

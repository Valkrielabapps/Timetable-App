"""
GET / PUT a school's week as one structure - see
app/services/timetable_structure.py for what it holds and how it becomes
periods.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.timetable_structure import StructureOut, StructureSaveOut, TimetableStructure
from app.services.timetable_structure import StructureError, apply, infer

router = APIRouter(prefix="/api/schools", tags=["timetable structure"])


@router.get("/{school_id}/timetable-structure", response_model=StructureOut)
def get_structure(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    structure, irregular = infer(db, school_id)
    return StructureOut(structure=structure, irregular=irregular)


@router.put("/{school_id}/timetable-structure", response_model=StructureSaveOut)
def save_structure(
    school_id: int,
    payload: TimetableStructure,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_school_access(db, current_user, school_id, min_role="admin")
    try:
        report = apply(db, school_id, payload)
    except StructureError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    structure, _ = infer(db, school_id)
    return StructureSaveOut(structure=structure or payload, report=report)

"""
The short forms a school has confirmed ("MAT" is Mathematics, "BEAUL" is
Beula Rao), listed on the Subjects and Teachers pages so a wrong one can be
removed - or a new one added before an import asks. See services/aliases.py.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import aliases

router = APIRouter(prefix="/api/schools", tags=["short forms"])


class ShortFormIn(BaseModel):
    kind: Literal["subject", "teacher"]
    text: str = Field(min_length=1, max_length=100)
    meaning: str = Field(min_length=1, max_length=100)


@router.get("/{school_id}/short-forms")
def list_short_forms(school_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    from app.services.smart_import import _SUBJECT_ALIASES
    return {"items": aliases.listing(db, school_id), "built_in": len(_SUBJECT_ALIASES)}


@router.post("/{school_id}/short-forms")
def add_short_form(school_id: int, payload: ShortFormIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id, min_role="admin")
    n = aliases.remember_many(db, school_id, [payload.model_dump()], source="manual")
    if not n:
        raise HTTPException(status_code=400, detail="That short form is the name itself, or one the app already "
                                                    "reads that way.")
    db.commit()
    return {"items": aliases.listing(db, school_id)}


@router.delete("/{school_id}/short-forms/{alias_id}")
def delete_short_form(school_id: int, alias_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id, min_role="admin")
    if not aliases.forget(db, school_id, alias_id):
        raise HTTPException(status_code=404, detail="Short form not found")
    return {"items": aliases.listing(db, school_id)}

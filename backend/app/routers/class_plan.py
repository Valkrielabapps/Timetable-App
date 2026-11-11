"""
Every section's weekly plan from the school's allotment sheet - see
app/services/class_plan.py.

    POST /api/class-plan/preview   read the file: the plan and the questions (saves nothing)
    POST /api/class-plan/commit    save the previewed plan with the answers
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import class_plan
from app.services.uploads import read_upload

router = APIRouter(prefix="/api/class-plan", tags=["class plan"])


@router.post("/preview")
async def preview_plan(
    school_id: int = Form(...),
    file: UploadFile = File(...),
    staff_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """staff_file: the school's staff list, optional - short names in the
    file (last year's timetable especially) are matched to the names on it,
    and everyone on it is added as a teacher."""
    require_school_access(db, current_user, school_id, min_role="admin")
    content = await read_upload(file)
    staff = (staff_file.filename, await read_upload(staff_file)) if staff_file and staff_file.filename else None
    try:
        return class_plan.build_preview(db, school_id, file.filename, content, staff_file=staff)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class PlanCommitIn(BaseModel):
    school_id: int
    plan: dict
    answers: dict[str, str] = Field(default_factory=dict)


@router.post("/commit")
def commit_plan(payload: PlanCommitIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    if len(payload.plan.get("tables", [])) > 300:
        raise HTTPException(status_code=400, detail="That plan is too big to save in one go.")
    try:
        return class_plan.commit(db, payload.school_id, payload.plan, payload.answers)
    except class_plan.PlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

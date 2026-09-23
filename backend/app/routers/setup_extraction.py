from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.rate_limit import check_quota
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.setup_extraction import (
    SetupExtractionCommit,
    SetupExtractionCommitOut,
    SetupExtractionPreview,
)
from app.services.bulk_import import import_class_groups, import_subjects, import_teachers
from app.services.setup_extractor import extract_setup_llm, read_spreadsheet_rows

router = APIRouter(prefix="/api/schools/{school_id}/setup-extraction", tags=["setup extraction"])


@router.post("", response_model=SetupExtractionPreview)
async def extract_setup(
    school_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Uploads an arbitrary CSV/.xlsx (a staff list, an old timetable
    export, whatever the admin already has) and asks Claude to identify
    candidate teachers/subjects/class groups in it. Read-only — nothing
    is created here. The admin reviews the result in the frontend and
    POSTs the reviewed subset to /commit to actually create rows. See
    app/services/setup_extractor.py for the extraction contract and
    scope (CSV/.xlsx only, first 200 rows).
    """
    require_school_access(db, current_user, school_id, min_role="admin")
    # The most expensive LLM call in the app - a whole document per
    # request, not a sentence. Deliberately low: a school sets itself up
    # once, so a legitimate admin never approaches this.
    check_quota(f"llm-extract:{current_user.id}", limit=10, window_seconds=3600)
    content = await file.read()
    try:
        rows = read_spreadsheet_rows(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    extracted = extract_setup_llm(rows)
    if extracted is None:
        raise HTTPException(
            status_code=503,
            detail="Setup extraction isn't available right now — try bulk import instead.",
        )
    return SetupExtractionPreview(
        teachers=extracted.get("teachers", []),
        subjects=extracted.get("subjects", []),
        class_groups=extracted.get("class_groups", []),
        notes=extracted.get("notes", ""),
    )


@router.post("/commit", response_model=SetupExtractionCommitOut)
def commit_setup(
    school_id: int,
    payload: SetupExtractionCommit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Actually creates the admin-reviewed subset of a previous /extract
    preview. Reshapes the confirmed items into the same row-dict shape
    app/services/bulk_import.py's import_* functions expect and calls
    those directly, so upsert-by-name behavior and validation come from
    that existing, tested code rather than being reimplemented here.
    Subjects are created first, since import_teachers resolves
    qualified_subjects by looking up existing subjects for the school.
    """
    require_school_access(db, current_user, school_id, min_role="admin")

    subject_rows = [{"name": s.name, "required_room_type": ""} for s in payload.subjects]
    subject_result = import_subjects(db, school_id, subject_rows)

    teacher_rows = [
        {
            "name": t.name,
            "email": t.email or "",
            "max_periods_per_week": "",
            "qualified_subjects": ";".join(t.subject_names),
        }
        for t in payload.teachers
    ]
    teacher_result = import_teachers(db, school_id, teacher_rows)

    class_group_rows = [
        {"name": g.name, "grade": g.grade or "", "student_count": ""} for g in payload.class_groups
    ]
    class_group_result = import_class_groups(db, school_id, class_group_rows)

    return SetupExtractionCommitOut(
        subjects_created=subject_result.created,
        subjects_updated=subject_result.updated,
        teachers_created=teacher_result.created,
        teachers_updated=teacher_result.updated,
        class_groups_created=class_group_result.created,
        class_groups_updated=class_group_result.updated,
        errors=subject_result.errors + teacher_result.errors + class_group_result.errors,
    )

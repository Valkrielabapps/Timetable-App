from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import (
    ElectiveBlock, ElectiveOption, Subject, SubjectRequirement, TimetableEntry,
)
from app.models.user import User
from app.schemas.bulk_import import BulkImportOut
from app.schemas.subject import SubjectCreate, SubjectOut, SubjectUpdate
from app.services.bulk_import import TEMPLATES, import_subjects, parse_rows

router = APIRouter(prefix="/api/subjects", tags=["subjects"])


@router.post("", response_model=SubjectOut, status_code=201)
def create_subject(payload: SubjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    subject = Subject(**payload.model_dump())
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return subject


@router.get("", response_model=list[SubjectOut])
def list_subjects(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    return db.query(Subject).filter(Subject.school_id == school_id).all()


@router.get("/{subject_id}", response_model=SubjectOut)
def get_subject(subject_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    require_school_access(db, current_user, subject.school_id)
    return subject


@router.put("/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, payload: SubjectUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    require_school_access(db, current_user, subject.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(subject, field, value)
    db.commit()
    db.refresh(subject)
    return subject


@router.delete("/{subject_id}", status_code=204)
def delete_subject(subject_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    subject = db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    require_school_access(db, current_user, subject.school_id, min_role="admin")
    # SubjectRequirement.subject_id has no ORM-level relationship/cascade
    # back to Subject (only class_group_id does — see the model), so a
    # bare db.delete(subject) here left orphaned requirement rows behind:
    # invisible in the UI (DataEntryTab only iterates over subjects that
    # still exist), but still summed by the solver as real demand,
    # silently doubling a class group's actual periods/week and making
    # generation infeasible for no visible reason. Deleting them
    # explicitly here closes that gap. See dedupe_orphaned_requirements.py
    # for a one-off cleanup of any orphans a pre-fix delete already left.
    db.query(SubjectRequirement).filter(SubjectRequirement.subject_id == subject_id).delete()
    # Same orphan problem for block options, with a worse failure: a block
    # whose last option is gone would still reserve the section's periods for
    # nothing at all. Options go, and so does any block left empty by it. A
    # block left with one option still schedules correctly - it is just a
    # subject everyone in that block takes - so it is kept for the admin to see.
    affected_blocks = {
        o.block_id for o in db.query(ElectiveOption).filter(ElectiveOption.subject_id == subject_id).all()
    }
    db.query(ElectiveOption).filter(ElectiveOption.subject_id == subject_id).delete()
    for block_id in affected_blocks:
        remaining = db.query(ElectiveOption).filter(ElectiveOption.block_id == block_id).count()
        if remaining == 0:
            db.query(TimetableEntry).filter(TimetableEntry.elective_block_id == block_id).update(
                {TimetableEntry.elective_block_id: None}
            )
            db.query(ElectiveBlock).filter(ElectiveBlock.id == block_id).delete()
    db.delete(subject)
    db.commit()


@router.get("/bulk-import/template")
def download_subjects_template():
    """A starter CSV — see app/services/bulk_import.py:TEMPLATES."""
    return Response(
        content=TEMPLATES["subjects"],
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="subjects_template.csv"'},
    )


@router.post("/bulk-import", response_model=BulkImportOut)
async def bulk_import_subjects(
    school_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CSV or .xlsx of subjects (columns: name, required_room_type)
    instead of adding them one at a time. Upserts by name — re-uploading
    after fixing a typo updates rather than duplicates. See
    app/services/bulk_import.py for the parsing/import logic and the
    best-effort error-handling philosophy (one bad row doesn't block the
    rest of the file).
    """
    require_school_access(db, current_user, school_id, min_role="admin")
    content = await file.read()
    try:
        rows = parse_rows(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = import_subjects(db, school_id, rows)
    return BulkImportOut(created=result.created, updated=result.updated, errors=result.errors)

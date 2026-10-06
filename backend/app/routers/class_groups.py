from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, SubjectRequirement, TimetableEntry,
)
from app.models.user import User
from app.schemas.bulk_import import BulkImportOut
from app.schemas.class_group import (
    ClassGroupCreate,
    ClassGroupOut,
    ClassGroupUpdate,
    SubjectRequirementCreate,
    SubjectRequirementOut,
    SubjectRequirementUpdate,
)
from app.services.bulk_import import TEMPLATES, import_class_groups, parse_rows

router = APIRouter(prefix="/api/class-groups", tags=["class groups"])


@router.post("", response_model=ClassGroupOut, status_code=201)
def create_class_group(payload: ClassGroupCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    class_group = ClassGroup(**payload.model_dump())
    db.add(class_group)
    db.commit()
    db.refresh(class_group)
    return class_group


@router.get("", response_model=list[ClassGroupOut])
def list_class_groups(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    return db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()


@router.get("/requirements", response_model=list[SubjectRequirementOut])
def list_all_requirements(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Every requirement across every section in the school, not just one
    class group — used by TeachersSection.jsx's live workload total, which
    needs to sum a teacher's periods/week commitments across all sections
    at once, not just whichever one is currently open. Registered here,
    before /{class_group_id}, on purpose: FastAPI matches routes in
    declaration order, and this literal one-segment path would otherwise
    be shadowed by /{class_group_id} treating "requirements" as an
    (invalid) class_group_id."""
    require_school_access(db, current_user, school_id)
    return (
        db.query(SubjectRequirement)
        .join(ClassGroup, SubjectRequirement.class_group_id == ClassGroup.id)
        .filter(ClassGroup.school_id == school_id)
        .all()
    )


@router.get("/{class_group_id}", response_model=ClassGroupOut)
def get_class_group(class_group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    class_group = db.get(ClassGroup, class_group_id)
    if not class_group:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, class_group.school_id)
    return class_group


@router.put("/{class_group_id}", response_model=ClassGroupOut)
def update_class_group(class_group_id: int, payload: ClassGroupUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    class_group = db.get(ClassGroup, class_group_id)
    if not class_group:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, class_group.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(class_group, field, value)
    db.commit()
    db.refresh(class_group)
    return class_group


@router.delete("/{class_group_id}", status_code=204)
def delete_class_group(class_group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    class_group = db.get(ClassGroup, class_group_id)
    if not class_group:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, class_group.school_id, min_role="admin")
    # TimetableEntry.class_group_id has no ORM-level relationship/cascade
    # back to ClassGroup (only SubjectRequirement does, via the
    # cascade="all, delete-orphan" on ClassGroup.requirements — see the
    # model), so deleting a class group that already has generated
    # timetable entries would otherwise either raise a foreign-key
    # constraint error (Postgres) or silently leave orphaned rows behind
    # (SQLite, which doesn't enforce FKs by default) — the orphaned rows
    # then crash _to_timetable_out's plain dict lookups the next time
    # that timetable is viewed. Deleting them explicitly here closes that
    # gap, the same fix already applied to delete_subject in subjects.py
    # for the equivalent bug.
    db.query(TimetableEntry).filter(TimetableEntry.class_group_id == class_group_id).delete()
    db.delete(class_group)
    db.commit()


# --- Subject requirements: "this class group needs N periods/week of subject X" ---
# Nested under class-groups since a requirement doesn't make sense without its
# class group, but subject_id/teacher_id reference the other generic tables.


@router.post(
    "/{class_group_id}/requirements",
    response_model=SubjectRequirementOut,
    status_code=201,
)
def add_requirement(
    class_group_id: int, payload: SubjectRequirementCreate, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.class_group_id != class_group_id:
        raise HTTPException(
            status_code=400, detail="class_group_id in body must match URL"
        )
    class_group = db.get(ClassGroup, class_group_id)
    if not class_group:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, class_group.school_id, min_role="admin")

    # The other half of the check in app/routers/elective_blocks.py: a subject
    # is either common to the whole section or an option in one of its blocks,
    # never both. Both would schedule it twice and quietly inflate the
    # section's real periods per week.
    in_block = (
        db.query(ElectiveBlock)
        .join(ElectiveOption, ElectiveOption.block_id == ElectiveBlock.id)
        .filter(
            ElectiveBlock.class_group_id == class_group_id,
            ElectiveOption.subject_id == payload.subject_id,
        )
        .first()
    )
    if in_block:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This subject is already an option in {in_block.name} for this section. "
                f"A subject can be common to everyone or an option in a block, not both."
            ),
        )

    # Upsert on (class_group_id, subject_id) rather than blind-insert: a
    # class group should only have one requirement per subject, and a
    # duplicate here (e.g. from a client-side race — two "create" calls in
    # quick succession before the first one's result comes back) would
    # silently inflate the real periods/week total past what the UI shows,
    # which can make the solver infeasible for no visible reason.
    existing = (
        db.query(SubjectRequirement)
        .filter(
            SubjectRequirement.class_group_id == class_group_id,
            SubjectRequirement.subject_id == payload.subject_id,
        )
        .first()
    )
    if existing:
        existing.periods_per_week = payload.periods_per_week
        existing.preferred_teacher_id = payload.preferred_teacher_id
        existing.assistant_teacher_id = payload.assistant_teacher_id
        db.commit()
        db.refresh(existing)
        return existing

    requirement = SubjectRequirement(**payload.model_dump())
    db.add(requirement)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.get("/{class_group_id}/requirements", response_model=list[SubjectRequirementOut])
def list_requirements(class_group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    class_group = db.get(ClassGroup, class_group_id)
    if not class_group:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, class_group.school_id)
    return (
        db.query(SubjectRequirement)
        .filter(SubjectRequirement.class_group_id == class_group_id)
        .all()
    )


@router.put("/requirements/{requirement_id}", response_model=SubjectRequirementOut)
def update_requirement(
    requirement_id: int, payload: SubjectRequirementUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requirement = db.get(SubjectRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    class_group = db.get(ClassGroup, requirement.class_group_id)
    require_school_access(db, current_user, class_group.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(requirement, field, value)
    db.commit()
    db.refresh(requirement)
    return requirement


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    requirement = db.get(SubjectRequirement, requirement_id)
    if not requirement:
        raise HTTPException(status_code=404, detail="Requirement not found")
    class_group = db.get(ClassGroup, requirement.class_group_id)
    require_school_access(db, current_user, class_group.school_id, min_role="admin")
    db.delete(requirement)
    db.commit()


@router.get("/bulk-import/template")
def download_class_groups_template():
    return Response(
        content=TEMPLATES["class_groups"],
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="class_groups_template.csv"'},
    )


@router.post("/bulk-import", response_model=BulkImportOut)
async def bulk_import_class_groups(
    school_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CSV or .xlsx of class groups/sections (columns: name, grade,
    student_count) instead of adding them one at a time. Upserts on
    (grade, name) — e.g. re-uploading with an updated student_count for
    "Grade 8 - A" updates that section rather than creating a duplicate.
    Note this only creates the sections themselves, not their subject
    requirements (periods/week per subject) — those are still set per
    section in Data Entry, since they depend on which subjects that grade
    actually takes.
    """
    require_school_access(db, current_user, school_id, min_role="admin")
    content = await file.read()
    try:
        rows = parse_rows(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = import_class_groups(db, school_id, rows)
    return BulkImportOut(created=result.created, updated=result.updated, errors=result.errors)

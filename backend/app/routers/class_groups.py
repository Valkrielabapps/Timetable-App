from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import (
    School, ClassGroup, ElectiveBlock, ElectiveOption, Subject, SubjectRequirement, Teacher, TimetableEntry, ZeroPeriod,
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
from app.services import plans

router = APIRouter(prefix="/api/class-groups", tags=["class groups"])


@router.post("", response_model=ClassGroupOut, status_code=201)
def create_class_group(payload: ClassGroupCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    plans.require_section_capacity(db, db.get(School, payload.school_id))
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
    changes = payload.model_dump(exclude_unset=True)
    teacher_id = changes.get("class_teacher_id")
    if teacher_id is not None:
        teacher = db.get(Teacher, teacher_id)
        if not teacher or teacher.school_id != class_group.school_id:
            raise HTTPException(status_code=404, detail="Teacher not found")
    old_grade = class_group.grade
    for field, value in changes.items():
        setattr(class_group, field, value)
    db.flush()
    # Zero periods are kept per grade by name. Renaming a grade's last section
    # renames the grade, so its zero periods follow; while another section
    # still has the old name, they stay with that one.
    if "grade" in changes and old_grade and class_group.grade != old_grade:
        still_used = db.query(ClassGroup).filter(
            ClassGroup.school_id == class_group.school_id, ClassGroup.grade == old_grade
        ).first()
        if still_used is None:
            db.query(ZeroPeriod).filter(
                ZeroPeriod.school_id == class_group.school_id, ZeroPeriod.grade == old_grade
            ).update({ZeroPeriod.grade: class_group.grade}, synchronize_session=False)
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


class CopyRequirementsIn(BaseModel):
    target_ids: list[int] = Field(min_length=1, max_length=500)
    # Which of the source section's subjects to copy; omitted = every subject
    # with periods set.
    subject_ids: list[int] | None = None


@router.post("/{class_group_id}/requirements/copy")
def copy_requirements(
    class_group_id: int,
    payload: CopyRequirementsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copy this section's periods/week for some subjects to other sections,
    in one request and one transaction.

    Replaces the frontend firing one request per subject per section at once
    (8 subjects x 7 sections = 56 in parallel), which could run the database
    out of connections and come back as a 500 part-way through. A target that
    already has the subject keeps its own teacher choices; only the periods
    change. A subject that is an elective option in a target section is
    skipped and reported, since it can't also be a common subject there."""
    source = db.get(ClassGroup, class_group_id)
    if not source:
        raise HTTPException(status_code=404, detail="Class group not found")
    require_school_access(db, current_user, source.school_id, min_role="admin")

    targets = (
        db.query(ClassGroup)
        .filter(ClassGroup.id.in_(set(payload.target_ids) - {class_group_id}), ClassGroup.school_id == source.school_id)
        .all()
    )
    if not targets:
        raise HTTPException(status_code=400, detail="Pick at least one other section to copy to.")

    query = db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == class_group_id)
    if payload.subject_ids:
        query = query.filter(SubjectRequirement.subject_id.in_(payload.subject_ids))
    source_rows = [r for r in query.all() if r.periods_per_week and r.periods_per_week > 0]
    if not source_rows:
        raise HTTPException(status_code=400, detail="Nothing to copy: set some periods/week in this section first.")

    target_ids = [t.id for t in targets]
    existing = {
        (r.class_group_id, r.subject_id): r
        for r in db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id.in_(target_ids)).all()
    }
    in_blocks = {
        (cg_id, subject_id)
        for cg_id, subject_id in db.query(ElectiveBlock.class_group_id, ElectiveOption.subject_id)
        .join(ElectiveOption, ElectiveOption.block_id == ElectiveBlock.id)
        .filter(ElectiveBlock.class_group_id.in_(target_ids))
        .all()
    }
    labels = {t.id: (f"{t.grade} - {t.name}" if t.grade else t.name) for t in targets}
    subject_names = {s.id: s.name for s in db.query(Subject).filter(Subject.id.in_([r.subject_id for r in source_rows])).all()}

    created = updated = 0
    skipped: list[str] = []
    for target in targets:
        for row in source_rows:
            key = (target.id, row.subject_id)
            if key in in_blocks:
                skipped.append(f"{subject_names.get(row.subject_id, 'A subject')} in {labels[target.id]} (it's an elective option there)")
                continue
            if key in existing:
                existing[key].periods_per_week = row.periods_per_week
                updated += 1
            else:
                db.add(SubjectRequirement(class_group_id=target.id, subject_id=row.subject_id, periods_per_week=row.periods_per_week))
                created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "sections": len(targets)}


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
    school = db.get(School, school_id)
    result = import_class_groups(
        db, school_id, rows,
        max_new=plans.sections_remaining(db, school), limit_message=plans.sections_limit_message(school),
    )
    return BulkImportOut(created=result.created, updated=result.updated, errors=result.errors)

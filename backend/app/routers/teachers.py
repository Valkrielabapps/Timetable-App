from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import ElectiveOption, SubjectRequirement, Teacher
from app.models.user import User
from app.schemas.bulk_import import BulkImportOut
from app.schemas.teacher import TeacherCreate, TeacherOut, TeacherUpdate
from app.services.bulk_import import TEMPLATES, import_teachers, parse_rows

router = APIRouter(prefix="/api/teachers", tags=["teachers"])


@router.post("", response_model=TeacherOut, status_code=201)
def create_teacher(payload: TeacherCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    teacher = Teacher(**payload.model_dump())
    db.add(teacher)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.get("", response_model=list[TeacherOut])
def list_teachers(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    return db.query(Teacher).filter(Teacher.school_id == school_id).all()


@router.get("/{teacher_id}", response_model=TeacherOut)
def get_teacher(teacher_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    require_school_access(db, current_user, teacher.school_id)
    return teacher


@router.put("/{teacher_id}", response_model=TeacherOut)
def update_teacher(teacher_id: int, payload: TeacherUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    require_school_access(db, current_user, teacher.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(teacher, field, value)
    db.commit()
    db.refresh(teacher)
    return teacher


@router.delete("/{teacher_id}", status_code=204)
def delete_teacher(teacher_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    teacher = db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    require_school_access(db, current_user, teacher.school_id, min_role="admin")
    # A pin to a teacher who no longer exists doesn't fall back to "anyone
    # qualified" - the solver reads it as "only this teacher", finds nobody,
    # and fails with "no qualified teacher found", which points the admin at
    # qualifications rather than at the teacher they deleted. Clearing the pin
    # restores the normal choice among qualified staff.
    db.query(SubjectRequirement).filter(SubjectRequirement.preferred_teacher_id == teacher_id).update(
        {SubjectRequirement.preferred_teacher_id: None}
    )
    db.query(ElectiveOption).filter(ElectiveOption.preferred_teacher_id == teacher_id).update(
        {ElectiveOption.preferred_teacher_id: None}
    )
    db.delete(teacher)
    db.commit()


@router.get("/bulk-import/template")
def download_teachers_template():
    return Response(
        content=TEMPLATES["teachers"],
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="teachers_template.csv"'},
    )


@router.post("/bulk-import", response_model=BulkImportOut)
async def bulk_import_teachers(
    school_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CSV or .xlsx of teachers (columns: name, email,
    max_periods_per_week, qualified_subjects — subject names separated by
    ';' or ',') instead of adding them one at a time. Subjects should be
    imported/added first so qualified_subjects can resolve against them;
    see app/services/bulk_import.py for what happens to an unresolvable
    subject name (the teacher still gets created, with a warning).
    """
    require_school_access(db, current_user, school_id, min_role="admin")
    content = await file.read()
    try:
        rows = parse_rows(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = import_teachers(db, school_id, rows)
    return BulkImportOut(created=result.created, updated=result.updated, errors=result.errors)

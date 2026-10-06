"""
Elective blocks: subjects one section studies at the same time, each student
taking one of them. See ElectiveBlock in app/models/school.py.

Every write is validated as a whole set, because the ways a block goes wrong
are all about overlap - and each of them schedules a subject twice, which
silently inflates the section's real periods per week and tends to surface
much later as an infeasible timetable with no visible cause:

  - the same subject twice in one block
  - a subject in two blocks of the same section
  - a subject that is both a block option and one of the section's common
    subjects (a normal SubjectRequirement)

The requirement side refuses the third case too, in
app/routers/class_groups.py, so neither order of entry can create it.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Subject, SubjectRequirement, Teacher,
    TimetableEntry,
)
from app.models.user import User
from app.schemas.elective_block import (
    ElectiveBlockCreate, ElectiveBlockOut, ElectiveBlockUpdate, ElectiveOptionIn,
)

router = APIRouter(prefix="/api/elective-blocks", tags=["elective-blocks"])


def _validate_options(
    db: Session,
    school_id: int,
    class_group_id: int,
    options: list[ElectiveOptionIn],
    block_id: int | None,
) -> None:
    """Refuse a set of options that would schedule any subject twice.

    `block_id` is the block being edited, if any, so its own current options
    are not counted as a clash with themselves.
    """
    if len(options) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "A block needs at least two subjects to choose between. A single "
                "subject everyone takes belongs with the section's common subjects."
            ),
        )

    subject_ids = [o.subject_id for o in options]
    subjects = {
        s.id: s for s in db.query(Subject).filter(
            Subject.id.in_(subject_ids), Subject.school_id == school_id,
        ).all()
    }
    missing = [sid for sid in subject_ids if sid not in subjects]
    if missing:
        raise HTTPException(status_code=400, detail="A subject in this block doesn't exist in this school.")

    seen: set[int] = set()
    for sid in subject_ids:
        if sid in seen:
            raise HTTPException(
                status_code=400,
                detail=f"{subjects[sid].name} is in this block twice.",
            )
        seen.add(sid)

    common = (
        db.query(SubjectRequirement)
        .filter(
            SubjectRequirement.class_group_id == class_group_id,
            SubjectRequirement.subject_id.in_(subject_ids),
        )
        .all()
    )
    if common:
        name = subjects[common[0].subject_id].name
        raise HTTPException(
            status_code=400,
            detail=(
                f"{name} is already one of this section's common subjects. A subject "
                f"can be common to everyone or an option in a block, not both - remove "
                f"it from the common subjects first."
            ),
        )

    other_blocks = db.query(ElectiveBlock).filter(ElectiveBlock.class_group_id == class_group_id)
    if block_id is not None:
        other_blocks = other_blocks.filter(ElectiveBlock.id != block_id)
    for other in other_blocks.all():
        for option in other.options:
            if option.subject_id in seen:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{subjects[option.subject_id].name} is already an option in "
                        f"{other.name}. A subject can only be in one block per section."
                    ),
                )

    teacher_ids = {o.preferred_teacher_id for o in options if o.preferred_teacher_id is not None}
    if teacher_ids:
        found = {
            t.id for t in db.query(Teacher).filter(
                Teacher.id.in_(teacher_ids), Teacher.school_id == school_id,
            ).all()
        }
        if teacher_ids - found:
            raise HTTPException(status_code=400, detail="A preferred teacher doesn't exist in this school.")


@router.get("", response_model=list[ElectiveBlockOut])
def list_blocks(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    return (
        db.query(ElectiveBlock)
        .filter(ElectiveBlock.school_id == school_id)
        .order_by(ElectiveBlock.class_group_id, ElectiveBlock.id)
        .all()
    )


@router.post("", response_model=ElectiveBlockOut, status_code=201)
def create_block(payload: ElectiveBlockCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    class_group = db.get(ClassGroup, payload.class_group_id)
    if not class_group or class_group.school_id != payload.school_id:
        raise HTTPException(status_code=404, detail="Section not found")

    _validate_options(db, payload.school_id, payload.class_group_id, payload.options, None)

    block = ElectiveBlock(
        school_id=payload.school_id,
        class_group_id=payload.class_group_id,
        name=payload.name.strip(),
        periods_per_week=payload.periods_per_week,
        options=[
            ElectiveOption(subject_id=o.subject_id, preferred_teacher_id=o.preferred_teacher_id)
            for o in payload.options
        ],
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


@router.put("/{block_id}", response_model=ElectiveBlockOut)
def update_block(
    block_id: int, payload: ElectiveBlockUpdate, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    block = db.get(ElectiveBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    require_school_access(db, current_user, block.school_id, min_role="admin")

    if payload.options is not None:
        _validate_options(db, block.school_id, block.class_group_id, payload.options, block.id)
        # Replaced wholesale: the options are validated as a set, so editing
        # one in place could pass checks the full set would fail.
        #
        # The old rows are flushed away first. Assigning the new list directly
        # lets the unit of work insert before it deletes, and keeping any
        # subject across the edit then trips the (block_id, subject_id) unique
        # constraint on a perfectly valid request.
        block.options.clear()
        db.flush()
        block.options = [
            ElectiveOption(subject_id=o.subject_id, preferred_teacher_id=o.preferred_teacher_id)
            for o in payload.options
        ]
    if payload.name is not None:
        block.name = payload.name.strip()
    if payload.periods_per_week is not None:
        block.periods_per_week = payload.periods_per_week

    db.commit()
    db.refresh(block)
    return block


@router.delete("/{block_id}", status_code=204)
def delete_block(block_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    block = db.get(ElectiveBlock, block_id)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    require_school_access(db, current_user, block.school_id, min_role="admin")
    # Generated timetables keep their rows; they only stop knowing which ones
    # were a block. Done explicitly because SQLite, used in tests and local
    # development, does not enforce the ON DELETE SET NULL on its own.
    db.query(TimetableEntry).filter(TimetableEntry.elective_block_id == block.id).update(
        {TimetableEntry.elective_block_id: None}
    )
    db.delete(block)
    db.commit()

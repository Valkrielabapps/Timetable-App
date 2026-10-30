"""
Elective blocks: subjects studied at the same time, each student taking one
of them. See ElectiveBlock in app/models/school.py.

A block can span several sections, and each option is a teaching group drawn
from some or all of them, so one structure covers every arrangement a school
uses: one section splitting up, several sections pooling their students, a
big subject split into two groups, a subject one section takes on its own
while others pool, and sections of different grades sharing a period.

Every write is validated as a whole set, because the ways a block goes wrong
are all about overlap - and each of them schedules a subject twice for the
same students, which silently inflates a section's real periods per week and
tends to surface much later as an infeasible timetable with no visible cause:

  - the same subject twice for one section, unless it is deliberately split
    into named groups
  - a subject that is both a block option and one of the section's common
    subjects (a normal SubjectRequirement)

and one more that is about coverage: every section in the block must have at
least one group its students go to, or the section would sit idle.

The requirement side refuses the common-subject case too, in
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


def _label(cg: ClassGroup) -> str:
    return f"{cg.grade} {cg.name}" if cg.grade else cg.name


def _resolve_sections(db: Session, school_id: int, home_id: int, section_ids: list[int] | None) -> list[ClassGroup]:
    """The block's sections, its own first, each once."""
    ordered = list(dict.fromkeys([home_id, *(section_ids or [])]))
    found = {
        cg.id: cg for cg in db.query(ClassGroup).filter(
            ClassGroup.id.in_(ordered), ClassGroup.school_id == school_id,
        ).all()
    }
    if len(found) != len(ordered):
        raise HTTPException(status_code=400, detail="A section in this block doesn't exist in this school.")
    return [found[i] for i in ordered]


def _validate_block(
    db: Session,
    school_id: int,
    sections: list[ClassGroup],
    options: list[ElectiveOptionIn],
    block_id: int | None,
) -> list[list[int] | None]:
    """Refuse a block that would leave a section idle or teach any subject
    twice to the same students. Returns each option's stored section list
    (None when it is every section of the block).

    `block_id` is the block being edited, if any, so its own current options
    are not counted as a clash with themselves.
    """
    section_ids = [cg.id for cg in sections]
    labels = {cg.id: _label(cg) for cg in sections}
    if not options:
        raise HTTPException(status_code=400, detail="Add at least one subject to the block.")
    if len(sections) == 1 and len(options) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "A block needs at least two subjects to choose between. A single "
                "subject everyone takes belongs with the section's common subjects - "
                "or add more sections to the block to teach them together."
            ),
        )

    subject_ids = [o.subject_id for o in options]
    subjects = {
        s.id: s for s in db.query(Subject).filter(
            Subject.id.in_(subject_ids), Subject.school_id == school_id,
        ).all()
    }
    if any(sid not in subjects for sid in subject_ids):
        raise HTTPException(status_code=400, detail="A subject in this block doesn't exist in this school.")

    stored: list[list[int] | None] = []
    groups: list[list[int]] = []
    for o in options:
        name = subjects[o.subject_id].name
        if o.class_group_ids is None:
            chosen = list(section_ids)
        else:
            outside = [i for i in o.class_group_ids if i not in labels]
            if outside:
                raise HTTPException(
                    status_code=400,
                    detail=f"{name} is set for a section that isn't in this block. Add the section to the block first.",
                )
            chosen = [i for i in section_ids if i in set(o.class_group_ids)]
            if not chosen:
                raise HTTPException(
                    status_code=400,
                    detail=f"Choose at least one section whose students take {name}.",
                )
        groups.append(chosen)
        stored.append(None if chosen == section_ids else chosen)

    for sid in section_ids:
        if not any(sid in g for g in groups):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No subject in this block is for {labels[sid]}, so its students would have "
                    f"nowhere to go. Give it at least one subject, or take it out of the block."
                ),
            )

    # A subject twice for the same section is a split into groups only when
    # each group is named; otherwise it is a mistake that doubles its periods.
    for sid in section_ids:
        by_subject: dict[int, list[str]] = {}
        for o, g in zip(options, groups):
            if sid in g:
                by_subject.setdefault(o.subject_id, []).append((o.label or "").strip().lower())
        for subject_id, names in by_subject.items():
            if len(names) > 1 and (not all(names) or len(set(names)) != len(names)):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{subjects[subject_id].name} is in this block twice for {labels[sid]}. If it "
                        f"is split into groups, give each one a different name, such as Group 1 and Group 2."
                    ),
                )

    subjects_for = {sid: {o.subject_id for o, g in zip(options, groups) if sid in g} for sid in section_ids}
    common = (
        db.query(SubjectRequirement)
        .filter(
            SubjectRequirement.class_group_id.in_(section_ids),
            SubjectRequirement.subject_id.in_(subject_ids),
        )
        .all()
    )
    for r in common:
        if r.subject_id in subjects_for[r.class_group_id]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{subjects[r.subject_id].name} is already one of {labels[r.class_group_id]}'s common "
                    f"subjects. A subject can be common to everyone or an option in a block, not both - "
                    f"remove it from the common subjects first."
                ),
            )

    # A subject may be in two blocks of one section: Maths / Economics for
    # some students and Maths / History for others are two Maths classes at
    # different times, each student in at most one of them. Each block takes
    # its own periods, so nothing is counted twice.

    teacher_ids = [o.preferred_teacher_id for o in options if o.preferred_teacher_id is not None]
    if teacher_ids:
        found = {
            t.id: t for t in db.query(Teacher).filter(
                Teacher.id.in_(set(teacher_ids)), Teacher.school_id == school_id,
            ).all()
        }
        if set(teacher_ids) - set(found):
            raise HTTPException(status_code=400, detail="A preferred teacher doesn't exist in this school.")
        twice = next((t for t in teacher_ids if teacher_ids.count(t) > 1), None)
        if twice is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{found[twice].name} is set to teach two groups of this block, but its groups all "
                    f"meet at the same time. Choose a different teacher for one of them."
                ),
            )
    return stored


def _options(payload_options: list[ElectiveOptionIn], stored: list[list[int] | None]) -> list[ElectiveOption]:
    return [
        ElectiveOption(
            subject_id=o.subject_id, preferred_teacher_id=o.preferred_teacher_id,
            class_group_ids=sections, label=(o.label or "").strip() or None,
        )
        for o, sections in zip(payload_options, stored)
    ]


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

    sections = _resolve_sections(db, payload.school_id, payload.class_group_id, payload.section_ids)
    stored = _validate_block(db, payload.school_id, sections, payload.options, None)

    block = ElectiveBlock(
        school_id=payload.school_id,
        class_group_id=payload.class_group_id,
        name=payload.name.strip(),
        periods_per_week=payload.periods_per_week,
        options=_options(payload.options, stored),
        linked_sections=sections[1:],
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

    if payload.section_ids is not None or payload.options is not None:
        sections = _resolve_sections(
            db, block.school_id, block.class_group_id,
            payload.section_ids if payload.section_ids is not None else block.section_ids,
        )
        options_in = payload.options if payload.options is not None else [
            ElectiveOptionIn(
                subject_id=o.subject_id, preferred_teacher_id=o.preferred_teacher_id,
                class_group_ids=o.class_group_ids, label=o.label,
            )
            for o in block.options
        ]
        stored = _validate_block(db, block.school_id, sections, options_in, block.id)
        block.linked_sections = sections[1:]
        # Replaced wholesale: the options are validated as a set, so editing
        # one in place could pass checks the full set would fail.
        #
        # The old rows are flushed away first. Assigning the new list directly
        # lets the unit of work insert before it deletes, and keeping any
        # subject across the edit then trips the (block_id, subject_id) unique
        # constraint on a perfectly valid request.
        old_ids = [o.id for o in block.options]
        block.options.clear()
        db.flush()
        if old_ids:
            db.query(TimetableEntry).filter(TimetableEntry.elective_option_id.in_(old_ids)).update(
                {TimetableEntry.elective_option_id: None}, synchronize_session=False,
            )
        block.options = _options(options_in, stored)
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
        {TimetableEntry.elective_block_id: None, TimetableEntry.elective_option_id: None}
    )
    db.delete(block)
    db.commit()

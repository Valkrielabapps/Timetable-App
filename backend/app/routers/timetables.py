"""
Timetable generation, run as a background job.

Why a job instead of a plain request/response: solving a large school's
schedule can legitimately take up to a minute (see
app/core/config.py:solver_time_limit_seconds and the stress-test notes in
app/services/solver.py). Holding an HTTP request open that long is
fragile — browsers, reverse proxies, and hosting platforms all impose
their own timeouts well under that, and a stuck request gives the admin no
feedback in the meantime. So instead:

  1. POST /generate creates a Timetable row with status="generating" and
     returns immediately (202-style, though we return 201 since the row
     was created).
  2. A background thread does the actual solving and, when done, updates
     that same row's status to "draft" (success) or "failed".
  3. The frontend polls GET /{id} (see TimetableTab.jsx) until status is
     no longer "generating".

This uses a plain Python thread rather than a task queue (Celery/RQ +
Redis) — the right tradeoff for this project's current scale: zero new
infrastructure to run, at the cost of jobs not surviving a server restart
and not scaling across multiple backend processes. If this needs to run
behind multiple worker processes or survive restarts, swap this for a
real task queue; the job-row-plus-polling API shape wouldn't need to
change.
"""
import threading

import sentry_sdk
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.auth import get_current_user
from app.core.database import SessionLocal, get_db
from app.models.school import (
    ClassGroup,
    Period,
    Room,
    Subject,
    SubjectRequirement,
    Teacher,
    Timetable,
    TimetableEntry,
)
from app.models.user import User
from app.schemas.timetable import (
    EditCommandRequest,
    EditCommandResponse,
    TimetableEntryOut,
    TimetableEntryUpdate,
    TimetableOut,
)
from app.services.edit_command_parser import parse_edit_command_llm
from app.services.export import build_excel, build_pdf
from app.services.infeasibility_explainer import explain_infeasibility
from app.services.solver import generate_school_timetable

router = APIRouter(prefix="/api/timetables", tags=["timetables"])


def _to_timetable_out(db: Session, timetable: Timetable) -> TimetableOut:
    """Attach human-readable names to each entry, since the DB only stores
    foreign keys. Done here (not in the DB model) to keep the model layer
    free of presentation concerns."""
    class_groups = {c.id: c for c in db.query(ClassGroup).filter(
        ClassGroup.school_id == timetable.school_id
    ).all()}
    subjects = {s.id: s for s in db.query(Subject).filter(
        Subject.school_id == timetable.school_id
    ).all()}
    teachers = {t.id: t for t in db.query(Teacher).filter(
        Teacher.school_id == timetable.school_id
    ).all()}
    periods = {p.id: p for p in db.query(Period).filter(
        Period.school_id == timetable.school_id
    ).all()}
    rooms = {r.id: r for r in db.query(Room).filter(
        Room.school_id == timetable.school_id
    ).all()}

    entries = []
    for e in timetable.entries:
        period = periods[e.period_id]
        room = rooms.get(e.room_id) if e.room_id else None
        entries.append({
            "id": e.id,
            "class_group_id": e.class_group_id,
            "class_group_name": class_groups[e.class_group_id].name,
            "subject_id": e.subject_id,
            "subject_name": subjects[e.subject_id].name,
            "teacher_id": e.teacher_id,
            "teacher_name": teachers[e.teacher_id].name,
            "assistant_teacher_id": e.assistant_teacher_id,
            "assistant_teacher_name": teachers[e.assistant_teacher_id].name if e.assistant_teacher_id else None,
            "period_id": e.period_id,
            "period_label": period.label,
            "day_of_week": period.day_of_week,
            "order": period.order,
            "room_id": e.room_id,
            "room_name": room.name if room else None,
            "locked": e.locked,
            "lab_batch": e.lab_batch,
        })

    return TimetableOut(
        id=timetable.id,
        school_id=timetable.school_id,
        status=timetable.status,
        solver_status=timetable.solver_status,
        error_message=timetable.error_message,
        error_explanation=timetable.error_explanation,
        entries=entries,
    )


def _run_generation_job(timetable_id: int, school_id: int) -> None:
    """
    Runs on a background thread — must open its own DB session rather
    than reusing the request's (SQLAlchemy sessions aren't thread-safe,
    and the request's session is closed once the response is sent anyway,
    which happens well before this function finishes).
    """
    db = SessionLocal()
    try:
        result = generate_school_timetable(db, school_id)
        timetable = db.get(Timetable, timetable_id)
        if timetable is None:
            return  # deleted while generating; nothing to update

        timetable.solver_status = result.status

        if result.status in ("optimal", "feasible"):
            # (class_group_id, subject_id) -> assistant_teacher_id, from the
            # plan — not something the solver chooses, just carried over so
            # each generated entry can show who's assisting. A single query
            # up front rather than one per assignment, since a school-wide
            # generation can produce hundreds of entries.
            assistant_by_requirement = {
                (r.class_group_id, r.subject_id): r.assistant_teacher_id
                for r in db.query(SubjectRequirement)
                .join(ClassGroup, SubjectRequirement.class_group_id == ClassGroup.id)
                .filter(ClassGroup.school_id == school_id)
                .all()
                if r.assistant_teacher_id is not None
            }
            for a in result.assignments:
                key = (a["class_group_id"], a["subject_id"], a["teacher_id"], a["period_id"])
                db.add(TimetableEntry(
                    timetable_id=timetable.id,
                    class_group_id=a["class_group_id"],
                    subject_id=a["subject_id"],
                    teacher_id=a["teacher_id"],
                    assistant_teacher_id=assistant_by_requirement.get((a["class_group_id"], a["subject_id"])),
                    period_id=a["period_id"],
                    room_id=a.get("room_id"),
                    lab_batch=a.get("batch"),
                    # Carries a lock forward from the previous timetable if
                    # this entry landed on the exact same (class group,
                    # subject, teacher, period) that was locked before —
                    # see generate_school_timetable's locked-entry handling
                    # in app/services/solver.py. So an admin's lock sticks
                    # across regenerations instead of needing to be
                    # reapplied by hand every time.
                    locked=key in result.locked_keys,
                ))
            timetable.status = "draft"
        else:
            timetable.status = "failed"
            # Newline-joined rather than "; " — result.errors may contain
            # several distinct diagnoses (see _diagnose_infeasibility in
            # app/services/solver.py), and the frontend renders each line
            # as its own bullet rather than running them together into one
            # sentence.
            if result.errors:
                timetable.error_message = "\n".join(result.errors)
                # Best-effort — see explain_infeasibility's docstring for
                # why this never raises and just leaves error_explanation
                # null on any failure (no API key, network issue, etc.).
                # Run once here, not on every GET, since this result never
                # changes for this timetable once computed.
                timetable.error_explanation = explain_infeasibility(result.errors)
            elif result.status == "infeasible":
                # _diagnose_infeasibility ran and came up empty — a real
                # conflict exists, but it's an interaction between several
                # constraints rather than one single identifiable cause,
                # which is a genuinely hard problem (see the ARCHITECTURE.md
                # note on this). Say so honestly instead of pretending to
                # know, and give a concrete next step.
                timetable.error_message = (
                    "No feasible timetable found, and the specific cause couldn't be "
                    "automatically identified — it's likely an interaction between several "
                    "constraints rather than one on its own. Try temporarily removing your "
                    "most recently added constraint or subject requirement and regenerating, "
                    "to narrow down which one is conflicting."
                )
            else:
                timetable.error_message = (
                    "The solver couldn't reach a conclusive answer in time. "
                    "This usually means the school is very large — try generating "
                    "a smaller subset (e.g. one grade at a time) if this keeps happening."
                )

        db.commit()
    except Exception as exc:  # noqa: BLE001 - background job, must not crash silently
        # Report before the traceback is flattened into error_message below.
        # This runs on a background thread with no HTTP response to carry the
        # failure, so without this the only surviving trace of a solver crash
        # is str(exc) in a database column nobody is watching.
        sentry_sdk.capture_exception(exc)
        db.rollback()
        timetable = db.get(Timetable, timetable_id)
        if timetable is not None:
            timetable.status = "failed"
            timetable.error_message = f"Internal error during generation: {exc}"
            db.commit()
    finally:
        db.close()


@router.post("/generate", response_model=TimetableOut, status_code=201)
def generate_timetable(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Kicks off generation and returns immediately with status=generating.
    Poll GET /api/timetables/{id} for the result."""
    require_school_access(db, current_user, school_id, min_role="admin")
    timetable = Timetable(school_id=school_id, status="generating")
    db.add(timetable)
    db.commit()
    db.refresh(timetable)

    thread = threading.Thread(
        target=_run_generation_job,
        args=(timetable.id, school_id),
        daemon=True,
    )
    thread.start()

    return _to_timetable_out(db, timetable)


@router.get("/{timetable_id}", response_model=TimetableOut)
def get_timetable(timetable_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    timetable = db.get(Timetable, timetable_id)
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
    require_school_access(db, current_user, timetable.school_id)
    return _to_timetable_out(db, timetable)


@router.get("", response_model=list[TimetableOut])
def list_timetables(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    timetables = db.query(Timetable).filter(Timetable.school_id == school_id).all()
    return [_to_timetable_out(db, t) for t in timetables]


def _check_slot_conflict(
    db: Session,
    timetable_id: int,
    class_group_id: int,
    new_period_id: int,
    new_teacher_id: int,
    new_room_id: int | None,
    exclude_entry_ids: set[int],
) -> None:
    """
    Raises a 400 if placing (class_group_id, new_teacher_id, new_room_id)
    at new_period_id would double-book the class group, the teacher, or
    the room against some *other* entry already in this timetable at that
    period. `exclude_entry_ids` leaves out the entry (or entries, for a
    swap) being moved, so an entry doesn't conflict with its own old slot
    or with the other entry it's being swapped against.
    """
    siblings = (
        db.query(TimetableEntry)
        .filter(
            TimetableEntry.timetable_id == timetable_id,
            TimetableEntry.id.notin_(exclude_entry_ids),
            TimetableEntry.period_id == new_period_id,
        )
        .all()
    )
    for s in siblings:
        if s.class_group_id == class_group_id:
            raise HTTPException(
                status_code=400,
                detail="This class group already has something scheduled in that period.",
            )
        if s.teacher_id == new_teacher_id:
            raise HTTPException(
                status_code=400,
                detail="This teacher is already scheduled in that period.",
            )
        if new_room_id is not None and s.room_id == new_room_id:
            raise HTTPException(
                status_code=400,
                detail="This room is already booked in that period.",
            )


@router.patch("/entries/{entry_id}", response_model=TimetableEntryOut)
def update_entry(entry_id: int, payload: TimetableEntryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Manual editing of one already-generated slot: lock/unlock it, and/or
    move it to a different period/teacher/room by hand (used by
    TimetableTab.jsx's drag-to-move and lock toggle).

    Locking doesn't do anything by itself here — it's read back by
    app/services/solver.py the next time this school's timetable is
    regenerated, which forces that exact (class group, subject, teacher,
    period) combination to stay fixed instead of being re-solved. Editing
    is only allowed on a "draft" timetable (a completed, successful
    generation) — not one that's still generating or that failed, since
    there's nothing coherent to edit in those states.

    Conflict checking: any change to period_id/teacher_id/room_id is
    checked against every other entry already in this same timetable at
    the target period, so a manual move can't silently double-book the
    class group, the teacher, or the room. locked-only edits skip this
    check entirely since nothing about the schedule is actually moving.

    Note: this rejects moving a slot onto a period some *other* entry
    already occupies for the same class group — including when the intent
    was really "swap these two slots". Use POST
    /entries/{entry_id}/swap-with/{other_entry_id} for that instead; it's
    a different operation because it has to move both entries in one
    transaction to avoid a spurious conflict against each other.
    """
    entry = db.get(TimetableEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")

    timetable = db.get(Timetable, entry.timetable_id)
    require_school_access(db, current_user, timetable.school_id, min_role="admin")
    if timetable.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"This timetable isn't editable right now (status: {timetable.status}).",
        )

    data = payload.model_dump(exclude_unset=True)
    return _apply_entry_update(db, entry, data)


def _apply_entry_update(db: Session, entry: TimetableEntry, data: dict) -> TimetableEntryOut:
    """The actual mutation behind PATCH /entries/{id} — factored out so
    POST /timetables/{id}/edit-command (conversational editing) performs
    the EXACT same conflict-checked update instead of a second copy of
    this logic. Callers are responsible for auth/status checks; this just
    validates the slot and applies the change."""
    if "period_id" in data or "teacher_id" in data or "room_id" in data:
        new_period_id = data.get("period_id", entry.period_id)
        new_teacher_id = data.get("teacher_id", entry.teacher_id)
        new_room_id = data.get("room_id", entry.room_id)
        _check_slot_conflict(
            db, entry.timetable_id, entry.class_group_id,
            new_period_id, new_teacher_id, new_room_id,
            exclude_entry_ids={entry.id},
        )

    for field, value in data.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)

    return _entry_out(db, entry)


@router.post("/entries/{entry_id}/swap-with/{other_entry_id}", response_model=list[TimetableEntryOut])
def swap_entries(entry_id: int, other_entry_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Swaps two entries' periods in one transaction — what actually happens
    when you drag one filled slot in TimetableTab.jsx onto another filled
    slot. A plain PATCH .../period_id move would reject this: moving entry
    A into entry B's period looks like a double-booking until B has also
    moved out of the way, and PATCH only moves one entry at a time. Doing
    both moves together, in a single conflict check that excludes both
    entries from each other, avoids that false rejection while still
    catching a real conflict (e.g. either entry's teacher is already
    booked elsewhere at the other's period).

    Refuses to swap a locked entry — a lock means "don't move this until
    I unlock it", and a swap is a move just like a drag.
    """
    entry = db.get(TimetableEntry, entry_id)
    other = db.get(TimetableEntry, other_entry_id)
    if not entry or not other:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    if entry.timetable_id != other.timetable_id:
        raise HTTPException(status_code=400, detail="Both entries must belong to the same timetable.")

    timetable = db.get(Timetable, entry.timetable_id)
    require_school_access(db, current_user, timetable.school_id, min_role="admin")
    if timetable.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"This timetable isn't editable right now (status: {timetable.status}).",
        )
    if entry.locked or other.locked:
        raise HTTPException(status_code=400, detail="Can't swap a locked slot — unlock it first.")
    if entry.period_id == other.period_id:
        raise HTTPException(status_code=400, detail="These are already in the same period.")

    return _apply_entry_swap(db, entry, other)


def _apply_entry_swap(db: Session, entry: TimetableEntry, other: TimetableEntry) -> list[TimetableEntryOut]:
    """The actual mutation behind POST /entries/{id}/swap-with/{id} —
    factored out for the same reason as _apply_entry_update above.
    Callers are responsible for auth/status/locked/same-timetable checks."""
    both_ids = {entry.id, other.id}
    _check_slot_conflict(
        db, entry.timetable_id, entry.class_group_id,
        other.period_id, entry.teacher_id, entry.room_id,
        exclude_entry_ids=both_ids,
    )
    _check_slot_conflict(
        db, other.timetable_id, other.class_group_id,
        entry.period_id, other.teacher_id, other.room_id,
        exclude_entry_ids=both_ids,
    )

    entry.period_id, other.period_id = other.period_id, entry.period_id
    db.commit()
    db.refresh(entry)
    db.refresh(other)

    return [_entry_out(db, entry), _entry_out(db, other)]


def _entry_out(db: Session, entry: TimetableEntry) -> TimetableEntryOut:
    """Builds a single TimetableEntryOut with human-readable names, same
    lookups as _to_timetable_out but for one entry — used by the PATCH
    endpoint so it doesn't have to rebuild the whole timetable's entry
    list just to return the one row that changed."""
    class_group = db.get(ClassGroup, entry.class_group_id)
    subject = db.get(Subject, entry.subject_id)
    teacher = db.get(Teacher, entry.teacher_id)
    period = db.get(Period, entry.period_id)
    room = db.get(Room, entry.room_id) if entry.room_id else None
    return TimetableEntryOut(
        id=entry.id,
        class_group_id=entry.class_group_id,
        class_group_name=class_group.name if class_group else "?",
        subject_id=entry.subject_id,
        subject_name=subject.name if subject else "?",
        teacher_id=entry.teacher_id,
        teacher_name=teacher.name if teacher else "?",
        period_id=entry.period_id,
        period_label=period.label if period else None,
        day_of_week=period.day_of_week if period else 0,
        order=period.order if period else 0,
        room_id=entry.room_id,
        room_name=room.name if room else None,
        locked=entry.locked,
        lab_batch=entry.lab_batch,
    )


@router.post("/{timetable_id}/edit-command", response_model=EditCommandResponse)
def edit_command(timetable_id: int, payload: EditCommandRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Conversational counterpart to drag-and-drop editing: plain-English
    text (e.g. "move Grade 8's Math to period 2 on Wednesdays", "lock
    Mrs. Sharma's Monday classes") is resolved via
    app/services/edit_command_parser.py into one of the same lock/move/
    swap operations the PATCH/swap-with endpoints perform, and applied
    through the exact same conflict-checked mutation functions
    (_apply_entry_update / _apply_entry_swap below) — this endpoint never
    mutates anything on its own, it only decides WHICH of those two
    functions to call and with what arguments.

    Unlike constraint parsing, there's no non-LLM fallback here (see
    edit_command_parser.py's module docstring for why): if no
    ANTHROPIC_API_KEY is configured, or the call fails for any reason,
    this returns 503 telling the admin to use drag-and-drop instead of
    silently doing nothing. Every id the model returns is re-validated
    against this timetable's actual entries/periods/teachers before use —
    a hallucinated id is treated as an ordinary "couldn't resolve that"
    failure (422), never trusted.
    """
    timetable = db.get(Timetable, timetable_id)
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
    require_school_access(db, current_user, timetable.school_id, min_role="admin")
    if timetable.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"This timetable isn't editable right now (status: {timetable.status}).",
        )

    entries = db.query(TimetableEntry).filter(TimetableEntry.timetable_id == timetable_id).all()
    if not entries:
        raise HTTPException(status_code=400, detail="This timetable has no entries to edit yet.")

    class_groups = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == timetable.school_id).all()}
    subjects = {s.id: s for s in db.query(Subject).filter(Subject.school_id == timetable.school_id).all()}
    teachers = {t.id: t for t in db.query(Teacher).filter(Teacher.school_id == timetable.school_id).all()}
    periods = {p.id: p for p in db.query(Period).filter(Period.school_id == timetable.school_id).all()}

    def _class_group_label(cg) -> str:
        return f"{cg.grade} - {cg.name}" if cg.grade else cg.name

    entries_context = [
        {
            "id": e.id,
            "class_group_name": _class_group_label(class_groups[e.class_group_id]) if e.class_group_id in class_groups else "?",
            "subject_name": subjects[e.subject_id].name if e.subject_id in subjects else "?",
            "teacher_name": teachers[e.teacher_id].name if e.teacher_id in teachers else "?",
            "day_of_week": periods[e.period_id].day_of_week if e.period_id in periods else None,
            "order": periods[e.period_id].order if e.period_id in periods else None,
            "period_label": periods[e.period_id].label if e.period_id in periods else None,
            "locked": e.locked,
        }
        for e in entries
    ]
    periods_context = [
        {"id": p.id, "day_of_week": p.day_of_week, "order": p.order, "label": p.label}
        for p in periods.values()
    ]
    teachers_context = [{"id": t.id, "name": t.name} for t in teachers.values()]

    parsed = parse_edit_command_llm(payload.text, entries_context, periods_context, teachers_context)
    if parsed is None:
        raise HTTPException(
            status_code=503,
            detail="Conversational editing isn't available right now — try dragging the entry instead.",
        )

    action = parsed.get("action")
    description = parsed.get("description") or "Edit applied."
    unresolved_detail = "Couldn't confidently resolve that — try rephrasing, or use drag-and-drop."

    if action == "unresolved" or action not in ("move", "lock", "unlock", "swap"):
        raise HTTPException(status_code=422, detail=description or unresolved_detail)

    entry = next((e for e in entries if e.id == parsed.get("entry_id")), None)
    if entry is None:
        raise HTTPException(status_code=422, detail=unresolved_detail)

    if action in ("lock", "unlock"):
        updated = _apply_entry_update(db, entry, {"locked": action == "lock"})
        return EditCommandResponse(action=action, description=description, entries=[updated])

    if action == "move":
        if entry.locked:
            raise HTTPException(status_code=400, detail="That slot is locked — unlock it first.")
        target_period_id = parsed.get("target_period_id")
        if target_period_id not in periods:
            raise HTTPException(status_code=422, detail=unresolved_detail)
        data = {"period_id": target_period_id}
        target_teacher_id = parsed.get("target_teacher_id")
        if target_teacher_id is not None:
            if target_teacher_id not in teachers:
                raise HTTPException(status_code=422, detail=unresolved_detail)
            data["teacher_id"] = target_teacher_id
        updated = _apply_entry_update(db, entry, data)
        return EditCommandResponse(action=action, description=description, entries=[updated])

    # action == "swap"
    other = next((e for e in entries if e.id == parsed.get("other_entry_id")), None)
    if other is None:
        raise HTTPException(status_code=422, detail=unresolved_detail)
    if entry.locked or other.locked:
        raise HTTPException(status_code=400, detail="Can't swap a locked slot — unlock it first.")
    if entry.period_id == other.period_id:
        raise HTTPException(status_code=400, detail="These are already in the same period.")
    updated = _apply_entry_swap(db, entry, other)
    return EditCommandResponse(action=action, description=description, entries=updated)


_EXPORT_CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@router.get("/{timetable_id}/export")
def export_timetable(timetable_id: int, format: str = "xlsx", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Downloads a printable version of a generated timetable — one sheet
    (Excel) or page (PDF) per section, followed by one per teacher, so
    the same file can be handed to a class or a teacher. See
    app/services/export.py for how the grids are built; both formats
    share the same underlying data so they can't disagree with each other
    or with what the Timetable tab shows on screen.
    """
    if format not in _EXPORT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="format must be 'xlsx' or 'pdf'")

    timetable = db.get(Timetable, timetable_id)
    if not timetable:
        raise HTTPException(status_code=404, detail="Timetable not found")
    require_school_access(db, current_user, timetable.school_id)
    if timetable.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"This timetable isn't ready to export yet (status: {timetable.status}).",
        )

    content = build_excel(db, timetable) if format == "xlsx" else build_pdf(db, timetable)
    filename = f"timetable_{timetable_id}.{format}"
    return Response(
        content=content,
        media_type=_EXPORT_CONTENT_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

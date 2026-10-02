from pydantic import BaseModel, ConfigDict


class TimetableEntryUpdate(BaseModel):
    """
    Manual edits to one already-generated entry: lock/unlock it (so it's
    kept in place on the next regenerate — see app/services/solver.py),
    and/or move it to a different period/teacher/room by hand. All fields
    optional and independent — a drag-to-move sends just `period_id`, the
    lock toggle sends just `locked`. See PATCH /api/timetables/entries/{id}
    in app/routers/timetables.py for the conflict checks applied before
    any of period_id/teacher_id/room_id actually change.
    """

    locked: bool | None = None
    period_id: int | None = None
    teacher_id: int | None = None
    room_id: int | None = None


class TimetableEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    class_group_id: int
    class_group_name: str
    subject_id: int
    subject_name: str
    teacher_id: int
    teacher_name: str
    assistant_teacher_id: int | None = None
    assistant_teacher_name: str | None = None
    period_id: int
    period_label: str | None
    day_of_week: int
    order: int
    room_id: int | None
    room_name: str | None
    locked: bool
    lab_batch: int | None = None


class ViolationOut(BaseModel):
    """One rule a timetable breaks, and the slots involved."""

    constraint_id: int | None = None
    # The sentence the admin confirmed when they added the rule, so the warning
    # quotes them rather than paraphrasing.
    description: str
    strength: str
    entry_ids: list[int]
    # What went wrong in numbers. "This breaks a rule" without "she has 7
    # periods and the rule allows 6" leaves someone hunting for which slot to
    # move.
    detail: str


class TimetableOut(BaseModel):
    """
    Represents one generation job's current state. `status` is the job
    lifecycle: "generating" while the background solve is still running,
    then "draft" (succeeded — `entries` is populated) or "failed"
    (`error_message` explains why). The frontend polls GET
    /api/timetables/{id} using this shape until status != "generating".
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    school_id: int
    status: str
    solver_status: str | None
    error_message: str | None
    # Plain-language rewrite of error_message (see
    # app/services/infeasibility_explainer.py) — null whenever that
    # service didn't run or couldn't produce one, in which case the
    # frontend just shows error_message's bulleted list on its own.
    error_explanation: str | None = None
    entries: list[TimetableEntryOut]
    # Rules this timetable currently breaks. Normally empty: the solver was
    # given the same rules, so a freshly generated timetable should honour them
    # all. It fills up when someone moves a slot by hand - a manual move that
    # double-books nobody passes every physical check while still breaking a
    # rule, and without this the Constraints tab goes on calling that rule
    # enforced while the timetable disagrees.
    #
    # A violation on an UNTOUCHED timetable means something else: the solver and
    # the checker disagree, and one of them is wrong. That has happened three
    # times so far, each time silently.
    violations: list[ViolationOut] = []


class EditCommandRequest(BaseModel):
    """POST /api/timetables/{id}/edit-command — plain-English editing
    instead of drag-and-drop, e.g. "move Grade 8's Math to period 2 on
    Wednesdays" or "lock Mrs. Sharma's Monday classes". See
    app/services/edit_command_parser.py for how this gets resolved."""

    text: str


class EditCommandResponse(BaseModel):
    """`entries` is the one or two rows actually changed (one for a
    move/lock/unlock, two for a swap) — same shape PATCH .../entries/{id}
    and POST .../swap-with/{id} already return, so the frontend can patch
    local state with the exact same applyEntryUpdates(...entries) call
    either way, regardless of which UI triggered the change."""

    action: str
    description: str
    entries: list[TimetableEntryOut]


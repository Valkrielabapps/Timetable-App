from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.access import require_school_access
from app.core.rate_limit import check_quota
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.school import ClassGroup, Constraint, Period, Subject, Teacher
from app.models.user import User
from app.schemas.constraint import (
    ConstraintBatchParseRequest,
    ConstraintCreate,
    ConstraintOut,
    ConstraintParseRequest,
    ConstraintParseResponse,
    ConstraintReparseRequest,
    ConstraintUpdate,
)
from app.services import constraint_parser as regex_parser
from app.services.llm_constraint_parser import (
    ParsedConstraint,
    parse_constraint_llm,
    parse_constraints_batch_llm,
)

router = APIRouter(prefix="/api/constraints", tags=["constraints"])


def _is_enforced(constraint: Constraint) -> bool:
    """Whether this constraint row is actually read by the solver — see
    app/services/solver.py. Kept in one place so the API response
    (ConstraintOut.enforced) and the /parse endpoint agree, instead of two
    copies of this logic drifting apart."""
    p = constraint.parameters or {}
    if constraint.type == "workload_limit":
        return "teacher_id" in p and "max_periods_per_week" in p
    if constraint.type == "availability":
        return "teacher_id" in p and "day_of_week" in p
    if constraint.type in ("no_subject_period", "require_subject_period"):
        return "subject_id" in p and p.get("position") in ("first", "last")
    if constraint.type in ("no_subject_day", "require_subject_day"):
        return "subject_id" in p and isinstance(p.get("day_of_week"), int)
    if constraint.type == "max_consecutive_periods":
        max_consecutive = p.get("max_consecutive")
        has_target = "subject_id" in p or "teacher_id" in p
        return has_target and isinstance(max_consecutive, int) and max_consecutive >= 1
    if constraint.type == "min_gap_between_subjects":
        min_gap = p.get("min_gap")
        return "first_subject_id" in p and "second_subject_id" in p and isinstance(min_gap, int) and min_gap >= 1
    if constraint.type == "subject_sequence":
        return "first_subject_id" in p and "second_subject_id" in p
    return False


def _scopes_overlap(a: list[int] | None, b: list[int] | None) -> bool:
    """None means "school-wide", which overlaps with any scope, including
    another school-wide constraint. Two specific scopes overlap if they
    share at least one class_group_id."""
    if a is None or b is None:
        return True
    return bool(set(a) & set(b))


def _find_placement_conflicts(
    db: Session, school_id: int, constraint_id: int | None, constraint_type: str, parameters: dict
) -> list[str]:
    """
    Flags the one placement contradiction that's cleanly detectable without
    needing the rest of the school's data: two 'require_subject_period'
    constraints on the same subject, with overlapping scope, but different
    positions ('first' vs 'last'). The solver intersects every 'require'
    constraint's eligible-period set for a given requirement (see
    generate_school_timetable in app/services/solver.py) — first-period and
    last-period sets don't overlap on any school with more than one period a
    day, so requiring both at once means that subject can NEVER be
    scheduled, no matter what else is true. Every other kind of
    contradiction (e.g. a workload cap that's too low given the school's
    actual current subject load) depends on data outside this one
    constraint and is handled instead by _diagnose_infeasibility at
    generation time (app/services/solver.py), not here.

    constraint_id is excluded from the comparison (None when checking a
    not-yet-saved constraint, e.g. from /parse) so a constraint never
    conflicts with itself.
    """
    if constraint_type != "require_subject_period":
        return []
    subject_id = parameters.get("subject_id")
    position = parameters.get("position")
    if not subject_id or position not in ("first", "last"):
        return []

    query = db.query(Constraint).filter(
        Constraint.school_id == school_id,
        Constraint.type == "require_subject_period",
    )
    if constraint_id is not None:
        query = query.filter(Constraint.id != constraint_id)
    others = query.all()
    conflicts = []
    for other in others:
        p = other.parameters or {}
        if p.get("subject_id") != subject_id:
            continue
        other_position = p.get("position")
        if other_position not in ("first", "last") or other_position == position:
            continue
        if not _scopes_overlap(parameters.get("class_group_ids"), p.get("class_group_ids")):
            continue
        conflicts.append(
            f"Contradicts constraint #{other.id} ('{other.description}'), which requires the same "
            f"subject to be the {other_position} period instead — a subject can't satisfy both at "
            f"once, so it will never be schedulable. Remove or rescope one of the two."
        )
    return conflicts


def _find_day_conflicts(
    db: Session, school_id: int, constraint_id: int | None, constraint_type: str, parameters: dict
) -> list[str]:
    """
    Same idea as _find_placement_conflicts but for the day-based placement
    types: 'require_subject_day' pins a subject to exactly one day of the
    week; two 'require_subject_day' rows for the same subject naming
    different days (with overlapping scope) can never both hold, and
    neither can a 'require_subject_day' plus a 'no_subject_day' for the
    SAME day (one says "only this day", the other says "never this day").
    Kept as a separate function rather than folded into
    _find_placement_conflicts since the two placement dimensions
    (position vs. day) don't interact with each other.
    """
    if constraint_type not in ("no_subject_day", "require_subject_day"):
        return []
    subject_id = parameters.get("subject_id")
    day_of_week = parameters.get("day_of_week")
    if not subject_id or not isinstance(day_of_week, int):
        return []

    query = db.query(Constraint).filter(
        Constraint.school_id == school_id,
        Constraint.type.in_(["no_subject_day", "require_subject_day"]),
    )
    if constraint_id is not None:
        query = query.filter(Constraint.id != constraint_id)
    others = query.all()
    conflicts = []
    for other in others:
        p = other.parameters or {}
        if p.get("subject_id") != subject_id:
            continue
        other_day = p.get("day_of_week")
        if not isinstance(other_day, int):
            continue
        if not _scopes_overlap(parameters.get("class_group_ids"), p.get("class_group_ids")):
            continue
        if constraint_type == "require_subject_day" and other.type == "require_subject_day" and other_day != day_of_week:
            conflicts.append(
                f"Contradicts constraint #{other.id} ('{other.description}'), which requires the same "
                f"subject on a different day instead — a subject can only be pinned to one day, so "
                f"it will never be schedulable. Remove or rescope one of the two."
            )
        elif {constraint_type, other.type} == {"no_subject_day", "require_subject_day"} and other_day == day_of_week:
            conflicts.append(
                f"Contradicts constraint #{other.id} ('{other.description}') — one requires this "
                f"subject on that day, the other bans it that same day. Remove or rescope one of the two."
            )
    return conflicts


def _to_out(db: Session, constraint: Constraint) -> ConstraintOut:
    conflicts = _find_placement_conflicts(
        db, constraint.school_id, constraint.id, constraint.type, constraint.parameters or {}
    ) + _find_day_conflicts(
        db, constraint.school_id, constraint.id, constraint.type, constraint.parameters or {}
    )
    return ConstraintOut(
        id=constraint.id,
        school_id=constraint.school_id,
        type=constraint.type,
        parameters=constraint.parameters or {},
        is_hard=constraint.is_hard,
        weight=constraint.weight,
        description=constraint.description,
        source_text=constraint.source_text,
        parsed_by=constraint.parsed_by,
        enforced=_is_enforced(constraint),
        conflicts=conflicts,
    )


def _adapt_legacy(legacy: regex_parser.ParsedConstraint) -> ParsedConstraint:
    """The regex fallback parser (app/services/constraint_parser.py)
    predates the unified LLM-parser output shape and still names its two
    placement types directly ("no_subject_period" / "require_subject_period")
    instead of type="subject_period_position" + mode. Translate so the rest
    of this router only has to handle one shape regardless of which parser
    produced it."""
    if legacy.type in ("no_subject_period", "require_subject_period"):
        return ParsedConstraint(
            type="subject_period_position",
            description=legacy.description,
            teacher_name=legacy.teacher_name,
            subject_name=legacy.subject_name,
            position=legacy.position,
            mode="exclude" if legacy.type == "no_subject_period" else "require",
        )
    if legacy.type in ("no_subject_day", "require_subject_day"):
        return ParsedConstraint(
            type="subject_day_position",
            description=legacy.description,
            subject_name=legacy.subject_name,
            day_of_week=legacy.day_of_week,
            mode="exclude" if legacy.type == "no_subject_day" else "require",
        )
    if legacy.type == "max_consecutive_periods":
        return ParsedConstraint(
            type="max_consecutive_periods",
            description=legacy.description,
            teacher_name=legacy.teacher_name,
            subject_name=legacy.subject_name,
            max_consecutive=legacy.max_consecutive,
        )
    if legacy.type == "min_gap_between_subjects":
        return ParsedConstraint(
            type="min_gap_between_subjects",
            description=legacy.description,
            first_subject_name=legacy.first_subject_name,
            second_subject_name=legacy.second_subject_name,
            min_gap=legacy.min_gap,
        )
    if legacy.type == "subject_sequence":
        return ParsedConstraint(
            type="subject_sequence",
            description=legacy.description,
            teacher_name=legacy.teacher_name,
            first_subject_name=legacy.first_subject_name,
            second_subject_name=legacy.second_subject_name,
        )
    return ParsedConstraint(
        type=legacy.type,
        description=legacy.description,
        teacher_name=legacy.teacher_name,
        subject_name=legacy.subject_name,
        max_periods_per_week=legacy.max_periods_per_week,
        day_of_week=legacy.day_of_week,
    )


@router.post("", response_model=ConstraintOut, status_code=201)
def create_constraint(payload: ConstraintCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    constraint = Constraint(**payload.model_dump())
    db.add(constraint)
    db.commit()
    db.refresh(constraint)
    return _to_out(db, constraint)


@router.get("", response_model=list[ConstraintOut])
def list_constraints(school_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_school_access(db, current_user, school_id)
    query = db.query(Constraint).filter(Constraint.school_id == school_id)
    return [_to_out(db, c) for c in query.all()]


@router.get("/{constraint_id}", response_model=ConstraintOut)
def get_constraint(constraint_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    constraint = db.get(Constraint, constraint_id)
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")
    require_school_access(db, current_user, constraint.school_id)
    return _to_out(db, constraint)


@router.put("/{constraint_id}", response_model=ConstraintOut)
def update_constraint(constraint_id: int, payload: ConstraintUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Direct field edit — most useful for adjusting `parameters.class_group_ids`
    (the scope of a placement/consecutive/sequence constraint) without
    re-typing and re-parsing the whole rule, e.g. TimetableTab's scope
    picker sends {"parameters": {...same dict, class_group_ids: [...]}}. For
    changing the rule's actual meaning from new free text, use
    PUT /{constraint_id}/reparse instead.
    """
    constraint = db.get(Constraint, constraint_id)
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")
    require_school_access(db, current_user, constraint.school_id, min_role="admin")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(constraint, field, value)
    db.commit()
    db.refresh(constraint)
    return _to_out(db, constraint)


@router.delete("/{constraint_id}", status_code=204)
def delete_constraint(constraint_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    constraint = db.get(Constraint, constraint_id)
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")
    require_school_access(db, current_user, constraint.school_id, min_role="admin")
    db.delete(constraint)
    db.commit()


@dataclass
class _ResolvedConstraint:
    """What a piece of constraint text resolved to, ready to become a row.

    A named shape rather than a tuple because it grew past three fields once
    `source_text` and `parsed_by` were recorded, and `(str, dict, str, str,
    str)` at three call sites is a positional-argument bug waiting to happen.
    """

    db_type: str
    parameters: dict
    description: str
    source_text: str | None
    parsed_by: str | None


@dataclass
class _ResolutionData:
    """Everything needed to turn a ParsedConstraint's *names* (teacher_name,
    subject_name, ...) into this school's actual row ids — fetched once
    per request (not once per rule) so a batch of N rules costs one set of
    three queries, not N."""

    teacher_by_name: dict[str, Teacher]
    subject_by_name: dict[str, Subject]
    # A "class group label" can name a whole grade (matches every section
    # in it) or one specific section, so constraint text can say either
    # "Grade 3" or "Grade 3 - A" and both resolve.
    label_to_class_groups: dict[str, list[ClassGroup]]
    teacher_names: list[str]
    subject_names: list[str]
    class_group_labels: list[str]
    # (day_of_week, order, label) per period, for the LLM prompt's timetable
    # structure summary - see _period_summary in llm_constraint_parser.py.
    periods: list[tuple[int, int, str | None, bool]]


def _load_resolution_data(db: Session, school_id: int) -> _ResolutionData:
    teachers = db.query(Teacher).filter(Teacher.school_id == school_id).all()
    subjects = db.query(Subject).filter(Subject.school_id == school_id).all()
    class_groups = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    periods = db.query(Period).filter(Period.school_id == school_id).all()

    label_to_class_groups: dict[str, list[ClassGroup]] = {}
    for grade in sorted({cg.grade for cg in class_groups if cg.grade}):
        label_to_class_groups[grade] = [cg for cg in class_groups if cg.grade == grade]
    for cg in class_groups:
        label = f"{cg.grade} - {cg.name}" if cg.grade else cg.name
        label_to_class_groups[label] = [cg]

    return _ResolutionData(
        teacher_by_name={t.name: t for t in teachers},
        subject_by_name={s.name: s for s in subjects},
        label_to_class_groups=label_to_class_groups,
        teacher_names=[t.name for t in teachers],
        subject_names=[s.name for s in subjects],
        class_group_labels=list(label_to_class_groups.keys()),
        periods=[(p.day_of_week, p.order, p.label, p.is_break) for p in periods],
    )


def _parse_text_to_constraint(text: str, data: _ResolutionData) -> ParsedConstraint:
    """Parsing tries Claude first (app/services/llm_constraint_parser.py),
    which understands far more phrasing and constraint types than the
    regex parser. If no ANTHROPIC_API_KEY is configured, or the API call
    fails for any reason, it falls back to the regex parser
    (app/services/constraint_parser.py) — via _adapt_legacy, since that
    parser predates the unified output shape — so constraint entry never
    just breaks because of an LLM/network issue."""
    parsed = parse_constraint_llm(
        text, data.teacher_names, data.subject_names, data.class_group_labels, data.periods
    )
    if parsed is None:
        legacy = regex_parser.parse_constraint(text, data.teacher_names, data.subject_names)
        parsed = _adapt_legacy(legacy)
        # Tagged here rather than inside _adapt_legacy, which has several
        # return points and would need the same line on each.
        parsed.parsed_by = "regex"
    return parsed


def _apply_parsed_constraint(
    db: Session,
    school_id: int,
    parsed: ParsedConstraint,
    data: _ResolutionData,
    source_text: str | None = None,
) -> _ResolvedConstraint:
    """
    Turns one already-parsed ParsedConstraint into (db_type, parameters,
    description) — the second half of what used to be
    _resolve_constraint_text, split out so both the single-constraint path
    (_resolve_constraint_text below) and the batch path
    (_resolve_constraints_batch_text) can resolve N parsed rules against
    the SAME pre-fetched teacher/subject/class-group lookups (`data`),
    instead of re-querying the database once per rule.

    Types and how they're wired:
      - workload_limit    -> Teacher.max_periods_per_week
      - availability      -> adds the matched day's periods to
                             Teacher.unavailable_period_ids
      - subject_period_position (mode=require|exclude) -> stored as
                             Constraint(type="require_subject_period" or
                             "no_subject_period", parameters={subject_id,
                             position, class_group_ids?}); read directly by
                             the solver. class_group_ids scopes the rule to
                             specific sections/grades; omitted = school-wide.
      - max_consecutive_periods -> stored as parameters={subject_id,
                             max_consecutive, class_group_ids?} (subject
                             variant) or {teacher_id, max_consecutive}
                             (teacher variant — not scoped to class groups,
                             since it caps that teacher's whole schedule);
                             read directly by the solver.
      - subject_day_position (mode=require|exclude) -> stored as
                             Constraint(type="require_subject_day" or
                             "no_subject_day", parameters={subject_id,
                             day_of_week, class_group_ids?}); read directly
                             by the solver, same require/exclude shape as
                             subject_period_position but for a whole day
                             instead of first/last period.
      - min_gap_between_subjects -> stored as parameters={
                             first_subject_id, second_subject_id, min_gap,
                             class_group_ids?}; read directly by the
                             solver.
      - subject_sequence  -> stored as parameters={first_subject_id,
                             second_subject_id, class_group_ids?}; read
                             directly by the solver (forbids
                             second_subject from the period right after
                             first_subject, same class, any day).

    Anything else (no match, or the catch-all scheduling_rule bucket) is
    still returned and shown in the UI, just not applied to the solve.
    """
    teacher_by_name = data.teacher_by_name
    subject_by_name = data.subject_by_name
    label_to_class_groups = data.label_to_class_groups

    matched_teacher = teacher_by_name.get(parsed.teacher_name) if parsed.teacher_name else None
    matched_subject = subject_by_name.get(parsed.subject_name) if parsed.subject_name else None
    matched_class_groups = label_to_class_groups.get(parsed.class_group_name) if parsed.class_group_name else None
    matched_first_subject = subject_by_name.get(parsed.first_subject_name) if parsed.first_subject_name else None
    matched_second_subject = subject_by_name.get(parsed.second_subject_name) if parsed.second_subject_name else None

    parameters: dict = {}
    db_type = parsed.type

    if parsed.type == "workload_limit" and matched_teacher and parsed.max_periods_per_week:
        matched_teacher.max_periods_per_week = parsed.max_periods_per_week
        parameters = {"teacher_id": matched_teacher.id, "max_periods_per_week": parsed.max_periods_per_week}

    elif parsed.type == "availability" and matched_teacher and parsed.day_of_week is not None:
        day_period_ids = [
            p.id for p in db.query(Period).filter(
                Period.school_id == school_id,
                Period.day_of_week == parsed.day_of_week,
            ).all()
        ]
        existing = set(matched_teacher.unavailable_period_ids or [])
        matched_teacher.unavailable_period_ids = sorted(existing | set(day_period_ids))
        parameters = {"teacher_id": matched_teacher.id, "day_of_week": parsed.day_of_week}

    elif parsed.type == "subject_period_position":
        db_type = {"exclude": "no_subject_period", "require": "require_subject_period"}.get(parsed.mode, "scheduling_rule")
        if matched_subject and parsed.position and parsed.mode in ("require", "exclude"):
            parameters = {"subject_id": matched_subject.id, "position": parsed.position}
            if matched_class_groups:
                parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]
        elif matched_subject:
            parameters = {"subject_id": matched_subject.id}

    elif parsed.type == "subject_day_position":
        db_type = {"exclude": "no_subject_day", "require": "require_subject_day"}.get(parsed.mode, "scheduling_rule")
        if matched_subject and parsed.day_of_week is not None and parsed.mode in ("require", "exclude"):
            parameters = {"subject_id": matched_subject.id, "day_of_week": parsed.day_of_week}
            if matched_class_groups:
                parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]
        elif matched_subject:
            parameters = {"subject_id": matched_subject.id}

    elif parsed.type == "max_consecutive_periods":
        # Teacher variant caps that teacher's own back-to-back periods
        # across their whole schedule (any subject/class), so it's not
        # scoped to class groups — only the subject variant is.
        if matched_teacher and not matched_subject and parsed.max_consecutive and parsed.max_consecutive >= 1:
            parameters = {"teacher_id": matched_teacher.id, "max_consecutive": parsed.max_consecutive}
        elif matched_subject and parsed.max_consecutive and parsed.max_consecutive >= 1:
            parameters = {"subject_id": matched_subject.id, "max_consecutive": parsed.max_consecutive}
            if matched_class_groups:
                parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]
        elif matched_subject:
            parameters = {"subject_id": matched_subject.id}
        elif matched_teacher:
            parameters = {"teacher_id": matched_teacher.id}

    elif parsed.type == "min_gap_between_subjects":
        if matched_first_subject and matched_second_subject and parsed.min_gap and parsed.min_gap >= 1:
            parameters = {
                "first_subject_id": matched_first_subject.id,
                "second_subject_id": matched_second_subject.id,
                "min_gap": parsed.min_gap,
            }
            if matched_class_groups:
                parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]
        else:
            if matched_first_subject:
                parameters["first_subject_id"] = matched_first_subject.id
            if matched_second_subject:
                parameters["second_subject_id"] = matched_second_subject.id

    elif parsed.type == "subject_sequence":
        if matched_first_subject and matched_second_subject:
            parameters = {
                "first_subject_id": matched_first_subject.id,
                "second_subject_id": matched_second_subject.id,
            }
            if matched_class_groups:
                parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]
        else:
            if matched_first_subject:
                parameters["first_subject_id"] = matched_first_subject.id
            if matched_second_subject:
                parameters["second_subject_id"] = matched_second_subject.id

    else:
        if matched_teacher:
            parameters["teacher_id"] = matched_teacher.id
        if matched_subject:
            parameters["subject_id"] = matched_subject.id
        if matched_class_groups:
            parameters["class_group_ids"] = [cg.id for cg in matched_class_groups]

    return _ResolvedConstraint(
        db_type=db_type,
        parameters=parameters,
        description=parsed.description,
        source_text=source_text,
        parsed_by=parsed.parsed_by,
    )


def _resolve_constraint_text(db: Session, school_id: int, text: str) -> _ResolvedConstraint:
    """
    Shared by both POST /parse (new constraint) and PUT /{id}/reparse
    (editing an existing one's text in place): turns plain-English text
    into (db_type, parameters, description) — load the school's
    teacher/subject/class-group names once, parse the one rule, then
    resolve it. See _apply_parsed_constraint for what each constraint
    type resolves to.
    """
    data = _load_resolution_data(db, school_id)
    parsed = _parse_text_to_constraint(text, data)
    return _apply_parsed_constraint(db, school_id, parsed, data, source_text=text)


def _resolve_constraints_batch_text(db: Session, school_id: int, text: str) -> list[_ResolvedConstraint]:
    """
    Batch counterpart to _resolve_constraint_text, used by POST
    /api/constraints/batch: turns a whole block of text — several rules
    written together, one per line or run into a paragraph — into a list
    of (db_type, parameters, description) tuples, one per distinct rule
    found.

    Tries parse_constraints_batch_llm first, which sees the whole block at
    once and can split it into rules more intelligently than a naive
    split (e.g. a rule that wraps across two lines, or several rules
    separated by commas in one sentence). If that's unavailable (no
    ANTHROPIC_API_KEY, package missing, or the call failed) or the model
    returned nothing usable, falls back to treating each non-empty line as
    its own rule and running it through the same single-constraint
    pipeline every /parse request already uses (LLM-per-line, then regex)
    — a reasonable assumption for a fallback path, since the batch-entry
    UI's placeholder text encourages one rule per line anyway.
    """
    data = _load_resolution_data(db, school_id)

    parsed_list = parse_constraints_batch_llm(
        text, data.teacher_names, data.subject_names, data.class_group_labels, data.periods
    )
    if not parsed_list:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        # The per-line fallback knows exactly which line produced which rule,
        # so each row records its own sentence rather than the whole paste.
        return [
            _apply_parsed_constraint(db, school_id, _parse_text_to_constraint(line, data), data, source_text=line)
            for line in lines
        ]

    # The batch model splits the block itself, so there is no per-rule
    # sentence to attribute - every row records the paste it came from.
    for parsed in parsed_list:
        parsed.parsed_by = "llm"
    return [
        _apply_parsed_constraint(db, school_id, parsed, data, source_text=text)
        for parsed in parsed_list
    ]


@router.post("/parse", response_model=ConstraintParseResponse, status_code=201)
def parse_and_create_constraint(payload: ConstraintParseRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Take plain-English constraint text, parse it (see
    _resolve_constraint_text), and save it as a new Constraint row."""
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    # Per-user, not per-IP: this spends Anthropic credit per call, and the
    # realistic overspend is one authenticated client looping, not anonymous
    # abuse. Generous enough that entering rules by hand never trips it.
    check_quota(f"llm:{current_user.id}", limit=60, window_seconds=3600)
    resolved = _resolve_constraint_text(db, payload.school_id, payload.text)

    constraint = Constraint(
        school_id=payload.school_id,
        type=resolved.db_type,
        parameters=resolved.parameters,
        is_hard=True,
        description=resolved.description,
        source_text=resolved.source_text,
        parsed_by=resolved.parsed_by,
    )
    db.add(constraint)
    db.commit()
    db.refresh(constraint)

    out = _to_out(db, constraint)
    return ConstraintParseResponse(constraint=out, enforced=out.enforced)


@router.post("/batch", response_model=list[ConstraintParseResponse], status_code=201)
def parse_and_create_constraints_batch(
    payload: ConstraintBatchParseRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    Batch counterpart to POST /parse: takes a whole block of free text —
    several rules an admin pasted or typed together, e.g. one per line —
    and creates one Constraint row per distinct rule found, instead of
    requiring a separate request (and a separate round of typing) per
    sentence. See _resolve_constraints_batch_text for how the text gets
    split into individual rules, with and without an LLM available.

    Every row is created and committed before any conflict-checking
    happens (`_to_out` below), so a rule that contradicts another rule
    from the SAME batch gets flagged exactly like it would if the two had
    been entered one at a time in separate requests — conflict detection
    is DB-driven (queries every constraint of this type for the school),
    not batch-scoped, so there's no special-casing needed here for
    "conflicts with a sibling from this same paste" versus "conflicts
    with something already saved."
    """
    require_school_access(db, current_user, payload.school_id, min_role="admin")
    # Tighter than /parse: a batch sends a whole pasted block in one prompt,
    # so each call costs several times what a single-sentence parse does.
    check_quota(f"llm-batch:{current_user.id}", limit=20, window_seconds=3600)
    resolved = _resolve_constraints_batch_text(db, payload.school_id, payload.text)
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="Couldn't find any constraints in that text. Try one clear rule per line.",
        )

    created = []
    for item in resolved:
        constraint = Constraint(
            school_id=payload.school_id,
            type=item.db_type,
            parameters=item.parameters,
            is_hard=True,
            description=item.description,
            source_text=item.source_text,
            parsed_by=item.parsed_by,
        )
        db.add(constraint)
        created.append(constraint)
    db.commit()
    for constraint in created:
        db.refresh(constraint)

    responses = []
    for constraint in created:
        out = _to_out(db, constraint)
        responses.append(ConstraintParseResponse(constraint=out, enforced=out.enforced))
    return responses


@router.put("/{constraint_id}/reparse", response_model=ConstraintParseResponse)
def reparse_constraint(constraint_id: int, payload: ConstraintReparseRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Re-parses new text into an EXISTING constraint row instead of creating
    a new one — what TimetableTab.jsx's "Edit" affordance calls when you
    fix a typo or reword a rule, so its id (and position in the list)
    stays stable instead of a delete-then-recreate. Goes through the same
    _resolve_constraint_text as a brand-new constraint, so an edited rule
    behaves identically to one typed fresh.
    """
    constraint = db.get(Constraint, constraint_id)
    if not constraint:
        raise HTTPException(status_code=404, detail="Constraint not found")
    require_school_access(db, current_user, constraint.school_id, min_role="admin")

    resolved = _resolve_constraint_text(db, constraint.school_id, payload.text)
    constraint.type = resolved.db_type
    constraint.parameters = resolved.parameters
    constraint.description = resolved.description
    # A reword replaces the rule, so the recorded input replaces it too -
    # keeping the original would attribute the new type to text that never
    # produced it.
    constraint.source_text = resolved.source_text
    constraint.parsed_by = resolved.parsed_by
    db.commit()
    db.refresh(constraint)

    out = _to_out(db, constraint)
    return ConstraintParseResponse(constraint=out, enforced=out.enforced)

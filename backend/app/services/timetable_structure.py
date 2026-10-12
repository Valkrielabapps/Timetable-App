"""
A school's week, set up once instead of period by period.

Before this, every period of every day was its own row an admin added by
hand: "Monday, slot 3". A school with eight periods over six days typed in
forty-eight of them, and a change to the day - lunch moving, a class teacher
period added - meant editing every one. Now the admin says what the day looks
like and this module makes the rows:

    days            which weekdays are working days
    periods_per_day the ordinary periods, the same every day
    short_days      a day with fewer (a half-day Saturday)
    breaks          "after period 3", "after period 6", with their names
    class teacher   a period where each section is with its class teacher,
                    at the start of the day or after a given period
    zero period     a free slot for activities - the same for the whole school
                    or different per grade, at one point every day or a
                    different point per day

Numbering
---------
Only lesson slots are numbered, so "period 1" is always the first lesson
whatever comes before it - adding a class teacher period at the start does
not quietly shift every saved rule that says "period 1".

A zero period is either a slot of its own or a reservation, and the
difference is what keeps numbering honest. Free for the whole school at the
same point every day, nobody is taught in it, so it is a slot like a break
and takes no number. Anywhere else - per grade, or moving between days - some
sections are being taught in it while others are not, so it is an ordinary
numbered lesson slot that is kept free for the grades it belongs to (a
ZeroPeriod row). Each day then has one more numbered period than the school's
lesson count, and every section still gets that many lessons.

Updating in place
-----------------
Teacher unavailability, timetable entries and zero reservations point at
Period rows by id. Rebuilding the rows from scratch would orphan all of
them, so applying a structure matches the new slots against the old ones -
lesson 3 is lesson 3, the break after period 4 is that break - and only adds
or removes what actually changed. Whatever has to go is reported back rather
than vanishing quietly.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.school import (
    ClassGroup, Constraint, Period, Teacher, Timetable, TimetableEntry, ZeroPeriod,
)
from app.schemas.timetable_structure import (
    BreakSlot, ClassTeacherPeriodConfig, StructureReport, TimetableStructure, ZeroPeriodConfig,
    ZeroPlacement,
)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

KIND_LABELS = {"class_teacher": "Class teacher period", "zero": "Zero period", "break": "Break"}


class StructureError(ValueError):
    """A structure that can't be laid out, with a reason meant for a person."""


# ---------------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------------


def lesson_numbers(periods) -> dict[int, int]:
    """period id -> its number in the day, for lesson slots only.

    The number a person sees and says: "period 5" is the fifth lesson of that
    day, not the fifth row - breaks, the class teacher period and a
    school-wide zero period sit between numbers without taking one.
    """
    by_day: dict[int, list] = defaultdict(list)
    for p in periods:
        if not p.is_break:
            by_day[p.day_of_week].append(p)
    out: dict[int, int] = {}
    for day_periods in by_day.values():
        for number, p in enumerate(sorted(day_periods, key=lambda p: p.order), start=1):
            out[p.id] = number
    return out


def describe_periods(db: Session, school_id: int, periods=None) -> list[dict]:
    """Every period of a school as the API shows it: with its number and the
    zero periods reserved on it, which no single row can work out alone."""
    if periods is None:
        periods = (
            db.query(Period)
            .filter(Period.school_id == school_id)
            .order_by(Period.day_of_week, Period.order)
            .all()
        )
    numbers = lesson_numbers(periods)
    zero: dict[int, list[str | None]] = defaultdict(list)
    ids = [p.id for p in periods]
    if ids:
        for z in db.query(ZeroPeriod).filter(ZeroPeriod.period_id.in_(ids)).all():
            zero[z.period_id].append(z.grade)
    return [
        {
            "id": p.id, "school_id": p.school_id, "day_of_week": p.day_of_week, "order": p.order,
            "label": p.label, "kind": p.kind or "lesson", "is_break": p.is_break,
            "number": numbers.get(p.id),
            "zero_all": None in zero.get(p.id, []),
            "zero_grades": sorted(g for g in zero.get(p.id, []) if g is not None),
        }
        for p in periods
    ]


def zero_period_ids_for(db: Session, school_id: int, grade: str | None) -> set[int]:
    """Lesson slots a section of this grade has no lessons in."""
    out = set()
    for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all():
        if z.grade is None or (grade is not None and z.grade == grade):
            out.add(z.period_id)
    return out


# ---------------------------------------------------------------------------
# Laying out a day
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Slot:
    kind: str
    label: str | None
    # How a slot is recognised across two versions of a structure, so an
    # existing row can be kept rather than replaced.
    key: tuple


def _zero_is_numbered(cfg: TimetableStructure) -> bool:
    """Whether the zero period is a reservation on a numbered slot (True) or a
    slot of its own (False) - see the module docstring."""
    z = cfg.zero_period
    if not z.enabled:
        return False
    whole_school_fixed = (
        z.scope == "school" and len(z.placements) == 1 and z.placements[0].every_day is not None
    )
    return not whole_school_fixed


def _lessons_on(cfg: TimetableStructure, day: int) -> int:
    """Numbered slots on a day: its periods, plus one when the zero period is
    a reservation and so needs a slot of its own to sit in."""
    return cfg.short_days.get(day, cfg.periods_per_day) + (1 if _zero_is_numbered(cfg) else 0)


def layout(cfg: TimetableStructure, day: int) -> list[Slot]:
    """The slots of one day, in order."""
    lessons = _lessons_on(cfg, day)
    z = cfg.zero_period
    zero_at = z.placements[0].every_day if z.enabled and not _zero_is_numbered(cfg) else None
    breaks_after: dict[int, list[str]] = defaultdict(list)
    for b in cfg.breaks:
        breaks_after[b.after].append(b.label)
    ct = cfg.class_teacher_period

    out: list[Slot] = []

    def class_teacher_after(k: int) -> None:
        if ct.enabled and ct.after == k:
            out.append(Slot("class_teacher", None, ("class_teacher",)))

    class_teacher_after(0)
    for k in range(1, lessons + 1):
        if zero_at == k:
            out.append(Slot("zero", None, ("zero",)))
        out.append(Slot("lesson", None, ("lesson", k)))
        # Nothing hangs off the last period: a break or class teacher period
        # after it would just be the end of the day. A short day simply has no
        # break that falls after its last period.
        if k < lessons:
            class_teacher_after(k)
            for i, label in enumerate(breaks_after.get(k, [])):
                out.append(Slot("break", label, ("break", k, i)))
    if zero_at == lessons + 1:
        out.append(Slot("zero", None, ("zero",)))
    return out


def _reservations(cfg: TimetableStructure) -> set[tuple[int, int, str | None]]:
    """(day, period number, grade) for each zero period kept as a reservation."""
    if not _zero_is_numbered(cfg):
        return set()
    out = set()
    for placement in cfg.zero_period.placements:
        for day in cfg.days:
            number = placement.every_day
            if number is None:
                number = (placement.by_day or {}).get(day)
            if number is not None and number <= _lessons_on(cfg, day):
                out.add((day, number, placement.grade))
    return out


def validate(cfg: TimetableStructure, grades: set[str]) -> None:
    if not cfg.days:
        raise StructureError("Choose at least one working day.")
    if len(set(cfg.days)) != len(cfg.days) or any(not 0 <= d <= 6 for d in cfg.days):
        raise StructureError("Working days must be distinct days of the week.")
    for day, n in cfg.short_days.items():
        if day not in cfg.days:
            raise StructureError(f"{DAY_NAMES[day] if 0 <= day <= 6 else day} isn't a working day.")
        if not 1 <= n < cfg.periods_per_day:
            raise StructureError(
                f"A shorter day needs between 1 and {cfg.periods_per_day - 1} periods "
                f"({DAY_NAMES[day]} has {n})."
            )

    numbered_max = cfg.periods_per_day + (1 if _zero_is_numbered(cfg) else 0)
    seen_after = set()
    for b in cfg.breaks:
        if not 1 <= b.after < numbered_max:
            raise StructureError(
                f"A break has to come after a period between 1 and {numbered_max - 1} "
                f"(\"{b.label}\" is after period {b.after})."
            )
        if b.after in seen_after:
            raise StructureError(f"There are two breaks after period {b.after}.")
        seen_after.add(b.after)

    ct = cfg.class_teacher_period
    if ct.enabled and not 0 <= ct.after < numbered_max:
        raise StructureError(
            f"The class teacher period has to come before period {numbered_max} "
            f"(it is after period {ct.after})."
        )

    z = cfg.zero_period
    if not z.enabled:
        return
    if not z.placements:
        raise StructureError("Say where the zero period goes.")
    if z.scope == "school":
        if len(z.placements) != 1 or z.placements[0].grade is not None:
            raise StructureError("A whole-school zero period has one placement, for every grade.")
    else:
        names = [p.grade for p in z.placements]
        if any(g is None for g in names):
            raise StructureError("Each zero period placement needs a grade.")
        if len(set(names)) != len(names):
            raise StructureError("A grade has two zero period placements.")
        unknown = [g for g in names if g not in grades]
        if unknown:
            raise StructureError(f"No section has the grade {', '.join(unknown)}.")
    for p in z.placements:
        who = p.grade or "the whole school"
        if (p.every_day is None) == (p.by_day is None):
            raise StructureError(
                f"The zero period for {who} needs either one period for every day, "
                f"or a period per day - not both."
            )
        positions = {d: p.every_day for d in cfg.days} if p.every_day is not None else (p.by_day or {})
        if not positions:
            raise StructureError(f"The zero period for {who} isn't on any day.")
        for day, number in positions.items():
            if day not in cfg.days:
                raise StructureError(f"The zero period for {who} is on a day that isn't a working day.")
            slots = cfg.short_days.get(day, cfg.periods_per_day) + 1
            if not 1 <= number <= slots and p.every_day is None:
                raise StructureError(
                    f"{DAY_NAMES[day]} has {slots} periods with the zero period, so the zero "
                    f"period for {who} can't be period {number}."
                )
            if p.every_day is not None and not 1 <= number <= cfg.periods_per_day + 1:
                raise StructureError(
                    f"With the zero period a day has {cfg.periods_per_day + 1} periods, so it "
                    f"can't be period {number}."
                )


# ---------------------------------------------------------------------------
# Comparing with what the school has now
# ---------------------------------------------------------------------------


def _existing_slots(day_periods: list[Period]) -> list[tuple[tuple, Period]]:
    """(key, period) for a day's current rows, keyed the way layout() keys
    new slots, so the two can be matched."""
    out: list[tuple[tuple, Period]] = []
    used: set[tuple] = set()
    lessons = 0
    breaks_seen: dict[int, int] = defaultdict(int)
    for p in sorted(day_periods, key=lambda p: p.order):
        if p.kind == "lesson":
            lessons += 1
            key: tuple = ("lesson", lessons)
        elif p.kind == "break":
            key = ("break", lessons, breaks_seen[lessons])
            breaks_seen[lessons] += 1
        else:
            key = (p.kind,)
        if key in used:  # a second class teacher period on one day - can't be matched
            key = (*key, "duplicate", p.id)
        used.add(key)
        out.append((key, p))
    return out


@dataclass
class _Plan:
    # (period, new order, kind, label)
    updates: list[tuple[Period, int, str, str | None]] = field(default_factory=list)
    # (day, order, kind, label)
    inserts: list[tuple[int, int, str, str | None]] = field(default_factory=list)
    deletes: list[Period] = field(default_factory=list)
    reservations: set[tuple[int, int, str | None]] = field(default_factory=set)
    # Anything a timetable would notice: slots added, removed, changing kind
    # or position relative to each other, or a different zero period.
    # Renumbering `order` alone (a hand-made school counted from 1) is not.
    material: bool = False


def _plan(db: Session, school_id: int, cfg: TimetableStructure) -> _Plan:
    periods = db.query(Period).filter(Period.school_id == school_id).all()
    by_day: dict[int, list[Period]] = defaultdict(list)
    for p in periods:
        by_day[p.day_of_week].append(p)

    plan = _Plan()
    for day in sorted(set(by_day) | set(cfg.days)):
        existing = _existing_slots(by_day.get(day, []))
        wanted = layout(cfg, day) if day in cfg.days else []
        by_key = {key: p for key, p in existing}
        wanted_keys = {slot.key for slot in wanted}
        old_sequence = [(key, p.label if p.kind != "lesson" else None) for key, p in existing]
        new_sequence = []
        for order, slot in enumerate(wanted):
            current = by_key.get(slot.key)
            # Lessons keep whatever label they had (a time, say); the others
            # are named by the structure.
            label = (current.label if current else None) if slot.kind == "lesson" else slot.label
            new_sequence.append((slot.key, label if slot.kind != "lesson" else None))
            if current is not None:
                plan.updates.append((current, order, slot.kind, label))
            else:
                plan.inserts.append((day, order, slot.kind, label))
        plan.deletes.extend(p for key, p in existing if key not in wanted_keys)
        if old_sequence != new_sequence:
            plan.material = True

    plan.reservations = _reservations(cfg)
    numbers = lesson_numbers(periods)
    period_by_id = {p.id: p for p in periods}
    current_reservations = {
        (period_by_id[z.period_id].day_of_week, numbers.get(z.period_id), z.grade)
        for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all()
        if z.period_id in period_by_id
    }
    if current_reservations != plan.reservations:
        plan.material = True
    return plan


# ---------------------------------------------------------------------------
# Reading the structure back
# ---------------------------------------------------------------------------


def infer(db: Session, school_id: int) -> tuple[TimetableStructure | None, bool]:
    """The structure a school's current periods follow, and whether they
    follow it exactly.

    Read from the periods themselves rather than stored separately, so it can
    never disagree with them - including for a school set up by hand, or by
    the setup assistant, before structures existed. When the days don't all
    follow one pattern, the structure of the fullest day is returned and the
    second value says so: saving it will make every day match.
    """
    periods = db.query(Period).filter(Period.school_id == school_id).all()
    if not periods:
        return None, False
    numbers = lesson_numbers(periods)
    reservations = db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all()
    numbered = bool(reservations)

    by_day: dict[int, list[Period]] = defaultdict(list)
    for p in periods:
        by_day[p.day_of_week].append(p)

    lessons_by_day = {d: sum(1 for p in ps if p.kind == "lesson") for d, ps in by_day.items()}
    counts = {d: n - (1 if numbered else 0) for d, n in lessons_by_day.items()}
    days = sorted(d for d, n in counts.items() if n >= 1)
    if not days:
        return None, True
    full = max(counts[d] for d in days)
    reference = next(d for d in days if counts[d] == full)

    breaks: list[BreakSlot] = []
    ct = ClassTeacherPeriodConfig()
    zero_at: int | None = None
    lessons = 0
    for p in sorted(by_day[reference], key=lambda p: p.order):
        if p.kind == "lesson":
            lessons += 1
        elif p.kind == "break" and lessons >= 1 and lessons not in {b.after for b in breaks}:
            breaks.append(BreakSlot(after=lessons, label=p.label or "Break"))
        elif p.kind == "class_teacher" and not ct.enabled:
            ct = ClassTeacherPeriodConfig(enabled=True, after=lessons)
        elif p.kind == "zero" and zero_at is None:
            zero_at = lessons + 1

    zero = ZeroPeriodConfig()
    if zero_at is not None and not numbered:
        zero = ZeroPeriodConfig(enabled=True, scope="school", placements=[ZeroPlacement(every_day=zero_at)])
    elif numbered:
        period_by_id = {p.id: p for p in periods}
        by_grade: dict[str | None, dict[int, int]] = defaultdict(dict)
        for z in reservations:
            p = period_by_id.get(z.period_id)
            if p is not None and z.period_id in numbers:
                by_grade[z.grade][p.day_of_week] = numbers[z.period_id]
        placements = []
        for grade, positions in sorted(by_grade.items(), key=lambda kv: kv[0] or ""):
            distinct = set(positions.values())
            if len(distinct) == 1 and set(positions) == set(days):
                placements.append(ZeroPlacement(grade=grade, every_day=distinct.pop()))
            else:
                placements.append(ZeroPlacement(grade=grade, by_day=dict(sorted(positions.items()))))
        scope = "school" if all(p.grade is None for p in placements) else "grade"
        zero = ZeroPeriodConfig(enabled=True, scope=scope, placements=placements)

    cfg = TimetableStructure(
        days=days,
        periods_per_day=full,
        short_days={d: counts[d] for d in days if counts[d] < full},
        breaks=breaks,
        class_teacher_period=ct,
        zero_period=zero,
    )
    grades = {g for (g,) in db.query(ClassGroup.grade).filter(ClassGroup.school_id == school_id) if g}
    try:
        validate(cfg, grades)
    except StructureError:
        return cfg, True
    return cfg, _plan(db, school_id, cfg).material


# ---------------------------------------------------------------------------
# Applying
# ---------------------------------------------------------------------------


def _section_label(cg: ClassGroup) -> str:
    return f"{cg.grade} - {cg.name}" if cg.grade else cg.name


def _ir_period_numbers(parameters: dict) -> set[int]:
    """Every period number a stored rule names, wherever in it they are."""
    found: set[int] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "period_orders" and isinstance(value, list):
                    found.update(v for v in value if isinstance(v, int))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(parameters)
    return found


def apply(db: Session, school_id: int, cfg: TimetableStructure) -> StructureReport:
    """Make the school's periods follow `cfg`, keeping every row that still
    has a place in it. Commits."""
    grades = {g for (g,) in db.query(ClassGroup.grade).filter(ClassGroup.school_id == school_id) if g}
    validate(cfg, grades)
    plan = _plan(db, school_id, cfg)
    report = StructureReport(changed=plan.material)

    removed_ids = {p.id for p in plan.deletes}
    if removed_ids:
        report.timetable_entries_removed = (
            db.query(TimetableEntry)
            .filter(TimetableEntry.period_id.in_(removed_ids))
            .delete(synchronize_session=False)
        )
        for teacher in db.query(Teacher).filter(Teacher.school_id == school_id).all():
            current = teacher.unavailable_period_ids or []
            gone = [i for i in current if i in removed_ids]
            if gone:
                teacher.unavailable_period_ids = [i for i in current if i not in removed_ids]
                report.unavailability_removed.append(
                    f"{teacher.name}: {len(gone)} unavailable period"
                    f"{'' if len(gone) == 1 else 's'} no longer exist"
                    f"{'s' if len(gone) == 1 else ''}"
                )
        db.query(ZeroPeriod).filter(ZeroPeriod.period_id.in_(removed_ids)).delete(
            synchronize_session=False
        )
        for p in plan.deletes:
            db.delete(p)
        db.flush()
    report.periods_removed = len(removed_ids)

    # Every kept row is moved out of the way first: (school, day, order) is
    # unique, and reordering in place would collide part way through.
    for p, *_ in plan.updates:
        p.order = -p.id - 1
    db.flush()
    for p, order, kind, label in plan.updates:
        p.order, p.kind, p.label = order, kind, label
    db.flush()
    for day, order, kind, label in plan.inserts:
        db.add(Period(school_id=school_id, day_of_week=day, order=order, kind=kind, label=label))
    db.flush()
    report.periods_added = len(plan.inserts)

    db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).delete(synchronize_session=False)
    periods = db.query(Period).filter(Period.school_id == school_id).all()
    numbers = lesson_numbers(periods)
    by_position = {(p.day_of_week, numbers[p.id]): p for p in periods if p.id in numbers}
    for day, number, grade in sorted(plan.reservations, key=lambda r: (r[0], r[1], r[2] or "")):
        period = by_position.get((day, number))
        if period is not None:
            db.add(ZeroPeriod(school_id=school_id, period_id=period.id, grade=grade))

    most = max(_lessons_on(cfg, d) for d in cfg.days)
    for c in db.query(Constraint).filter(Constraint.school_id == school_id, Constraint.type == "ir").all():
        beyond = sorted(n for n in _ir_period_numbers(c.parameters or {}) if n > most)
        if beyond:
            report.rules_out_of_range.append(
                f"\"{c.description}\" mentions period {', '.join(map(str, beyond))}, "
                f"but no day has that many periods now."
            )

    if cfg.class_teacher_period.enabled:
        report.sections_without_class_teacher = sorted(
            _section_label(cg)
            for cg in db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
            if cg.class_teacher_id is None
        )

    report.timetable_outdated = plan.material and (
        db.query(Timetable).filter(Timetable.school_id == school_id, Timetable.status == "draft").first()
        is not None
    )
    db.commit()
    return report

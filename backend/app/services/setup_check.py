"""
Setup check: problems that will stop a timetable, found before generating.

Generating runs the solver for up to a minute and, when the setup can't
work, ends with "no timetable" and a diagnosis. Most of the reasons a school
hits are simple arithmetic on its setup - a section asked for more periods
than its week has, a teacher who alone must take more lessons than they have
free periods - and can be said in a second, before anything runs, next to a
link that opens the thing to change.

Each problem is either:
  error    - no timetable can exist until it's fixed. Only things that are
             certain go here: the solver would fail on them every time.
  warning  - generation works, but the result will be missing something
             (a lesson with no teacher, a lab lesson with no lab).

and carries a `fix`: what to open - a section's plan, a teacher, a block, a
rule, the rooms or the periods - so the page can take the admin there.

Deliberately simple and conservative: this does not run the solver's model,
and it says nothing it can't be sure of. A school that passes can still fail
on an interaction between several rules; that is what the failed-generation
diagnosis is for.
"""
from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.models.school import (
    ClassGroup, Constraint, ElectiveBlock, Period, Room, School, Subject, Teacher, ZeroPeriod,
)
from app.services import solver as _solver
from app.services import standard_rules as _std
from app.services.constraint_ir import IRError, Run, rule_from_dict

_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _label(cg: ClassGroup | None) -> str:
    if cg is None:
        return "a section"
    return f"{cg.grade} {cg.name}" if cg.grade else cg.name


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _issue(severity: str, kind: str, message: str, fix: dict) -> dict:
    return {"severity": severity, "kind": kind, "message": message, "fix": fix}


def _section_fix(cg: ClassGroup | None) -> dict:
    return {"type": "section", "id": cg.id if cg else None, "label": f"Open {_label(cg)}"}


def _teacher_fix(t: Teacher) -> dict:
    return {"type": "teacher", "id": t.id, "label": f"Open {t.name}"}


def _matching(options: list[tuple]) -> bool:
    """options: [(name, candidate teacher ids)]. Can each have its own
    teacher, all different (they run at once)?"""
    owner: dict[int, int] = {}

    def place(i: int, seen: set[int]) -> bool:
        for t in options[i][1]:
            if t in seen:
                continue
            seen.add(t)
            if t not in owner or place(owner[t], seen):
                owner[t] = i
                return True
        return False

    return all(place(i, set()) for i in range(len(options)))


def check_setup(db: Session, school_id: int) -> dict:
    school = db.get(School, school_id)
    token = _solver._STANDARD.set(_std.for_school(school))
    try:
        issues = _check(db, school_id, school)
    finally:
        _solver._STANDARD.reset(token)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def _check(db: Session, school_id: int, school: School | None) -> list[dict]:
    issues: list[dict] = []
    all_periods = db.query(Period).filter(Period.school_id == school_id).all()
    lessons = [p for p in all_periods if not p.is_break]
    if not lessons:
        return [_issue("error", "no_periods", "The school has no lesson periods yet, so there is nothing to "
                       "timetable. Set up the school day first.",
                       {"type": "periods", "id": None, "label": "Open the school day"})]
    lesson_ids = {p.id for p in lessons}
    day_of = {p.id: p.day_of_week for p in lessons}

    class_groups = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    cg_by_id = {cg.id: cg for cg in class_groups}
    frozen_ids = {cg.id for cg in class_groups if cg.frozen}
    teachers = db.query(Teacher).filter(Teacher.school_id == school_id).all()
    t_by_id = {t.id: t for t in teachers}
    subjects = {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
    rooms = db.query(Room).filter(Room.school_id == school_id).all()

    def sname(sid) -> str:
        return subjects[sid].name if sid in subjects else "A subject"

    # Periods each section can't use: zero periods for its grade, and the
    # end of a shorter day - the same sets the solver keeps them out of.
    zero_by_grade: dict = {}
    for z in db.query(ZeroPeriod).filter(ZeroPeriod.school_id == school_id).all():
        zero_by_grade.setdefault(z.grade, set()).add(z.period_id)
    from app.services.timetable_structure import grade_off_period_ids
    off_by_grade = grade_off_period_ids(lessons, school.grade_day_limits if school else None)
    off_by_cg = {
        cg.id: (zero_by_grade.get(None, set()) | zero_by_grade.get(cg.grade, set())
                | off_by_grade.get(cg.grade, set())) & lesson_ids
        for cg in class_groups
    }

    blocks = [b for b in db.query(ElectiveBlock).filter(ElectiveBlock.school_id == school_id)
              .order_by(ElectiveBlock.id).all() if b.options]

    # ------------------------------------------------------------------
    # 1. A section asked for more periods than its week has.
    # ------------------------------------------------------------------
    demand: dict[int, list[tuple[str, int]]] = {}
    for cg in class_groups:
        for r in cg.requirements:
            if r.periods_per_week:
                demand.setdefault(cg.id, []).append((sname(r.subject_id), r.periods_per_week))
    for b in blocks:
        for sid in b.section_ids:
            if sid in cg_by_id:
                demand.setdefault(sid, []).append((b.name, b.periods_per_week))
    for cg_id, parts in demand.items():
        if cg_id in frozen_ids:
            continue
        need = sum(n for _, n in parts)
        have = len(lessons) - len(off_by_cg.get(cg_id, ()))
        if need > have:
            cg = cg_by_id[cg_id]
            why = " (its grade's shorter day or zero periods take up the rest)" if off_by_cg.get(cg_id) else ""
            issues.append(_issue(
                "error", "section_overfull",
                f"{_label(cg)} needs {need} periods a week but its week has only {have}{why}. "
                f"Take {need - have} off its subjects' periods a week, or lengthen the day.",
                _section_fix(cg),
            ))

    # ------------------------------------------------------------------
    # Who can teach what. Mirrors the solver's own rules for "qualified".
    # ------------------------------------------------------------------
    requirements = [r for cg in class_groups if cg.id not in frozen_ids for r in cg.requirements
                    if r.periods_per_week]
    cands = {r.id: _solver._candidate_teacher_ids(r, teachers, t_by_id, cg_by_id) for r in requirements}

    def batches(r) -> int:
        n = subjects[r.subject_id].lab_batch_count if r.subject_id in subjects else None
        return n if isinstance(n, int) and n >= 2 else 1

    # Lessons a teacher can't avoid: theirs alone to teach.
    sure: dict[int, list[tuple[str, int]]] = {}

    def owe(tid: int, what: str, n: int) -> None:
        sure.setdefault(tid, []).append((what, n))

    for r in requirements:
        cg = cg_by_id.get(r.class_group_id)
        ids = cands[r.id]
        k = batches(r)
        if not ids:
            issues.append(_issue(
                "warning", "no_teacher",
                f"No teacher can teach {sname(r.subject_id)} in {_label(cg)}, so its lessons will be placed "
                f"with no teacher. Qualify a teacher for {sname(r.subject_id)}"
                f"{' in ' + cg.grade if cg and cg.grade else ''}, or pick one in the section's plan.",
                {"type": "teachers", "id": None, "label": "Open teachers"},
            ))
            continue
        if k > 1 and len(ids) < k:
            issues.append(_issue(
                "error", "lab_batches",
                f"{sname(r.subject_id)} in {_label(cg)} is split into {k} batches taught at the same time, "
                f"each by its own teacher, but only {_plural(len(ids), 'teacher')} can teach it. Qualify "
                f"another teacher, or split it into fewer batches.",
                _section_fix(cg),
            ))
            continue
        if len(ids) <= k:
            for tid in ids:
                owe(tid, f"{sname(r.subject_id)} in {_label(cg)}", r.periods_per_week)
        if r.assistant_teacher_id in t_by_id and k == 1:
            owe(r.assistant_teacher_id, f"assisting {sname(r.subject_id)} in {_label(cg)}", r.periods_per_week)

    # ------------------------------------------------------------------
    # 3. A shared block's groups all meet at once, so each needs its own
    #    teacher - and a group drawn from several sections needs one who
    #    may teach every one of them.
    # ------------------------------------------------------------------
    option_wrappers = []
    for b in blocks:
        members = [sid for sid in b.section_ids if sid in cg_by_id]
        if not members or any(sid in frozen_ids for sid in members):
            continue  # kept as it is with its frozen section
        home = cg_by_id.get(b.class_group_id) or cg_by_id[members[0]]
        fix = {"type": "block", "id": b.id, "class_group_id": home.id, "label": f"Open {b.name}"}
        groups = []
        for o in b.options:
            group = [sid for sid in o.group_section_ids if sid in members]
            if not group:
                continue
            allowed = None
            for sid in group:
                ids = _solver._candidate_teacher_ids(
                    SimpleNamespace(class_group_id=sid, subject_id=o.subject_id,
                                    preferred_teacher_id=o.preferred_teacher_id, allowed_teacher_ids=None),
                    teachers, t_by_id, cg_by_id)
                allowed = ids if allowed is None else [t for t in allowed if t in set(ids)]
            allowed = allowed or []
            name = sname(o.subject_id) + (f" ({o.label})" if o.label else "")
            where = ", ".join(_label(cg_by_id[s]) for s in group)
            if not allowed:
                issues.append(_issue(
                    "warning", "block_no_teacher",
                    f"No teacher can teach {name} in {b.name}" + (f" for all of {where}" if len(group) > 1 else "")
                    + ", so it will be placed with no teacher. Qualify a teacher for it"
                    + (" in every one of those grades." if len(group) > 1 else "."),
                    fix,
                ))
                continue
            groups.append((name, allowed))
            option_wrappers.append(SimpleNamespace(
                id=-o.id, class_group_id=group[0], subject_id=o.subject_id,
                periods_per_week=b.periods_per_week, block_id=b.id))
            if len(allowed) == 1:
                owe(allowed[0], f"{name} in {b.name}", b.periods_per_week)
        if len(groups) > 1 and not _matching(groups):
            # Name the teacher(s) who'd have to be in two groups at once.
            only = {}
            for name, allowed in groups:
                if len(allowed) == 1:
                    only.setdefault(allowed[0], []).append(name)
            clash = [(t, names) for t, names in only.items() if len(names) > 1]
            if clash:
                t, names = clash[0]
                detail = (f"{' and '.join(names)} can only be taught by {t_by_id[t].name}, who can't be in "
                          f"{_plural(len(names), 'group')} at once")
            else:
                staff = sorted({t_by_id[t].name for _, allowed in groups for t in allowed})
                detail = (f"its {len(groups)} groups need {len(groups)} different teachers, but only "
                          f"{', '.join(staff)} can teach them")
            issues.append(_issue(
                "error", "block_teacher_clash",
                f"{b.name}'s groups all meet at the same time, each with its own teacher, but {detail}. "
                f"Qualify another teacher for one of the groups, or pick a different teacher for it.",
                fix,
            ))

    # ------------------------------------------------------------------
    # 2. A teacher who alone must take more than they have free.
    # ------------------------------------------------------------------
    frozen_busy: dict[int, set[int]] = {}
    if frozen_ids:
        from app.services.freezing import frozen_source
        for cg in class_groups:
            if cg.id in frozen_ids:
                src = frozen_source(db, cg)
                for e in (src.entries if src else []):
                    if e.class_group_id == cg.id and e.teacher_id and e.period_id in lesson_ids:
                        frozen_busy.setdefault(e.teacher_id, set()).add(e.period_id)

    day_max = _solver._STANDARD.get().day_max

    def capacity(t: Teacher) -> tuple[int, str]:
        taken = frozen_busy.get(t.id, set())
        unavailable = set(t.unavailable_period_ids or [])
        free_ids = [pid for pid in lesson_ids if pid not in unavailable and pid not in taken]
        free = len(free_ids)
        reason = f"is free for only {_plural(free, 'period')}" if unavailable else f"has {free} free periods"
        if day_max is not None:
            by_day: dict[int, int] = {}
            for pid in free_ids:
                by_day[day_of[pid]] = by_day.get(day_of[pid], 0) + 1
            taken_day: dict[int, int] = {}
            for pid in taken:
                taken_day[day_of[pid]] = taken_day.get(day_of[pid], 0) + 1
            capped = sum(max(0, min(n, day_max - taken_day.get(d, 0))) for d, n in by_day.items())
            if capped < free:
                free, reason = capped, f"can teach at most {capped} (the school's limit of {day_max} a day)"
        cap = _solver._weekly_cap(t)
        if cap is not None and max(0, cap - len(taken)) < free:
            free = max(0, cap - len(taken))
            reason = f"is limited to {cap} periods a week"
        if taken:
            reason += f", and {len(taken)} of them already go to frozen sections"
        return free, reason

    teacher_errors = False
    for tid, owed in sure.items():
        t = t_by_id.get(tid)
        if t is None:
            continue
        need = sum(n for _, n in owed)
        have, reason = capacity(t)
        if need > have:
            teacher_errors = True
            owed.sort(key=lambda x: -x[1])
            listed = ", ".join(f"{w} ({n})" for w, n in owed[:5]) + (f" and {len(owed) - 5} more" if len(owed) > 5 else "")
            issues.append(_issue(
                "error", "teacher_overloaded",
                f"{t.name} is the only teacher for {listed}: {need} periods a week, but {reason}. "
                f"Raise their limit or free time, or give some of these to another teacher.",
                _teacher_fix(t),
            ))

    # Every sole-teacher load fits, but sections may still not share out:
    # the solver's own staffing check, which needs no timetable to run.
    # Only when nothing above already explains the school, so one cause isn't
    # reported twice in different words.
    if not teacher_errors and not any(i["severity"] == "error" for i in issues) and (requirements or option_wrappers):
        def batch_count(r) -> int:
            return batches(r)
        try:
            staffing = _solver._diagnose_teacher_assignment(
                requirements, option_wrappers, cands | {o.id: _block_cands(o, blocks, teachers, t_by_id, cg_by_id)
                                                        for o in option_wrappers},
                t_by_id, lessons, subjects, cg_by_id, batch_count, frozen_busy=frozen_busy,
            )
        except Exception:  # noqa: BLE001 - a check that can't run says nothing
            staffing = []
        for message in staffing:
            issues.append(_issue("error", "staffing", message,
                                 {"type": "teachers", "id": None, "label": "Open teachers"}))

    # ------------------------------------------------------------------
    # 4. A rule that needs lessons back to back the day can't fit.
    # ------------------------------------------------------------------
    by_day: dict[int, list[Period]] = {}
    for p in all_periods:
        by_day.setdefault(p.day_of_week, []).append(p)

    def longest_run(cg_id: int) -> int:
        off = off_by_cg.get(cg_id, set())
        best = 0
        for ps in by_day.values():
            run = 0
            for p in sorted(ps, key=lambda p: p.order):
                if p.is_break or p.id in off:
                    run = 0
                else:
                    run += 1
                    best = max(best, run)
        return best

    labels = _solver._class_group_labels(class_groups)
    subject_ids_by_name = {s.name: s.id for s in subjects.values()}
    for c in db.query(Constraint).filter(Constraint.school_id == school_id, Constraint.type == "ir").all():
        try:
            rule = rule_from_dict(c.parameters or {})
        except IRError:
            continue
        form = rule.form
        if not isinstance(form, Run) or not form.block_size or rule.strength != "required":
            continue
        sel = form.selector
        if not sel.subjects or sel.days or sel.period_orders or sel.period_positions or sel.teachers or sel.not_subjects:
            continue  # only the plain "X needs k together" shape is checked
        k = form.block_size
        sids = {subject_ids_by_name[n] for n in sel.subjects if n in subject_ids_by_name}
        scope = None
        if sel.class_groups:
            scope = {i for n in sel.class_groups for i in labels.get(n, [])}
        fix = {"type": "rule", "id": c.id, "label": "Open the rule"}
        rule_name = c.description or f"{', '.join(sel.subjects)} in blocks of {k}"
        problems = []
        for r in requirements:
            if r.subject_id not in sids or (scope is not None and r.class_group_id not in scope):
                continue
            cg = cg_by_id.get(r.class_group_id)
            if longest_run(r.class_group_id) < k:
                problems.append(f"{_label(cg)} never has {k} lesson periods in a row (breaks split its day)")
            elif form.blocks is None and r.periods_per_week < k:
                # The rule forbids a lesson on its own (a longer run is fine),
                # so only fewer than k a week is certain to break it.
                problems.append(f"{_label(cg)} has only {_plural(r.periods_per_week, 'period')} of "
                                f"{sname(r.subject_id)} a week, too few for a block of {k}")
            elif form.blocks is not None and form.blocks_relation in ("==", ">=") and r.periods_per_week < form.blocks * k:
                problems.append(f"{_label(cg)} has only {r.periods_per_week} {sname(r.subject_id)} periods a week, "
                                f"fewer than {form.blocks} block{'s' if form.blocks != 1 else ''} of {k}")
        if problems:
            more = f", and {len(problems) - 3} more" if len(problems) > 3 else ""
            issues.append(_issue(
                "error", "double_periods",
                f"“{rule_name}” can't be met: {'; '.join(problems[:3])}{more}. Change the rule, "
                f"the periods a week, or the school day.",
                fix,
            ))

    # ------------------------------------------------------------------
    # 5. Rooms of a type: not enough at once. Rooms are matched after the
    #    timetable is made and never stop it, so these are warnings.
    # ------------------------------------------------------------------
    rooms_fix = {"type": "rooms", "id": None, "label": "Open rooms"}
    rooms_by_type: dict[str, list[Room]] = {}
    for room in rooms:
        if room.room_type:
            rooms_by_type.setdefault(room.room_type, []).append(room)
    need_by_type: dict[str, list] = {}
    for r in requirements:
        s = subjects.get(r.subject_id)
        if s and s.required_room_type:
            need_by_type.setdefault(s.required_room_type, []).append(r)
    for rtype, reqs in need_by_type.items():
        have = rooms_by_type.get(rtype, [])
        subject_names = sorted({sname(r.subject_id) for r in reqs})
        if not have:
            issues.append(_issue(
                "warning", "no_room_type",
                f"{', '.join(subject_names)} need{'s' if len(subject_names) == 1 else ''} a “{rtype}” "
                f"room, but the school has none, so those lessons won't get a room. Add one, or change the "
                f"subject's room type.", rooms_fix,
            ))
            continue
        at_once = max(batches(r) for r in reqs)
        if at_once > len(have):
            r = next(r for r in reqs if batches(r) == at_once)
            issues.append(_issue(
                "warning", "rooms_at_once",
                f"{sname(r.subject_id)} in {_label(cg_by_id.get(r.class_group_id))} runs {at_once} batches at once, "
                f"each needing a “{rtype}” room, but there {'is' if len(have) == 1 else 'are'} only "
                f"{len(have)}. Some batches won't get a room.", rooms_fix,
            ))
        weekly = sum(r.periods_per_week * batches(r) for r in reqs)
        slots = len(have) * len(lessons)
        if weekly > slots:
            issues.append(_issue(
                "warning", "rooms_short",
                f"Lessons needing a “{rtype}” room add up to {weekly} a week, but "
                f"{_plural(len(have), 'room')} × {len(lessons)} periods is only {slots}. "
                f"At least {weekly - slots} won't get one.", rooms_fix,
            ))
        sized = [room for room in have if room.capacity]
        if sized and len(sized) == len(have):
            biggest = max(room.capacity for room in sized)
            too_big = sorted({_label(cg_by_id.get(r.class_group_id)) for r in reqs
                              if batches(r) == 1 and (cg_by_id.get(r.class_group_id).student_count or 0) > biggest})
            if too_big:
                issues.append(_issue(
                    "warning", "rooms_too_small",
                    f"Every “{rtype}” room seats at most {biggest}, fewer than "
                    f"{', '.join(too_big[:4])}{' and others' if len(too_big) > 4 else ''} has, so "
                    f"{'its' if len(too_big) == 1 else 'their'} lessons won't get one.", rooms_fix,
                ))
    return issues


def _block_cands(o, blocks, teachers, t_by_id, cg_by_id) -> list[int]:
    block = next(b for b in blocks if b.id == o.block_id)
    option = next(x for x in block.options if x.id == -o.id)
    members = [sid for sid in block.section_ids if sid in cg_by_id]
    allowed = None
    for sid in [s for s in option.group_section_ids if s in members]:
        ids = _solver._candidate_teacher_ids(
            SimpleNamespace(class_group_id=sid, subject_id=option.subject_id,
                            preferred_teacher_id=option.preferred_teacher_id, allowed_teacher_ids=None),
            teachers, t_by_id, cg_by_id)
        allowed = ids if allowed is None else [t for t in allowed if t in set(ids)]
    return allowed or []

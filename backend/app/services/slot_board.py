"""
The timetable as a board to try moves on, in memory, without saving.

move-slot (app/routers/timetables.py) is the one place a slot actually moves.
This answers "what if" questions about it, fast enough to ask dozens of times
in one request:

  judge(section, from, to)   would move-slot accept this, and if not, why -
                             and which lesson is in the way
  suggest(section, from, to) a blocked move made possible by moving the lesson
                             in the way first (and, if that is blocked too,
                             the one in its way): chains of up to three moves

The checks mirror move-slot's one for one - frozen sections and subjects,
lesson-free slots, locks, a teacher or room in two places - so a move this
calls allowed is one move-slot accepts. Rules can't refuse a move (it's kept
and flagged), so they only turn an answer amber.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.school import ClassGroup, Period, Room, School, Subject, Teacher, Timetable, TimetableEntry
from app.services.constraint_ir_checker import Placement, check_rules
from app.services.subject_freezing import frozen_lessons_index
from app.services.timetable_structure import grade_off_period_ids, zero_period_ids_for

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# How far the search looks: lessons in the way, and periods to try moving
# each to. Enough for the two- and three-move fixes people make by hand,
# small enough to answer while they wait.
MAX_CHAIN = 3
MAX_SUGGESTIONS = 3


@dataclass
class Verdict:
    status: str                     # ok | warn | blocked
    reason: str | None = None
    # The lesson in the way, as (section, period): moving it elsewhere first
    # is what a suggested fix tries. None when nothing can be moved aside -
    # a lock, a frozen section, a period with no lessons.
    blocker: tuple[int, int] | None = None


@dataclass
class Step:
    class_group_id: int
    from_period_id: int
    to_period_id: int
    text: str = ""


@dataclass
class Suggestion:
    steps: list[Step]
    status: str                     # ok | warn: how the board ends up
    summary: str
    warnings: list[str] = field(default_factory=list)


class Board:
    def __init__(self, db: Session, timetable: Timetable, rules=None):
        """`rules` is (rules, index) from the router's _rule_setup, or None."""
        self.db = db
        school_id = timetable.school_id
        self.periods = {p.id: p for p in db.query(Period).filter(Period.school_id == school_id).all()}
        self.cgs = {c.id: c for c in db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()}
        self.subjects = {s.id: s for s in db.query(Subject).filter(Subject.school_id == school_id).all()}
        self.teachers = {t.id: t for t in db.query(Teacher).filter(Teacher.school_id == school_id).all()}
        self.rooms = {r.id: r for r in db.query(Room).filter(Room.school_id == school_id).all()}
        self.entries: list[TimetableEntry] = list(timetable.entries)
        self.pid = {e.id: e.period_id for e in self.entries}
        self._index()
        self.by_subject, self.by_block = frozen_lessons_index(db, school_id)
        school = db.get(School, school_id)
        self.off_by_grade = grade_off_period_ids(list(self.periods.values()),
                                                 school.grade_day_limits if school else None)
        self._zero: dict = {}
        self.school_id = school_id
        self.rules = rules
        self.base = self._broken() if rules else set()
        # "P3" - the lesson number in its day, what the grid calls it.
        self.number: dict[int, int] = {}
        by_day: dict[int, list[Period]] = {}
        for p in self.periods.values():
            if not p.is_break:
                by_day.setdefault(p.day_of_week, []).append(p)
        for ps in by_day.values():
            for n, p in enumerate(sorted(ps, key=lambda p: p.order), start=1):
                self.number[p.id] = n

    # -- the board -------------------------------------------------------

    def _index(self) -> None:
        self.at: dict[tuple[int, int], list[TimetableEntry]] = {}
        self.by_period: dict[int, list[TimetableEntry]] = {}
        for e in self.entries:
            pid = self.pid[e.id]
            self.at.setdefault((e.class_group_id, pid), []).append(e)
            self.by_period.setdefault(pid, []).append(e)

    def snapshot(self) -> dict:
        return dict(self.pid)

    def restore(self, snap: dict) -> None:
        self.pid = dict(snap)
        self._index()

    def apply(self, section: int, src: int, dst: int) -> None:
        sections = self.together(section, src, dst)
        source = [e for sid in sections for e in self.at.get((sid, src), [])]
        target = [e for sid in sections for e in self.at.get((sid, dst), [])]
        for e in source:
            self.pid[e.id] = dst
        for e in target:
            self.pid[e.id] = src
        self._index()

    # -- names -----------------------------------------------------------

    def label(self, cid) -> str:
        cg = self.cgs.get(cid)
        return (f"{cg.grade} {cg.name}" if cg.grade else cg.name) if cg else "another section"

    def subj(self, e) -> str:
        s = self.subjects.get(e.subject_id)
        return s.name if s else "a lesson"

    def when(self, pid) -> str:
        p = self.periods.get(pid)
        if p is None:
            return "that period"
        name = p.label or f"P{self.number.get(pid, p.order + 1)}"
        return f"{_DAYS[p.day_of_week] if 0 <= p.day_of_week < 7 else ''} {name}".strip()

    def slot_name(self, section: int, pid: int) -> str:
        """"11 A's Physics", "11 A's Block 1" - what's in a slot."""
        es = self.at.get((section, pid), [])
        if not es:
            return f"{self.label(section)}'s free period"
        blocks = {e.elective_block_id for e in es if e.elective_block_id}
        if blocks:
            from app.models.school import ElectiveBlock
            b = self.db.get(ElectiveBlock, next(iter(blocks)))
            what = b.name if b else "elective block"
        else:
            what = self.subj(es[0])
        return f"{self.label(section)}'s {what}"

    # -- the checks ------------------------------------------------------

    def _no_lesson(self, pid: int, cid: int) -> str | None:
        cg = self.cgs.get(cid)
        grade = cg.grade if cg else None
        if grade not in self._zero:
            self._zero[grade] = zero_period_ids_for(self.db, self.school_id, grade)
        if pid in self._zero[grade]:
            return f"That's {grade or self.label(cid)}'s zero period"
        if grade and pid in self.off_by_grade.get(grade, set()):
            return f"{grade}'s day is over by then"
        return None

    def _frozen_subject(self, e) -> str | None:
        return self.by_subject.get((e.class_group_id, e.subject_id)) or (
            self.by_block.get((e.class_group_id, e.elective_block_id)) if e.elective_block_id else None
        )

    def together(self, section: int, src: int, dst: int) -> list[int]:
        sections = [section]
        i = 0
        while i < len(sections):
            sid = sections[i]
            i += 1
            for pid in (src, dst):
                blocks = {e.elective_block_id for e in self.at.get((sid, pid), []) if e.elective_block_id is not None}
                if not blocks:
                    continue
                for o in self.by_period.get(pid, []):
                    if o.elective_block_id in blocks and o.class_group_id not in sections:
                        sections.append(o.class_group_id)
        return sections

    def judge(self, section: int, src: int, dst: int, with_rules: bool = True) -> Verdict:
        p = self.periods.get(dst)
        if p is None or p.is_break or dst == src:
            return Verdict("blocked", "Nothing can be scheduled there")
        sections = self.together(section, src, dst)
        source = [e for sid in sections for e in self.at.get((sid, src), [])]
        target = [e for sid in sections for e in self.at.get((sid, dst), [])]
        if not source:
            return Verdict("blocked", "There's nothing in that slot to move")
        for sid in sections:
            cg = self.cgs.get(sid)
            if cg is not None and cg.frozen:
                return Verdict("blocked", f"{self.label(sid)} is frozen"
                               + ("" if sid == section else " and shares this lesson"))
        for e in source + target:
            name = self._frozen_subject(e)
            if name:
                return Verdict("blocked", f"{name} is frozen")
        for sid in sections:
            if any(e.class_group_id == sid for e in source):
                why = self._no_lesson(dst, sid)
                if why:
                    return Verdict("blocked", why + ("" if sid == section else f" for {self.label(sid)}"))
            if any(e.class_group_id == sid for e in target):
                why = self._no_lesson(src, sid)
                if why:
                    return Verdict("blocked", f"What's there can't come back: {why[0].lower() + why[1:]}")
        if any(e.locked for e in source):
            return Verdict("blocked", "This slot is locked. Click it to unlock it first")
        locked = [e for e in target if e.locked]
        if locked:
            e = locked[0]
            where = "" if e.class_group_id == section else f" in {self.label(e.class_group_id)}"
            return Verdict("blocked", f"{self.subj(e)}{where} is locked there")
        moving = {e.id for e in source + target}
        for movers, there in ((source, dst), (target, src)):
            others = [o for o in self.by_period.get(there, []) if o.id not in moving]
            for e in movers:
                for o in others:
                    if e.teacher_id is not None and o.teacher_id == e.teacher_id:
                        t = self.teachers.get(e.teacher_id)
                        tname = t.name if t else "The teacher"
                        if there == dst:
                            reason = f"{tname} teaches {self.label(o.class_group_id)} then"
                        else:
                            reason = (f"{self.subj(e)} would move back to {self.when(src)}, where "
                                      f"{tname} teaches {self.label(o.class_group_id)}")
                        return Verdict("blocked", reason, blocker=(o.class_group_id, there))
                    if e.room_id is not None and o.room_id == e.room_id:
                        r = self.rooms.get(e.room_id)
                        return Verdict("blocked", f"{r.name if r else 'The room'} is in use by "
                                       f"{self.label(o.class_group_id)} then", blocker=(o.class_group_id, there))
        warnings = []
        for movers, there in ((source, dst), (target, src)):
            for e in movers:
                t = self.teachers.get(e.teacher_id)
                if t and there in set(t.unavailable_period_ids or []):
                    warnings.append(f"{t.name} is marked unavailable then")
        if with_rules and self.rules:
            snap = self.snapshot()
            self.apply(section, src, dst)
            warnings.extend(self._new_rule_breaks())
            self.restore(snap)
        if warnings:
            return Verdict("warn", "; ".join(dict.fromkeys(warnings)))
        return Verdict("ok")

    def _broken(self) -> set:
        rules, index = self.rules
        placements = []
        for e in self.entries:
            pid = self.pid[e.id]
            p = self.periods[pid]
            placements.append(Placement(
                entry_id=e.id, class_group_id=e.class_group_id, subject_id=e.subject_id,
                teacher_id=e.teacher_id, period_id=pid, day_of_week=p.day_of_week, order=p.order,
                occupies_teacher=e.teacher_id is not None,
            ))
        self._last = check_rules(placements, rules, index)
        return {(v.constraint_id, v.detail) for v in self._last if v.strength == "required"}

    def _new_rule_breaks(self) -> list[str]:
        now = self._broken()
        names = {v.description for v in self._last
                 if v.strength == "required" and (v.constraint_id, v.detail) in now - self.base}
        return [f"Breaks “{n}”" for n in sorted(names)]

    # -- fixing a blocked move ------------------------------------------

    def suggest(self, section: int, src: int, dst: int) -> tuple[Verdict, list[Suggestion]]:
        """The verdict on the move as asked, and - if it's blocked by a
        lesson that could move - ways to make room for it: move that lesson
        somewhere else first (and, if that's blocked too, the lesson in ITS
        way; or, if the move is still blocked by a second lesson, that one
        as well), then make the move. Best first: fewest moves, then no rule
        broken. Nothing on the board changes."""
        first = self.judge(section, src, dst)
        if first.status != "blocked" or first.blocker is None:
            return first, []
        lessons = [p.id for p in self.periods.values() if not p.is_break]
        chains: list[list[tuple[int, int, int]]] = []

        def free(sec, frm, to) -> bool:
            return self.judge(sec, frm, to, with_rules=False).status != "blocked"

        def main_ok() -> Verdict:
            return self.judge(section, src, dst, with_rules=False)

        b = first.blocker
        start = self.snapshot()
        for alt in lessons:
            if alt == b[1] or len(chains) >= 20:
                continue
            v = self.judge(b[0], b[1], alt, with_rules=False)
            if v.status != "blocked":
                self.apply(b[0], b[1], alt)
                after = main_ok()
                if after.status != "blocked":
                    chains.append([(b[0], b[1], alt)])
                elif after.blocker and after.blocker != b and MAX_CHAIN >= 3:
                    # Room made, but a second lesson is in the way: move it too.
                    c = after.blocker
                    mid = self.snapshot()
                    for alt2 in lessons:
                        if alt2 == c[1] or not free(c[0], c[1], alt2):
                            continue
                        self.apply(c[0], c[1], alt2)
                        if main_ok().status != "blocked":
                            chains.append([(b[0], b[1], alt), (c[0], c[1], alt2)])
                        self.restore(mid)
                self.restore(start)
            elif v.blocker and v.blocker != b and MAX_CHAIN >= 3:
                # The lesson in the way can't go there either: move what's in
                # ITS way first.
                c = v.blocker
                for alt2 in lessons:
                    if alt2 == c[1] or not free(c[0], c[1], alt2):
                        continue
                    self.apply(c[0], c[1], alt2)
                    if free(b[0], b[1], alt):
                        self.apply(b[0], b[1], alt)
                        if main_ok().status != "blocked":
                            chains.append([(c[0], c[1], alt2), (b[0], b[1], alt)])
                    self.restore(start)

        ranked = []
        for chain in chains:
            done = self._replay(chain, section, src, dst)
            if done is not None:
                ranked.append(done)
        ranked.sort(key=lambda d: (len(d[0]), len(d[1])))
        out, seen = [], set()
        for steps, warnings in ranked:
            key = tuple((s.class_group_id, s.from_period_id, s.to_period_id) for s in steps)
            if key in seen:
                continue
            seen.add(key)
            texts = [s.text for s in steps[:-1]]
            out.append(Suggestion(
                steps=steps, status="warn" if warnings else "ok", warnings=warnings,
                summary=f"{first.reason}. {', then '.join(texts)} as well?",
            ))
            if len(out) >= MAX_SUGGESTIONS:
                break
        return first, out

    def _replay(self, chain, section, src, dst):
        """Play the chain and the move from the real board: each step named
        as it stands when it's made, and the rules the end result breaks.
        None if any step turns out to be blocked."""
        snap = self.snapshot()
        steps = []
        try:
            for sec, frm, to in [*chain, (section, src, dst)]:
                if self.judge(sec, frm, to, with_rules=False).status == "blocked":
                    return None
                steps.append(Step(sec, frm, to, f"Move {self.slot_name(sec, frm)} from "
                                                f"{self.when(frm)} to {self.when(to)}"))
                self.apply(sec, frm, to)
            warnings = []
            for e in self.entries:
                t = self.teachers.get(e.teacher_id)
                if t and self.pid[e.id] != snap[e.id] and self.pid[e.id] in set(t.unavailable_period_ids or []):
                    warnings.append(f"{t.name} is marked unavailable then")
            if self.rules:
                warnings.extend(self._new_rule_breaks())
            return steps, list(dict.fromkeys(warnings))
        finally:
            self.restore(snap)

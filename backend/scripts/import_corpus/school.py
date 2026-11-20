"""
A made-up school whose every fact is known: the truth the import test cases
are rendered from, and what the scorer checks an importer's answer against.

Built to look like the schools in school-imports/public/samples.json: Indian
grade names, PRT/TGT/PGT teachers, a 5- or 6-day week of 6-9 periods with a
break and lunch, class teacher periods, language groups that split a grade
across several teachers at once (Keren's 2nd/3rd language), elective blocks in
Grades 11-12 ("Maths/Biology"), doubles for labs and games, and a weekly
timetable with no teacher in two places at once.

Everything is driven by one random.Random, so a seed always gives the same
school.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

FIRST = [
    "Anitha", "Kavitha", "Lakshmi", "Priya", "Deepa", "Sangeetha", "Meena", "Revathi", "Suganya", "Bhuvana",
    "Shalini", "Divya", "Nirmala", "Sarala", "Uma", "Vasanthi", "Geetha", "Jayanthi", "Malathi", "Radha",
    "Rekha", "Sumathi", "Vidya", "Usha", "Padma", "Hema", "Indira", "Kala", "Latha", "Mythili",
    "Ramesh", "Suresh", "Karthik", "Arun", "Vijay", "Prakash", "Senthil", "Murali", "Ganesh", "Rajesh",
    "Joseph", "Thomas", "Mary", "Sarah", "Beula", "Jenita", "Ruth", "Grace", "Abirami", "Lavanya",
    "Sabina", "Heera", "Farzana", "Ayesha", "Imran", "Salma", "Neha", "Pooja", "Rohit", "Amit",
]
LAST = [
    "Rao", "Iyer", "Nair", "Menon", "Pillai", "Krishnan", "Raman", "Subramaniam", "Natarajan", "Srinivasan",
    "Kumar", "Devi", "Selvam", "Rajan", "Joseph", "Thomas", "George", "Fernandes", "Khan", "Begum",
    "Sharma", "Gupta", "Singh", "Verma", "Das", "Bose", "Reddy", "Naidu", "Patel", "Shah",
]

# Subjects by stage, with periods a week and the short forms schools write them as.
SUBJECTS = {
    "English": ["ENG", "Eng", "English Lang", "E"],
    "Mathematics": ["MAT", "Maths", "Math", "MATHS", "M"],
    "Science": ["SCI", "Sci", "Gen. Science", "SC"],
    "Social Science": ["SST", "S. Sc.", "Soc. Sc.", "SOC", "SS"],
    "Hindi": ["HIN", "Hin", "HINDI"],
    "Tamil": ["TAM", "Tam", "TAMIL"],
    "Sanskrit": ["SKT", "Sans", "SANS"],
    "Computer Science": ["COMP", "CS", "Comp. Sc.", "COM"],
    "Physical Education": ["PE", "PET", "P.E.", "GAMES", "Games"],
    "Art": ["ART", "Art & Craft", "Drawing", "FINE ARTS"],
    "Music": ["MUS", "Music & Dance"],
    "Library": ["LIB", "Lib", "Library Period"],
    "EVS": ["EVS", "Env. Studies", "E.V.S."],
    "General Knowledge": ["GK", "G.K."],
    "Value Education": ["VE", "Moral Science", "Value Ed."],
    "SUPW": ["SUPW", "Work Education", "WE"],
    "Class Teacher Period": ["C.T", "CT", "Class Teacher", "CTP"],
    "Physics": ["PHY", "Phy", "PHYSICS"],
    "Chemistry": ["CHEM", "Chem", "CHE"],
    "Biology": ["BIO", "Bio"],
    "Accountancy": ["ACC", "Accounts", "ACCT"],
    "Business Studies": ["BST", "B. St.", "B ST"],
    "Economics": ["ECO", "Eco", "Econ"],
    "Robotics": ["ROBO", "Robo", "Robotics Lab"],
    "Second Language": ["2LN", "II Lang", "2nd Lang", "SL"],
    "Third Language": ["3LN", "III Lang", "3rd Lang", "TL"],
}

PLANS = {
    # stage -> [(subject, periods a week)]
    "primary": [("English", 7), ("Mathematics", 7), ("EVS", 5), ("Second Language", 5), ("Third Language", 3),
                ("Computer Science", 2), ("Physical Education", 2), ("Art", 2), ("Music", 1), ("Library", 1),
                ("General Knowledge", 1), ("Value Education", 1), ("Class Teacher Period", 5)],
    "middle": [("English", 6), ("Mathematics", 7), ("Science", 6), ("Social Science", 6), ("Second Language", 5),
               ("Third Language", 3), ("Computer Science", 2), ("Physical Education", 2), ("Art", 1),
               ("Library", 1), ("SUPW", 1), ("Robotics", 1), ("Class Teacher Period", 4)],
    "secondary": [("English", 7), ("Mathematics", 8), ("Science", 8), ("Social Science", 7), ("Second Language", 6),
                  ("Computer Science", 3), ("Physical Education", 2), ("Library", 1), ("Class Teacher Period", 3)],
    "senior": [("English", 6), ("Physics", 7), ("Chemistry", 7), ("Physical Education", 2), ("Library", 1),
               ("Class Teacher Period", 2)],
}
SENIOR_ELECTIVE = ["Mathematics", "Biology"]          # one block: students take one
SENIOR_OPTION = ["Computer Science", "Economics", "Physical Education"]  # second block
LANGUAGES = {"Second Language": ["Tamil", "Hindi"], "Third Language": ["Hindi", "Sanskrit"]}


def stage_of(grade: int) -> str:
    return "primary" if grade <= 5 else "middle" if grade <= 8 else "secondary" if grade <= 10 else "senior"


@dataclass
class Teacher:
    name: str           # "Kavitha Rao"
    title: str          # "Mrs."
    post: str           # "PRT" / "TGT" / "PGT"
    subjects: list[str]
    grades: list[int] = field(default_factory=list)
    class_teacher_of: str | None = None
    unavailable: list[tuple[int, int]] = field(default_factory=list)  # (day, period)


@dataclass
class Lesson:
    section: str        # "7A"
    day: int            # 0 = Monday
    period: int         # 1-based lesson number
    subject: str
    teacher: str | None
    block: str | None = None   # "7 Second Language" for a language/elective group lesson
    group: str | None = None   # which group of the block ("Tamil", "Group 2")


@dataclass
class School:
    name: str
    days: int
    periods: int
    breaks: list[tuple[int, str]]        # (after period n, "Break"/"Lunch")
    bell: list[str]                      # "8:40-9:20" per period
    grades: list[int]
    sections: list[str]                  # "7A"
    teachers: list[Teacher]
    plan: list[dict]                     # {section, subject, periods, teacher|None, block|None}
    blocks: list[dict]                   # {name, sections, periods, groups: [{subject, label, teacher}]}
    fixed: list[dict]                    # {subject, grades, period, days}
    lessons: list[Lesson]

    def grade_of(self, section: str) -> int:
        return int(section.rstrip("ABCDEFGH"))

    def to_truth(self) -> dict:
        return {
            "school": self.name,
            "days": DAYS[: self.days],
            "periods_per_day": self.periods,
            "breaks": [{"after_period": a, "name": n} for a, n in self.breaks],
            "bell_times": self.bell,
            "sections": self.sections,
            "subjects": sorted({p["subject"] for p in self.plan} | {g["subject"] for b in self.blocks for g in b["groups"]}),
            "teachers": [
                {"name": t.name, "title": t.title, "post": t.post, "subjects": t.subjects, "grades": t.grades,
                 "class_teacher_of": t.class_teacher_of}
                for t in self.teachers
            ],
            "plan": self.plan,
            "blocks": self.blocks,
            "fixed_periods": self.fixed,
            "lessons": [l.__dict__ for l in self.lessons],
        }


class _Unplaceable(Exception):
    pass


def build(rng: random.Random, size: str = "medium") -> School:
    """A school of `size` small (~6 sections) / medium (~14) / large (~24)."""
    for _attempt in range(200):
        try:
            return _build(rng, size)
        except _Unplaceable:
            continue
    raise RuntimeError("could not place a timetable after 40 tries - loosen the profile")


def _build(rng: random.Random, size: str) -> School:
    days = rng.choice([5, 5, 6])
    periods = rng.choice([7, 8, 8, 9])
    lunch_after = periods // 2 + (0 if periods % 2 else 0)
    breaks = [(2, "Short Break"), (lunch_after, "Lunch")] if periods >= 8 else [(lunch_after, "Lunch")]
    start = rng.choice([8 * 60, 8 * 60 + 30, 8 * 60 + 40, 9 * 60])
    length = rng.choice([40, 40, 45])
    bell, t = [], start
    for p in range(1, periods + 1):
        bell.append(f"{t // 60}:{t % 60:02d}-{(t + length) // 60}:{(t + length) % 60:02d}")
        t += length
        for after, name in breaks:
            if after == p:
                t += 20 if name == "Short Break" else 30

    band = {"small": (6, 8, 1, 2), "medium": (1, 10, 1, 2), "large": (1, 12, 2, 3)}[size]
    lo, hi, smin, smax = band
    if size == "small":
        grades = list(range(lo, hi + 1))
    else:
        grades = list(range(rng.choice([1, 3, 6]), hi + 1))
    sections = []
    for g in grades:
        n = rng.randint(smin, smax)
        sections += [f"{g}{chr(65 + i)}" for i in range(n)]
    slots = days * periods

    used_names: set[str] = set()

    def new_name() -> tuple[str, str]:
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            name = f"{first} {last}" if rng.random() < 0.75 else first
            if name not in used_names:
                used_names.add(name)
                male = first in {"Ramesh", "Suresh", "Karthik", "Arun", "Vijay", "Prakash", "Senthil", "Murali",
                                 "Ganesh", "Rajesh", "Joseph", "Thomas", "Imran", "Rohit", "Amit"}
                return name, ("Mr." if male else rng.choice(["Mrs.", "Ms.", "Mrs."]))

    plan: list[dict] = []
    blocks: list[dict] = []
    # Periods each section needs; scale the stage plan to fill the week exactly.
    for sec in sections:
        g = int(sec[:-1])
        stage = stage_of(g)
        items = list(PLANS[stage])
        if stage == "senior":
            items += [("__block1", 7), ("__block2", 6)]
        total = sum(n for _, n in items)
        # fill or trim with English/Maths-ish so every slot is taught
        i = 0
        while total < slots:
            subj, n = items[i % 3]
            items[i % 3] = (subj, n + 1)
            total += 1
            i += 1
        while total > slots:
            j = max(range(len(items)), key=lambda k: items[k][1])
            items[j] = (items[j][0], items[j][1] - 1)
            total -= 1
        for subj, n in items:
            if n <= 0:
                continue
            if subj in LANGUAGES or subj.startswith("__block"):
                continue  # grade-wide blocks, below
            plan.append({"section": sec, "subject": subj, "periods": n, "teacher": None, "block": None})
        # remember block period counts per grade
        for subj, n in items:
            if subj in LANGUAGES or subj.startswith("__block"):
                key = (g, subj)
                if not any(b["_key"] == key for b in blocks):
                    blocks.append({"_key": key, "periods": n})

    # Teachers: enough per subject that nobody is over ~70% of the week.
    load: dict[str, int] = {}
    for p in plan:
        load[p["subject"]] = load.get(p["subject"], 0) + p["periods"]
    teachers: list[Teacher] = []
    by_subject: dict[str, list[Teacher]] = {}
    cap = int(slots * (0.5 if size == 'large' else 0.6))
    for subj, need in sorted(load.items()):
        if subj == "Class Teacher Period":
            continue
        count = max(1, -(-need // cap))
        for _ in range(count):
            name, title = new_name()
            post = rng.choice(["TGT", "PGT"]) if subj in {"Physics", "Chemistry", "Biology", "Accountancy",
                                                          "Economics", "Business Studies"} else rng.choice(["PRT", "TGT", "TGT"])
            t = Teacher(name, title, post, [subj])
            teachers.append(t)
            by_subject.setdefault(subj, []).append(t)

    # Language and elective blocks: one per grade, groups across all its sections.
    real_blocks = []
    for b in blocks:
        g, kind = b["_key"]
        secs = [s for s in sections if int(s[:-1]) == g]
        groups = []
        if kind in LANGUAGES:
            langs = LANGUAGES[kind]
            n_groups = max(2, len(secs))
            for i in range(n_groups):
                lang = langs[0] if i < n_groups - 1 else langs[1]
                groups.append({"subject": lang, "label": f"Group {i + 1}"})
            name = f"{kind}"
        elif kind == "__block1":
            groups = [{"subject": s, "label": None} for s in SENIOR_ELECTIVE]
            name = "Elective A"
        else:
            groups = [{"subject": s, "label": None} for s in SENIOR_OPTION]
            name = "Elective B"
        taken = set()
        for gr in groups:
            # A language teacher teaches several grades' groups; a new one only
            # when every existing one already has this grade.
            pool = [t for t in by_subject.get(gr["subject"], []) if t.name not in taken
                    and sum(1 for bb in real_blocks for x in bb["groups"] if x.get("teacher") == t.name) < 3]
            if pool and rng.random() < 0.7:
                t = rng.choice(pool)
            else:
                name_, title = new_name()
                t = Teacher(name_, title, "PGT" if g >= 11 else "TGT", [gr["subject"]])
                teachers.append(t)
                by_subject.setdefault(gr["subject"], []).append(t)
            taken.add(t.name)
            gr["teacher"] = t.name
        real_blocks.append({"name": f"Grade {g} {name}", "grade": g, "sections": secs, "periods": b["periods"],
                            "groups": groups})

    # Class teachers: one per section, from its subject teachers.
    given: dict[str, int] = {}
    for p in sorted(plan, key=lambda p: -p["periods"]):
        pool = [t for t in by_subject.get(p["subject"], []) if t.name not in
                {g["teacher"] for b in real_blocks for g in b["groups"]}] or by_subject.get(p["subject"], [])
        if p["subject"] == "Class Teacher Period" or not pool:
            continue
        pick = min(pool, key=lambda t: (given.get(t.name, 0), rng.random()))
        p["teacher"] = pick.name
        given[pick.name] = given.get(pick.name, 0) + p["periods"]
    class_teachers = {}
    for sec in sections:
        mine = [p["teacher"] for p in plan if p["section"] == sec and p["teacher"]]
        free = [m for m in mine if m not in class_teachers.values()]
        ct = rng.choice(free or mine)
        class_teachers[sec] = ct
        for t in teachers:
            if t.name == ct:
                t.class_teacher_of = sec
        for p in plan:
            if p["section"] == sec and p["subject"] == "Class Teacher Period":
                p["teacher"] = ct

    # Nobody over ~85% of the week: hand their biggest ordinary class to a new
    # colleague for that subject until it fits.
    limit = int(slots * 0.85)

    def load_of(name):
        return (sum(p["periods"] for p in plan if p["teacher"] == name)
                + sum(b["periods"] for b in real_blocks for g in b["groups"] if g["teacher"] == name))

    for t in list(teachers):
        while load_of(t.name) > limit:
            mine = [p for p in plan if p["teacher"] == t.name and p["subject"] != "Class Teacher Period"]
            if not mine:
                break
            item = max(mine, key=lambda p: p["periods"])
            name_, title = new_name()
            helper = Teacher(name_, title, t.post, list(item["subject"] for _ in [0]))
            teachers.append(helper)
            by_subject.setdefault(item["subject"], []).append(helper)
            for p in plan:  # the whole subject in that section moves
                if p is item:
                    p["teacher"] = helper.name

    # Grades each teacher teaches.
    for t in teachers:
        gs = {int(p["section"][:-1]) for p in plan if p["teacher"] == t.name}
        gs |= {b["grade"] for b in real_blocks for gr in b["groups"] if gr["teacher"] == t.name}
        t.grades = sorted(gs)
    teachers = [t for t in teachers if t.grades]

    # Fixed: class teacher period in the last period every day for primary grades,
    # first period otherwise - when the plan has one a day.
    fixed = []
    ctp_days = {p["section"]: p["periods"] for p in plan if p["subject"] == "Class Teacher Period"}
    primary = sorted({int(s[:-1]) for s, n in ctp_days.items() if n >= days and int(s[:-1]) <= 5})
    if primary:
        fixed.append({"subject": "Class Teacher Period", "grades": primary, "period": periods, "days": None})

    lessons = _place_cp(rng, days, periods, sections, plan, real_blocks, fixed)
    return School(
        name=f"{rng.choice(['St.', 'Sri', 'Holy', 'Little', 'New', 'Green Valley'])} "
             f"{rng.choice(['Mary', 'Vidya', 'Cross', 'Flower', 'Horizon', 'Park'])} "
             f"{rng.choice(['School', 'Public School', 'Matric Hr. Sec. School', 'Senior Secondary School'])}",
        days=days, periods=periods, breaks=breaks, bell=bell, grades=grades, sections=sections,
        teachers=teachers, plan=plan, blocks=real_blocks, fixed=fixed, lessons=lessons,
    )


def _place(rng, days, periods, sections, plan, blocks, fixed) -> list[Lesson]:
    """A clash-free week, greedily: fixed lessons, then blocks (all their
    sections at once), then doubles, then the rest - most constrained first."""
    free_sec = {s: {(d, p) for d in range(days) for p in range(1, periods + 1)} for s in sections}
    busy: dict[str, set] = {}
    out: list[Lesson] = []

    def teacher_free(name, slot):
        return name is None or slot not in busy.get(name, set())

    def take(name, slot):
        if name:
            busy.setdefault(name, set()).add(slot)

    for f in fixed:
        for p in plan:
            g = int(p["section"][:-1])
            if p["subject"] == f["subject"] and g in f["grades"]:
                for d in range(days)[: p["periods"]]:
                    slot = (d, f["period"])
                    if slot not in free_sec[p["section"]] or not teacher_free(p["teacher"], slot):
                        raise _Unplaceable()
                    free_sec[p["section"]].discard(slot)
                    take(p["teacher"], slot)
                    out.append(Lesson(p["section"], d, f["period"], p["subject"], p["teacher"]))
                p["periods"] = p["periods"]  # all placed
                p["_done"] = True

    for b in sorted(blocks, key=lambda b: -b["periods"]):
        names = [g["teacher"] for g in b["groups"]]
        candidates = [(d, p) for d in range(days) for p in range(1, periods + 1)]
        rng.shuffle(candidates)
        placed, used_days = 0, {}
        for slot in candidates:
            if placed == b["periods"]:
                break
            if used_days.get(slot[0], 0) >= (2 if b["periods"] > days else 1):
                continue
            if all(slot in free_sec[s] for s in b["sections"]) and all(teacher_free(n, slot) for n in names):
                for s in b["sections"]:
                    free_sec[s].discard(slot)
                for n in names:
                    take(n, slot)
                for gr in b["groups"]:
                    for s in b["sections"]:
                        out.append(Lesson(s, slot[0], slot[1], gr["subject"], gr["teacher"], block=b["name"],
                                          group=gr["label"] or gr["subject"]))
                placed += 1
                used_days[slot[0]] = used_days.get(slot[0], 0) + 1
        if placed < b["periods"]:
            raise _Unplaceable()

    todo = [p for p in plan if not p.get("_done")]
    rng.shuffle(todo)
    todo.sort(key=lambda p: -p["periods"])
    for p in todo:
        sec, teacher = p["section"], p["teacher"]
        need = p["periods"]
        per_day = {}
        double = p["subject"] in {"Physics", "Chemistry", "Computer Science", "Robotics"} and need >= 4
        if double:
            # one double period in the week
            pairs = [(d, q) for d in range(days) for q in range(1, periods)]
            rng.shuffle(pairs)
            for d, q in pairs:
                a, b2 = (d, q), (d, q + 1)
                if a in free_sec[sec] and b2 in free_sec[sec] and teacher_free(teacher, a) and teacher_free(teacher, b2):
                    for s in (a, b2):
                        free_sec[sec].discard(s)
                        take(teacher, s)
                        out.append(Lesson(sec, s[0], s[1], p["subject"], teacher))
                    per_day[d] = 2
                    need -= 2
                    break
        slots = sorted(free_sec[sec], key=lambda s: (rng.random()))
        # spread: prefer days with fewest of this subject
        while need > 0:
            slots.sort(key=lambda s: (per_day.get(s[0], 0), rng.random()))
            for s in slots:
                if s in free_sec[sec] and teacher_free(teacher, s):
                    free_sec[sec].discard(s)
                    take(teacher, s)
                    out.append(Lesson(sec, s[0], s[1], p["subject"], teacher))
                    per_day[s[0]] = per_day.get(s[0], 0) + 1
                    need -= 1
                    break
            else:
                raise _Unplaceable()
    for p in plan:
        p.pop("_done", None)
    return sorted(out, key=lambda l: (l.section, l.day, l.period, l.group or ""))


def _place_cp(rng, days, periods, sections, plan, blocks, fixed) -> list[Lesson]:
    """The same week as _place, found by CP-SAT so big schools always get one:
    every section's every period taught once, no teacher in two places, blocks
    meeting in all their sections at once, at most two of a subject a day, and
    fixed lessons where they're fixed. Random weights vary the answer by seed."""
    from ortools.sat.python import cp_model

    m = cp_model.CpModel()
    slots = [(d, p) for d in range(days) for p in range(1, periods + 1)]
    occupy: dict = {(s, sl): [] for s in sections for sl in slots}
    teach: dict = {}
    x = {}
    obj = []
    for i, it in enumerate(plan):
        vs = []
        for sl in slots:
            v = m.NewBoolVar(f"x{i}_{sl[0]}_{sl[1]}")
            x[i, sl] = v
            vs.append(v)
            occupy[it["section"], sl].append(v)
            if it["teacher"]:
                teach.setdefault((it["teacher"], sl), []).append(v)
            obj.append(rng.randint(0, 9) * v)
        m.Add(sum(vs) == it["periods"])
        for d in range(days):
            m.Add(sum(x[i, (d, p)] for p in range(1, periods + 1)) <= 2)
        for f in fixed:
            g = int(it["section"][:-1])
            if it["subject"] == f["subject"] and g in f["grades"]:
                for sl in slots:
                    if sl[1] != f["period"]:
                        m.Add(x[i, sl] == 0)
    y = {}
    for j, b in enumerate(blocks):
        vs = []
        for sl in slots:
            v = m.NewBoolVar(f"y{j}_{sl[0]}_{sl[1]}")
            y[j, sl] = v
            vs.append(v)
            for s in b["sections"]:
                occupy[s, sl].append(v)
            for g in b["groups"]:
                teach.setdefault((g["teacher"], sl), []).append(v)
            obj.append(rng.randint(0, 9) * v)
        m.Add(sum(vs) == b["periods"])
        for d in range(days):
            m.Add(sum(y[j, (d, p)] for p in range(1, periods + 1)) <= 2)
    for key, vs in occupy.items():
        m.Add(sum(vs) == 1)
    for key, vs in teach.items():
        if len(vs) > 1:
            m.Add(sum(vs) <= 1)
    m.Maximize(sum(obj))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 3
    solver.parameters.random_seed = rng.randint(0, 10_000)
    solver.parameters.num_workers = 4
    if solver.Solve(m) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise _Unplaceable()
    out = []
    for (i, sl), v in x.items():
        if solver.Value(v):
            it = plan[i]
            out.append(Lesson(it["section"], sl[0], sl[1], it["subject"], it["teacher"]))
    for (j, sl), v in y.items():
        if solver.Value(v):
            b = blocks[j]
            for g in b["groups"]:
                for s in b["sections"]:
                    out.append(Lesson(s, sl[0], sl[1], g["subject"], g["teacher"], block=b["name"],
                                      group=g["label"] or g["subject"]))
    return sorted(out, key=lambda l: (l.section, l.day, l.period, l.group or ""))

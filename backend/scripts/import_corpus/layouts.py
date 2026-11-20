"""
The shapes schools put a timetable, a subject list, a staff list or their
rules in - each modelled on a real document in
school-imports/public/samples.json (named in the docstrings).

Every layout returns (sheets, written): the Sheets to render, and how this
file wrote each truth value - {"subjects": {"Social Science": ["S. Sc."]},
"teachers": {...}, "sections": {...}} - so the scorer can judge a reading
against what was actually on the page.
"""
from __future__ import annotations

import random
from collections import defaultdict

import mess
from render import Sheet
from school import DAYS, School

ROMAN = mess.ROMAN
SHORT_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
TINY_DAYS = ["Mon", "Tues", "Wed", "Thurs", "Frid", "Sat"]


class Written:
    """What this file wrote for each truth value."""

    def __init__(self):
        self.subjects: dict[str, set] = defaultdict(set)
        self.teachers: dict[str, set] = defaultdict(set)
        self.sections: dict[str, set] = defaultdict(set)

    def subject(self, truth, shown):
        self.subjects[truth].add(shown)
        return shown

    def teacher(self, truth, shown):
        self.teachers[truth].add(shown)
        return shown

    def section(self, truth, shown):
        self.sections[truth].add(shown)
        return shown

    def to_dict(self):
        return {k: {t: sorted(v) for t, v in getattr(self, k).items()} for k in ("subjects", "teachers", "sections")}


def _day_name(i: int, style: str) -> str:
    return {"full": DAYS, "short": SHORT_DAYS, "tiny": TINY_DAYS, "caps": [d.upper() for d in DAYS]}[style][i]


def _period_head(p: int, style: str) -> str:
    return {"num": str(p), "roman": ROMAN[p], "period_roman": f"PERIOD {ROMAN[p]}", "p": f"P{p}",
            "ordinal": f"{p}{'st' if p == 1 else 'nd' if p == 2 else 'rd' if p == 3 else 'th'}"}[style]


def _by_slot(school: School) -> dict:
    out = defaultdict(list)
    for l in school.lessons:
        out[(l.section, l.day, l.period)].append(l)
    return out


def _teacher_obj(school, name):
    return next(t for t in school.teachers if t.name == name)


def _cell(rng, school, w, lessons, opts) -> str:
    """One timetable cell: a lesson's subject, maybe with its teacher, or a
    block written as its short name, its options or a legend code."""
    if not lessons:
        return ""
    first = lessons[0]
    if first.block:
        how = opts["block_style"]
        if how == "short":
            kind = "Second Language" if "Second" in first.block else "Third Language" if "Third" in first.block else None
            if kind:
                return w.subject(kind, mess.subject(rng, kind, "short"))
            return first.block.split(" ", 2)[-1]
        if how == "options":
            subs = sorted({l.subject for l in lessons})
            return "/".join(w.subject(s, mess.subject(rng, s, opts["subject_style"])) for s in subs)
        if how == "teacher":  # Keren: 2LN-BEAUL - the section's own group teacher
            mine = [l for l in lessons]
            t = mine[0].teacher
            kind = "Second Language" if "Second" in first.block else "Third Language" if "Third" in first.block else first.subject
            return f"{w.subject(kind, mess.subject(rng, kind, 'short'))}-" \
                   f"{w.teacher(t, mess.teacher(rng, t, _teacher_obj(school, t).title, 'short'))}"
        return opts["legend"][first.block]
    subj = w.subject(first.subject, mess.subject(rng, first.subject, opts["subject_style"]))
    t = first.teacher
    if not t or opts["teacher_in_cell"] == "none":
        return subj
    tw = w.teacher(t, mess.teacher(rng, t, _teacher_obj(school, t).title, opts["teacher_style"]))
    return {"dash": f"{subj}-{tw}", "paren": f"{subj} ({tw})", "newline": f"{subj}\n{tw}",
            "slash": f"{subj}/{tw}"}[opts["teacher_in_cell"]]


def _options(rng, school, **force) -> dict:
    o = {
        "subject_style": rng.choice(["full", "short", "mixed", "caps"]),
        "teacher_in_cell": rng.choice(["none", "dash", "paren", "newline", "none"]),
        "teacher_style": rng.choice(["first", "short", "initial", "titled", "caps"]),
        "section_style": rng.choice(["plain", "dash", "roman", "roman_dash", "class", "grade", "std", "class_roman"]),
        "day_style": rng.choice(["full", "short", "tiny", "caps"]),
        "period_style": rng.choice(["num", "roman", "period_roman", "p", "ordinal"]),
        "bell_row": rng.random() < 0.5,
        "break_style": rng.choice(["column", "letters", "none"]),
        "block_style": rng.choice(["short", "options", "legend", "teacher"]),
        "class_teacher_line": rng.random() < 0.5,
    }
    o.update(force)
    o["legend"] = {b["name"]: f"{ROMAN[b['grade']]} {'L' if 'Language' in b['name'] else 'C'}{i + 1}"
                   for i, b in enumerate(school.blocks)}
    return o


def _legend_lines(school, w, rng, opts, sections) -> list[str]:
    if opts["block_style"] != "legend":
        return []
    lines = []
    grades = {school.grade_of(s) for s in sections}
    for b in school.blocks:
        if b["grade"] in grades:
            subs = "/".join(w.subject(g["subject"], mess.subject(rng, g["subject"], "caps")) for g in b["groups"])
            lines.append(f"({opts['legend'][b['name']]}- {subs})")
    return lines


# ----------------------------------------------------------------- timetables

def timetable_class_grids(rng: random.Random, school: School, sections=None, **force):
    """A grid per section, days down the side and periods across - Aditya
    Birla, BBPS Noida, Baptist Convent and Keren all do this. Breaks are a
    column (or a column spelt one letter per row, Baptist), bell times a
    second header row, the class teacher a line above."""
    o = _options(rng, school, **force)
    w = Written()
    slots = _by_slot(school)
    sheets = []
    for sec in sections or school.sections:
        label = w.section(sec, mess.section(rng, sec, o["section_style"]))
        notes = []
        if force.get("keren"):
            ct = next((t for t in school.teachers if t.class_teacher_of == sec), None)
            ctn = w.teacher(ct.name, mess.teacher(rng, ct.name, ct.title, "caps")) if ct else ""
            notes = []
            head = [f"Teacher's Name :  {ctn}", "", "", "", "", "", label]
        else:
            notes.append(label if o["section_style"] != "class_roman" else label)
            if o["class_teacher_line"]:
                ct = next((t for t in school.teachers if t.class_teacher_of == sec), None)
                if ct:
                    notes.append(f"CLASS TEACHER – {w.teacher(ct.name, mess.teacher(rng, ct.name, ct.title, 'caps'))}")
            head = None
        cols = []  # ("p", n) or ("b", name)
        for p in range(1, school.periods + 1):
            cols.append(("p", p))
            for after, bname in school.breaks:
                if after == p and o["break_style"] != "none":
                    cols.append(("b", bname))
        rows, merges = [], []
        if head:
            rows.append(head)
        corner = "Days" if not o["bell_row"] else "Day / Period"
        if not head and o["section_style"] in ("plain", "roman") and rng.random() < 0.4:
            corner = label  # BBPS: the section name in the corner cell
        rows.append([corner] + [_period_head(c[1], o["period_style"]) if c[0] == "p" else "" for c in cols])
        if o["bell_row"]:
            rows.append(["Time"] + [school.bell[c[1] - 1] if c[0] == "p" else "" for c in cols])
        top = len(rows)
        for d in range(school.days):
            row = [_day_name(d, o["day_style"])]
            for c in cols:
                if c[0] == "b":
                    row.append("")
                else:
                    row.append(_cell(rng, school, w, slots.get((sec, d, c[1]), []), o))
            rows.append(row)
        for ci, c in enumerate(cols, start=1):
            if c[0] == "b":
                text = c[1].upper()
                if o["break_style"] == "letters":
                    for i, d in enumerate(range(school.days)):
                        rows[top + i][ci] = text[i] if i < len(text) else ""
                else:
                    rows[top][ci] = text
                    merges.append((top, ci, top + school.days - 1, ci))
        sheets.append(Sheet(name=label.replace("/", "-")[:31], rows=rows, merges=merges,
                            notes_above=_legend_lines(school, w, rng, o, [sec]) + notes))
    return sheets, w, o


def timetable_transposed(rng: random.Random, school: School, sections=None, **force):
    """Periods (or clock times) down the side, days across, breaks as full
    rows - the KVS model timetable."""
    o = _options(rng, school, **force)
    w = Written()
    slots = _by_slot(school)
    sheets = []
    for sec in sections or school.sections:
        label = w.section(sec, mess.section(rng, sec, o["section_style"]))
        rows = [["Time" if o["bell_row"] else "Period"] + [_day_name(d, o["day_style"]) for d in range(school.days)]]
        merges = []
        for p in range(1, school.periods + 1):
            head = school.bell[p - 1].replace("-", " to ") if o["bell_row"] else _period_head(p, o["period_style"])
            rows.append([head] + [_cell(rng, school, w, slots.get((sec, d, p), []), o) for d in range(school.days)])
            for after, bname in school.breaks:
                if after == p:
                    if rng.random() < 0.5:
                        rows.append([""] + [bname.upper()] * school.days)
                    else:
                        rows.append([bname.upper()] + [""] * school.days)
                        merges.append((len(rows) - 1, 0, len(rows) - 1, school.days))
        sheets.append(Sheet(name=label[:31], rows=rows, merges=merges,
                            notes_above=_legend_lines(school, w, rng, o, [sec]) + [f"Time Table - {label}"]))
    return sheets, w, o


def timetable_master(rng: random.Random, school: School, sections=None, **force):
    """Every section on one sheet: a row each, days across with their periods
    under them (two header rows, the day merged over its periods)."""
    o = _options(rng, school, teacher_in_cell=rng.choice(["none", "dash"]), **force)
    w = Written()
    slots = _by_slot(school)
    head1, head2, merges = ["Class"], [""], []
    for d in range(school.days):
        start = len(head1)
        for p in range(1, school.periods + 1):
            head1.append(_day_name(d, o["day_style"]) if p == 1 else "")
            head2.append(_period_head(p, "num"))
        merges.append((0, start, 0, start + school.periods - 1))
    rows = [head1, head2]
    for sec in sections or school.sections:
        row = [w.section(sec, mess.section(rng, sec, o["section_style"]))]
        for d in range(school.days):
            for p in range(1, school.periods + 1):
                row.append(_cell(rng, school, w, slots.get((sec, d, p), []), o))
        rows.append(row)
    sheet = Sheet(name="Master", rows=rows, merges=merges,
                  notes_above=[f"{school.name.upper()}", "MASTER TIME TABLE 2025-26"]
                  + _legend_lines(school, w, rng, o, sections or school.sections))
    return [sheet], w, o


def timetable_teacher_grids(rng: random.Random, school: School, teachers=None, **force):
    """A grid per teacher with the class in each cell - KV Tezpur: titled by
    post ('TGT: MATHS 2') or by name, cells 'VII B' or 'VI A/SCI', and a block
    taught to several sections at once as 'XI A+B+C'."""
    o = _options(rng, school, **force)
    w = Written()
    title_by = rng.choice(["name", "post", "both"])
    count = defaultdict(int)
    cell_subject = rng.random() < 0.5
    by_teacher = defaultdict(list)
    for l in school.lessons:
        if l.teacher:
            by_teacher[l.teacher].append(l)
    sheets = []
    for t in teachers or [t.name for t in school.teachers]:
        tobj = _teacher_obj(school, t)
        subj = tobj.subjects[0]
        count[(tobj.post, subj)] += 1
        post_title = f"{tobj.post}: {mess.subject(rng, subj, 'caps')} {count[(tobj.post, subj)]}"
        named = mess.teacher(rng, t, tobj.title, rng.choice(["titled", "caps", "plain"]))
        title = {"name": named, "post": post_title, "both": f"{named} ({tobj.post} {mess.subject(rng, subj, 'full')})"}[title_by]
        # A grid titled by post ('TGT: MATHS 2') never names the teacher: the
        # file can't tell who it is, and the scorer must not expect a name.
        w.teacher(t, post_title if title_by == "post" else named)
        cell = defaultdict(list)
        for l in by_teacher[t]:
            cell[(l.day, l.period)].append(l)
        rows = [["DAY/PERIODS"] + [_period_head(p, "num") for p in range(1, school.periods + 1)]]
        for d in range(school.days):
            row = [_day_name(d, "caps")]
            for p in range(1, school.periods + 1):
                ls = cell.get((d, p), [])
                if not ls:
                    row.append("")
                    continue
                secs = sorted({l.section for l in ls})
                g = school.grade_of(secs[0])
                if len(secs) > 1:
                    text = f"{ROMAN[g]} " + "+".join(s[-1] for s in secs)
                    for s in secs:
                        w.section(s, text)
                else:
                    text = w.section(secs[0], mess.section(rng, secs[0], "roman"))
                if cell_subject:
                    text += "/" + w.subject(ls[0].subject, mess.subject(rng, ls[0].subject, "short"))
                row.append(text)
            rows.append(row)
        sheets.append(Sheet(name=(named if title_by != "post" else post_title)[:31].replace(":", ""), rows=rows,
                            notes_above=[title]))
    o.update(title_by=title_by, cell_subject=cell_subject)
    return sheets, w, o


TIMETABLE_LAYOUTS = {
    "class_grids": timetable_class_grids,
    "keren": lambda rng, school, sections=None: timetable_class_grids(
        rng, school, sections, keren=True, block_style="teacher", teacher_in_cell="dash", teacher_style="short",
        subject_style="short", day_style="tiny", bell_row=False, break_style="none", section_style="roman"),
    "transposed": timetable_transposed,
    "master": timetable_master,
    "teacher_grids": timetable_teacher_grids,
}


# ------------------------------------------------------------------- subjects

def subjects_list(rng, school: School, **_):
    """A plain list with a title above and S.No. - the simplest sheet a
    school sends."""
    w = Written()
    style = rng.choice(["full", "mixed", "caps"])
    rows = [["S.No.", rng.choice(["Subject", "Subjects", "SUBJECT NAME", "Name of the Subject"])]]
    subs = sorted({p["subject"] for p in school.plan} | {g["subject"] for b in school.blocks for g in b["groups"]})
    rng.shuffle(subs)
    for i, s in enumerate(subs, start=1):
        rows.append([f"{i}", w.subject(s, mess.subject(rng, s, style))])
    if rng.random() < 0.5:
        rows.append(["", ""])
        rows.append(["", "Total subjects: " + str(len(subs))])
    return [Sheet("Subjects", rows, notes_above=[school.name, "LIST OF SUBJECTS 2025-26"])], w, {"style": style}


def subjects_allotment(rng, school: School, **_):
    """Subject down the side, a column per grade with its periods a week -
    the KVS allotment table, and what most coordinators keep."""
    w = Written()
    style = rng.choice(["full", "mixed", "short"])
    grades = school.grades
    per = defaultdict(dict)
    for p in school.plan:
        g = school.grade_of(p["section"])
        per[p["subject"]][g] = p["periods"]
    for b in school.blocks:
        kind = "Second Language" if "Second" in b["name"] else "Third Language" if "Third" in b["name"] else None
        if kind:
            per[kind][b["grade"]] = b["periods"]
        else:
            for g in b["groups"]:
                per[g["subject"]][b["grade"]] = b["periods"]
    head = rng.choice(["Subject", "SUBJECTS", "Name of Subject"])
    gl = rng.choice(["num", "roman", "class"])
    rows = [[head] + [str(g) if gl == "num" else ROMAN[g] if gl == "roman" else f"Class {g}" for g in grades]]
    for s in sorted(per):
        rows.append([w.subject(s, mess.subject(rng, s, style))] + [str(per[s].get(g, "")) for g in grades])
    rows.append(["TOTAL"] + [str(sum(per[s].get(g, 0) for s in per)) for g in grades])
    return [Sheet("Allotment", rows, notes_above=["DISTRIBUTION OF PERIODS PER WEEK"])], w, {"style": style}


def subjects_by_grade_text(rng, school: School, **_):
    """'Class 6: English, Maths, Science, ...' - a line per grade, typed in
    Word or straight into a cell."""
    w = Written()
    style = rng.choice(["mixed", "short", "full"])
    rows = []
    by_grade = defaultdict(set)
    for p in school.plan:
        by_grade[school.grade_of(p["section"])].add(p["subject"])
    for b in school.blocks:
        for g in b["groups"]:
            by_grade[b["grade"]].add(g["subject"])
    for g in sorted(by_grade):
        names = sorted(by_grade[g])
        rows.append([f"Class {ROMAN[g]}", ", ".join(w.subject(s, mess.subject(rng, s, style)) for s in names)])
    return [Sheet("Subjects", rows, notes_above=["Subjects offered (2025-26)"])], w, {"style": style}


SUBJECT_LAYOUTS = {"list": subjects_list, "allotment": subjects_allotment, "by_grade": subjects_by_grade_text}


# ------------------------------------------------------------------- teachers

def _designation(rng, t, w):
    subj = w.subject(t.subjects[0], mess.subject(rng, t.subjects[0], rng.choice(["full", "short"])))
    return rng.choice([f"{t.post} ({subj})", f"{t.post}({subj})", f"{t.post} - {subj}"])


def teachers_kv_table(rng, school: School, **_):
    """Name | Designation 'TGT (Maths)' | dates | employee code, with the
    principal and non-teaching staff in the same list - KV Chheoki."""
    w = Written()
    nstyle = rng.choice(["titled", "caps", "mixed"])
    rows = [["S.No", "Name", "Designation", "Date of joining", "Employee Code"]]
    staff = list(school.teachers)
    rng.shuffle(staff)
    rows.append(["1", "Shri. " + rng.choice(["Suresh Babu", "Anand Raj"]), "Principal", "01/06/2019", str(rng.randint(1000, 9999))])
    for i, t in enumerate(staff, start=2):
        rows.append([str(i), w.teacher(t.name, mess.noisy(rng, mess.teacher(rng, t.name, t.title, nstyle), 0.08)),
                     _designation(rng, t, w), f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/20{rng.randint(10, 25)}",
                     str(rng.randint(10000, 99999))])
    for extra, post in [("Sh. Mani", "Sub Staff"), ("Smt. Rani", "Office Assistant")]:
        rows.append([str(len(rows)), extra, post, "", ""])
    return [Sheet("Staff", rows, notes_above=["STAFF DETAILS"])], w, {"name_style": nstyle, "non_teaching": 3}


def _range_text(grades: list[int]) -> str:
    if not grades:
        return ""
    if grades == list(range(grades[0], grades[-1] + 1)) and len(grades) > 2:
        return f"{grades[0]} to {grades[-1]}"
    return ", ".join(map(str, grades[:-1])) + (f" & {grades[-1]}" if len(grades) > 1 else str(grades[0]))


def teachers_free_text(rng, school: School, **_):
    """Name | Subjects 'Eng & SST' | Classes '6 to 8' | Mobile | Email -
    subjects and classes as people type them."""
    w = Written()
    rows = [["Name", rng.choice(["Subject(s)", "Subjects Handled", "Subject"]), "Classes", "Mobile", "Email"]]
    for t in school.teachers:
        subj = " & ".join(w.subject(s, mess.subject(rng, s, "mixed")) for s in t.subjects)
        nm = w.teacher(t.name, mess.teacher(rng, t.name, t.title, rng.choice(["titled", "plain", "initial"])))
        rows.append([nm, subj, _range_text(t.grades), f"9{rng.randint(100000000, 999999999)}",
                     f"{t.name.split()[0].lower()}{rng.randint(1, 99)}@school.in" if rng.random() < 0.7 else ""])
    return [Sheet("Teachers", rows)], w, {}


def teachers_by_department(rng, school: School, **_):
    """A heading row per department ('ENGLISH DEPARTMENT') with its teachers
    under it, so the subject is never on the teacher's own row."""
    w = Written()
    rows = [["Sl", "Name of the Teacher", "Designation", "Classes"]]
    by = defaultdict(list)
    for t in school.teachers:
        by[t.subjects[0]].append(t)
    n = 0
    for subj in sorted(by):
        rows.append(["", f"{w.subject(subj, mess.subject(rng, subj, 'caps'))} DEPARTMENT", "", ""])
        for t in by[subj]:
            n += 1
            rows.append([str(n), w.teacher(t.name, mess.teacher(rng, t.name, t.title, "titled")), t.post,
                         _range_text(t.grades)])
    return [Sheet("Staff", rows, notes_above=[school.name])], w, {}


def teachers_allotment(rng, school: School, **_):
    """A teacher's name as a heading, then the classes they take with periods:
    'VIII B - 6' - the teacher-by-teacher allotment list."""
    w = Written()
    rows = []
    per = defaultdict(lambda: defaultdict(int))
    for p in school.plan:
        if p["teacher"]:
            per[p["teacher"]][(p["section"], p["subject"])] += p["periods"]
    for b in school.blocks:
        for g in b["groups"]:
            for s in b["sections"][:1]:
                per[g["teacher"]][(s, g["subject"])] += b["periods"]
    for t in school.teachers:
        rows.append([w.teacher(t.name, mess.teacher(rng, t.name, t.title, "caps")) + f" ({t.post})"])
        for (sec, subj), n in sorted(per[t.name].items()):
            rows.append([f"{w.section(sec, mess.section(rng, sec, 'roman'))} - "
                         f"{w.subject(subj, mess.subject(rng, subj, 'short'))} - {n}"])
        rows.append([""])
    return [Sheet("Allotment", rows, notes_above=["WORK ALLOTMENT 2025-26"])], w, {}


TEACHER_LAYOUTS = {"kv_table": teachers_kv_table, "free_text": teachers_free_text,
                   "by_department": teachers_by_department, "allotment": teachers_allotment}


# ---------------------------------------------------------------------- rules

def rules_message(rng, school: School, **_):
    """A coordinator's WhatsApp message: a greeting, then numbered notes about
    teachers and subjects, the way Keren's arrived. Each note's meaning is in
    the truth as plain facts."""
    w = Written()
    facts, lines = [], []
    days = DAYS[: school.days]
    picks = rng.sample(school.teachers, k=min(5, len(school.teachers)))
    for i, t in enumerate(picks, start=1):
        kind = rng.choice(["days", "part_time", "morning", "no_last", "max_day"])
        nm = mess.teacher(rng, t.name, t.title, rng.choice(["titled", "first", "plain"]))
        if kind != "no_last":  # that note names the subject, not the teacher
            w.teacher(t.name, nm)
        subj = mess.subject(rng, t.subjects[0], "full")
        if kind == "no_last":
            w.subject(t.subjects[0], subj)
        if kind == "days":
            ds = sorted(rng.sample(range(school.days), k=3))
            facts.append({"type": "teacher_only_days", "teacher": t.name, "days": [days[d] for d in ds]})
            lines.append(f"{i}. {nm} ({subj} teacher) - she can be given classes only on "
                         f"{', '.join(days[d] for d in ds[:-1])} and {days[ds[-1]]}")
        elif kind == "part_time":
            d1, d2 = rng.sample(range(school.days), k=2)
            lunch = next(a for a, n in school.breaks if n == "Lunch")
            facts.append({"type": "teacher_unavailable", "teacher": t.name,
                          "slots": [{"day": days[d1], "periods": list(range(1, lunch + 1))},
                                    {"day": days[d2], "periods": list(range(lunch + 1, school.periods + 1))}]})
            lines.append(f"{i}. {nm} - part time. Not available {days[d1]} morning and {days[d2]} afternoon")
        elif kind == "morning":
            lunch = next(a for a, n in school.breaks if n == "Lunch")
            facts.append({"type": "teacher_unavailable", "teacher": t.name,
                          "slots": [{"day": d, "periods": list(range(lunch + 1, school.periods + 1))} for d in days]})
            lines.append(f"{i}. {nm} leaves after lunch every day")
        elif kind == "no_last":
            facts.append({"type": "subject_not_in_period", "subject": t.subjects[0], "period": school.periods})
            lines.append(f"{i}. No {subj} in the last period please")
        else:
            facts.append({"type": "teacher_max_per_day", "teacher": t.name, "value": 5})
            lines.append(f"{i}. {nm} should not have more than 5 periods a day")
    text = [rng.choice(["Good eve sir.", "Hello sir,", "Dear Sir/Madam,", "Sir pls note"]), *lines,
            rng.choice(["Thank you", "Thanks", "Regards"])]
    return [Sheet("Message", [[l] for l in text])], w, {"facts": facts, "text": "\n".join(text)}


RULE_LAYOUTS = {"message": rules_message}

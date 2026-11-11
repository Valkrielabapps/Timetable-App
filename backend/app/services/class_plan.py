"""
Every section's weekly plan from the school's own sheet.

The allotment sheet most schools keep - a small table per class: a label
("CLASS 6-AB"), then Subjects | Periods | Teacher - is the whole weekly plan:
which sections exist, how many periods of each subject each one has, and who
teaches it. smart_import.py reads its subjects and teachers; this reads the
rest, so the school doesn't type the plan in again section by section.

Nothing is guessed. Where the sheet can be read more than one way the school
is asked, and each answer is applied exactly:

  sections       "Class 3" names no sections: just 3A, or 3A and 3B?
  teachers       "Kavita k" isn't a teacher here: which one is it?
  shared         "Zareena/Shallu" for 6-AB: Zareena 6A and Shallu 6B, or
                 either for either?
  combined       "Maths/Bio" with "Aman/Deepak": a choice students make (an
                 elective block) or two subjects? "English Lit + Lib", 4
                 periods, one teacher: one subject, or split how?
  existing       sections that already have a plan: replace it or add to it?

And what would make generating fail later is found now: a section planned
for more periods than the week has, and a teacher planned for more than
they can teach.

Preview reads the file and returns the plan and the questions; commit takes
that plan back with the answers and saves it all in one transaction, also
making sure every teacher it names is qualified for what they are given (so
the plan never fails for that).
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.school import (
    ClassGroup, ElectiveBlock, ElectiveOption, Period, Subject, SubjectRequirement, Teacher,
)
from app.services.smart_import import (
    _NOT_A_TEACHER, _concept, count_of, plan_tables, _key, _norm, _rule_subjects, _split_people,
    _split_subjects, look_alike_people, read_sheets,
)

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11,
          "xii": 12}
_EARLY = {"kg": "KG", "lkg": "LKG", "ukg": "UKG", "nursery": "Nursery", "pg": "PG", "prekg": "Pre-KG",
          "playgroup": "Play Group", "prep": "Prep", "pp1": "PP1", "pp2": "PP2"}
_STREAMS = {"sci": "Science", "science": "Science", "com": "Commerce", "comm": "Commerce", "commerce": "Commerce",
            "hum": "Humanities", "humanities": "Humanities", "arts": "Arts", "art": "Arts", "bio": "Biology",
            "cs": "Computer Science", "maths": "Maths", "math": "Maths", "pcm": "PCM", "pcb": "PCB",
            "neet": "NEET", "jee": "JEE", "nj": "NEET/JEE", "neetjee": "NEET/JEE", "cuet": "CUET",
            "iit": "IIT", "foundation": "Foundation"}
_CLASS_TEACHER = {"classteacher", "ct"}


# ------------------------------------------------------------ reading labels

def _grade_and_rest(label: str) -> tuple[str | None, str]:
    """"CLASS 6-AB" -> ("6", "-AB"); "Class 9 (Sci)" -> ("9", "(Sci)");
    "Std IX A" -> ("9", "A"); "Class KG" -> ("KG", "")."""
    text = label.strip()
    m = re.match(r"^\s*(?:class|grade|std\.?|standard)?\s*[-:]?\s*", text, re.I)
    rest = text[m.end():] if m else text
    m = re.match(r"(\d{1,2})(?![\d])", rest)
    if m:
        return m.group(1), rest[m.end():]
    m = re.match(r"([ivx]{1,4})\b", rest, re.I)
    if m and m.group(1).lower() in _ROMAN:
        return str(_ROMAN[m.group(1).lower()]), rest[m.end():]
    m = re.match(r"([a-z][a-z\- ]{0,9}?)(?=$|[\s\-(:,])", rest, re.I)
    if m and _key(m.group(1)) in _EARLY:
        return _EARLY[_key(m.group(1))], rest[m.end():]
    return None, rest


def _sections_from(rest: str) -> list[str]:
    """"-AB" -> [A, B]; "A & B" -> [A, B]; "(Sci)" -> [Science]; "" -> []."""
    r = rest.strip(" -:()[]")
    if not r:
        return []
    k = _key(r)
    if k in _STREAMS:
        return [_STREAMS[k]]
    parts = [p for p in re.split(r"[\s,&/+\-]+|\band\b", r) if p]
    if parts and all(re.fullmatch(r"[A-Za-z]", p) for p in parts):
        return [p.upper() for p in parts]
    if re.fullmatch(r"[A-Z]{2,6}", r):  # "AB", "ABC"
        return list(r)
    words = [p for p in re.split(r"[\s()\-]+", r) if p]
    if words:
        named = [_STREAMS.get(_key(w), w if not w.islower() else w.title()) for w in words]
        return [" ".join(dict.fromkeys(named))]
    return []


def _grade_name(token: str, school_grades: list[str]) -> str:
    """The school's own way of naming a grade: "Grade 6", "Class 6", "6"."""
    if not token.isdigit():
        return token
    for g in school_grades:
        m = re.fullmatch(r"(.*?)(\d{1,2})", g.strip())
        if m and m.group(2) == token:
            return g
    for g in school_grades:
        m = re.fullmatch(r"(.*?)(\d{1,2})", g.strip())
        if m:
            return f"{m.group(1)}{token}"
    return f"Grade {token}"


def _periods(cell: str) -> int:
    # "3+3": two parts of one subject, six periods.
    if count_of(cell or ""):
        return count_of(cell)
    try:
        return max(0, int(round(float(cell))))
    except (TypeError, ValueError):
        m = re.search(r"\d+", cell or "")
        return int(m.group()) if m else 0


# -------------------------------------------------------------- the preview

def _school(db: Session, school_id: int) -> dict:
    groups = db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()
    return {
        "groups": groups,
        "grades": sorted({g.grade for g in groups if g.grade}),
        "subjects": db.query(Subject).filter(Subject.school_id == school_id).all(),
        "teachers": db.query(Teacher).filter(Teacher.school_id == school_id).all(),
        "lessons": sum(1 for p in db.query(Period).filter(Period.school_id == school_id) if not p.is_break),
    }


def _subject_name(raw: str, school_subjects: list[str]) -> str:
    by_norm = {_norm(s): s for s in school_subjects}
    if _norm(raw) in by_norm:
        return by_norm[_norm(raw)]
    return _rule_subjects([raw], school_subjects)[raw][0] if _concept(raw) else raw.strip()


def _one_name(subjects: list[str]) -> str:
    """"History", "Civics" -> "History & Civics"."""
    return " & ".join(subjects) if len(subjects) <= 2 else ", ".join(subjects[:-1]) + " & " + subjects[-1]


def _splits(n: int, a: str, b: str) -> list[dict]:
    return [{"key": f"split:{x}", "label": f"{a} {x}, {b} {n - x}"} for x in range(n - 1, 0, -1)]


def build_preview(db: Session, school_id: int, filename: str, content: bytes) -> dict:
    sheets = read_sheets(filename, content, "teachers")
    # A table per class, a grid of counts (classes down, subjects across, or
    # the other way), or a column of subjects per stream.
    title, tables = plan_tables(sheets)
    if not tables:
        raise ValueError("Couldn't find the periods for each class in this file. It can read a table per class "
                         "(Subjects, Periods, Teacher), a grid with classes down one side and subjects across "
                         "the top (or the other way round) with the periods in the cells, or a column of subjects "
                         "with a column of periods for each class. Fill in the plans by hand instead, or upload "
                         "the allotment sheet.")
    s = _school(db, school_id)
    subject_names = [x.name for x in s["subjects"]]
    teacher_names = [t.name for t in s["teachers"]]
    by_teacher = {_norm(t): t for t in teacher_names}
    questions: list[dict] = []
    checks: list[str] = []
    skipped: list[str] = []
    new_subjects: list[str] = []

    # Teachers named in the sheet, matched to the school's.
    raw_people: dict[str, None] = {}
    for t in tables:
        for _, _, cell in t["items"]:
            for p in _split_people(cell) + [x for x in re.split(r"\s*/\s*", cell) if _key(x) in _CLASS_TEACHER]:
                raw_people.setdefault(p, None)
    people: dict[str, dict] = {}
    for raw in raw_people:
        if _key(raw) in _CLASS_TEACHER:
            people[raw] = {"match": None, "class_teacher": True}
        elif _norm(raw) in by_teacher:
            people[raw] = {"match": by_teacher[_norm(raw)]}
        else:
            cands = [b if a == raw else a for a, b in look_alike_people([raw] + teacher_names) if raw in (a, b)]
            qid = f"teacher:{raw}"
            people[raw] = {"match": None, "q": qid}
            questions.append({
                "id": qid,
                "text": f"Who is “{raw}” in the sheet? There's no teacher by that name.",
                "options": [{"key": f"is:{c}", "label": c} for c in cands]
                + [{"key": "new", "label": f"Add “{raw}” as a new teacher"},
                   {"key": "none", "label": "Leave those periods without a teacher for now"}],
                "suggested": f"is:{cands[0]}" if len(cands) == 1 else "new",
            })

    out_tables = []
    no_sections: list[str] = []
    combined: dict = {}
    shared_example: dict = {}
    existing_with_plan: set[int] = set()
    plan_ids = {r.class_group_id for r in db.query(SubjectRequirement.class_group_id).join(
        ClassGroup, ClassGroup.id == SubjectRequirement.class_group_id).filter(ClassGroup.school_id == school_id)}
    for n, t in enumerate(tables):
        tid = f"t{n}"
        token, rest = _grade_and_rest(t["label"])
        grade = _grade_name(token, s["grades"]) if token else None
        letters = _sections_from(rest)
        have = [g for g in s["groups"] if grade and _norm(g.grade or "") == _norm(grade)]
        table = {"id": tid, "label": t["label"], "grade": grade or t["label"], "sections": letters, "items": []}
        if not letters and have:
            table["sections"] = [g.name for g in have]
        elif not letters:
            table["sections_q"] = "sections:all"
            no_sections.append(t["label"])
        for g in have:
            if g.name.lower() in {x.lower() for x in table["sections"]} and g.id in plan_ids:
                existing_with_plan.add(g.id)

        shared_items = 0
        for j, (subj_cell, per_cell, teacher_cell) in enumerate(t["items"]):
            periods = _periods(per_cell)
            # "PT/Games" is one subject spelt two ways, not two subjects.
            subjects = list(dict.fromkeys(_subject_name(x, subject_names) for x in _split_subjects(subj_cell)))
            if not subjects:
                continue
            if periods == 0:
                skipped.append(f"{subj_cell} ({t['label']})")
                continue
            for x in subjects:
                if _norm(x) not in {_norm(y) for y in subject_names} and x not in new_subjects:
                    new_subjects.append(x)
            ppl = list(dict.fromkeys(
                _split_people(teacher_cell) + [x for x in re.split(r"\s*/\s*", teacher_cell) if _key(x) in _CLASS_TEACHER]
            ))
            item = {"id": f"{tid}.{j}", "raw": subj_cell, "subjects": subjects, "periods": periods, "teachers": ppl}
            if len(subjects) > 1:
                # The same combined entry in several classes is asked once.
                sig = (_norm(re.sub(r"\s+", "", subj_cell)), tuple(_norm(p) for p in ppl), periods)
                group = combined.setdefault(sig, {"qid": f"combined:{len(combined)}", "raw": subj_cell.strip(),
                                                  "teachers": teacher_cell.strip(), "ppl": ppl, "periods": periods,
                                                  "subjects": subjects, "labels": []})
                group["labels"].append(t["label"])
                item["q"] = group["qid"]
            elif len(ppl) > 1 and len(ppl) == len(table["sections"]) and not table.get("sections_q"):
                shared_items += 1
            table["items"].append(item)
        if shared_items:
            table["shared_q"] = "shared:all"
            if not shared_example:
                ex = next(x for x in table["items"] if len(x["teachers"]) == len(table["sections"]) and len(x["subjects"]) == 1)
                shared_example.update(label=t["label"], raw=ex["raw"], ppl=ex["teachers"], grade=grade,
                                      secs=table["sections"])
        out_tables.append(table)

    if no_sections:
        questions.append({
            "id": "sections:all",
            "text": f"These classes don't say which sections they are for: {', '.join(no_sections)}. "
                    "How many sections does each have?",
            "options": [{"key": "n:1", "label": "One each (A)"}, {"key": "n:2", "label": "Two each (A and B)"},
                        {"key": "n:3", "label": "Three each (A, B and C)"}, {"key": "n:4", "label": "Four each (A to D)"}],
            "suggested": "n:1",
            "note": "If they differ, pick the most common; you can add or remove sections afterwards in the sidebar.",
        })
    if shared_example:
        e = shared_example
        questions.append({
            "id": "shared:all",
            "text": f"Where a class with several sections names one teacher per section for a subject (like "
                    f"{e['label']}, “{e['raw']}”: {' / '.join(e['ppl'])}), does each teacher take one section, in order?",
            "options": [
                {"key": "order", "label": f"Yes: {e['ppl'][0]} teaches {e['grade']} {e['secs'][0]}, "
                                          f"{e['ppl'][1]} teaches {e['grade']} {e['secs'][1]}, and so on"},
                {"key": "either", "label": "No: any of the teachers named can teach any of the sections"},
            ],
            "suggested": "order",
        })
    for g in combined.values():
        subjects, ppl, periods = g["subjects"], g["ppl"], g["periods"]
        where = ", ".join(g["labels"][:4]) + ("…" if len(g["labels"]) > 4 else "")
        opts = []
        if len(ppl) != 1:
            pairing = ", ".join(f"{a} with {b}" for a, b in zip(subjects, ppl)) if len(ppl) == len(subjects) else ""
            opts.append({"key": "choice", "label": "A choice: each student takes one, at the same time"
                         + (f" ({pairing})" if pairing else "")})
        opts.append({"key": "one", "label": f"One subject, “{_one_name(subjects)}”, {periods} periods"})
        if len(subjects) == 2 and periods >= 2:
            opts += _splits(periods, subjects[0], subjects[1])
        opts.append({"key": "separate", "label": f"Separate subjects, {periods} periods each"})
        opts.append({"key": "skip", "label": "Leave it out; I'll add it myself"})
        questions.append({
            "id": g["qid"],
            "text": f"“{g['raw']}”{' (' + g['teachers'] + ')' if g['teachers'] else ''}, {periods} periods a week, in {where}. "
                    "How should it go in the timetable?",
            "options": opts,
            "suggested": "choice" if len(ppl) > 1 and len(ppl) == len(subjects) else "one",
        })
    if existing_with_plan:
        names = {g.id: f"{g.grade or ''} {g.name}".strip() for g in s["groups"]}
        questions.append({
            "id": "existing",
            "text": f"{len(existing_with_plan)} of these sections already have a plan "
                    f"({', '.join(sorted(names[i] for i in existing_with_plan)[:5])}{'…' if len(existing_with_plan) > 5 else ''}). What should happen to it?",
            "options": [{"key": "replace", "label": "Replace it with the plan from the file"},
                        {"key": "add", "label": "Keep it, and add or update the subjects in the file"}],
            "suggested": "replace",
        })

    # What would make generating fail, found now (choices counted once).
    lessons = s["lessons"]
    load: dict[str, int] = defaultdict(int)
    for table in out_tables:
        nsec = max(1, len(table["sections"]))
        total = sum(it["periods"] for it in table["items"])
        if lessons and total > lessons:
            checks.append(f"{table['label']} has {total} periods planned but your week has {lessons} lessons. "
                          "Generating will fail until it's cut down or the week has more periods.")
        for it in table["items"]:
            ppl = [p for p in it["teachers"] if _key(p) not in _CLASS_TEACHER]
            if len(ppl) == 1 and len(it["subjects"]) == 1:
                load[people.get(ppl[0], {}).get("match") or ppl[0]] += it["periods"] * nsec
    maxes = {t.name: t.max_periods_per_week for t in s["teachers"]}
    for name, total in sorted(load.items(), key=lambda x: -x[1]):
        cap = maxes.get(name) or lessons
        if cap and total > cap:
            checks.append(f"{name} is planned for {total} periods a week, more than "
                          f"{'their limit of ' + str(cap) if maxes.get(name) else 'the ' + str(lessons) + ' lessons in your week'}. "
                          "Share some of them with another teacher, or generating will fail.")

    sections_total = sum(len(t["sections"]) for t in out_tables if not t.get("sections_q"))
    return {
        "sheet": title,
        "plan": {"tables": out_tables, "people": people, "ask_existing": bool(existing_with_plan)},
        "questions": questions,
        "checks": checks,
        "skipped": skipped,
        "new_subjects": new_subjects,
        "lessons_per_week": lessons,
        "summary": {"classes": len(out_tables), "sections": sections_total,
                    "subjects": sum(len(t["items"]) for t in out_tables)},
    }


# --------------------------------------------------------------- the commit

class PlanError(ValueError):
    pass


def commit(db: Session, school_id: int, plan: dict, answers: dict[str, str]) -> dict:
    """Save the previewed plan with the school's answers. All or nothing."""
    try:
        result = _commit(db, school_id, plan, answers)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def _answer(answers: dict, qid: str | None, allowed_prefixes: tuple[str, ...]) -> str | None:
    if not qid:
        return None
    a = answers.get(qid)
    if not a or not a.startswith(allowed_prefixes):
        raise PlanError("Answer every question before filling in the plans.")
    return a


def _commit(db: Session, school_id: int, plan: dict, answers: dict) -> dict:
    s = _school(db, school_id)
    subjects = {_norm(x.name): x for x in s["subjects"]}
    teachers = {_norm(t.name): t for t in s["teachers"]}
    created = {"sections": [], "subjects": [], "teachers": [], "requirements": 0, "blocks": 0}

    def subject(name: str) -> Subject:
        if _norm(name) not in subjects:
            sub = Subject(school_id=school_id, name=name.strip()[:100])
            db.add(sub)
            db.flush()
            subjects[_norm(name)] = sub
            created["subjects"].append(sub.name)
        return subjects[_norm(name)]

    def teacher(raw: str) -> Teacher | None | str:
        info = (plan.get("people") or {}).get(raw) or {}
        if info.get("class_teacher") or _key(raw) in _CLASS_TEACHER:
            return "class_teacher"
        name = info.get("match")
        if info.get("q"):
            a = _answer(answers, info["q"], ("is:", "new", "none"))
            if a == "none":
                return None
            name = raw if a == "new" else a[3:]
        name = name or raw
        if _norm(name) not in teachers:
            if _key(name) in _NOT_A_TEACHER:
                return None
            t = Teacher(school_id=school_id, name=name.strip()[:100], qualified_subject_ids=[], qualified_grades=[])
            db.add(t)
            db.flush()
            teachers[_norm(name)] = t
            created["teachers"].append(t.name)
        return teachers[_norm(name)]

    def qualify(t: Teacher, sub: Subject, grade: str | None):
        ids = list(t.qualified_subject_ids or [])
        if sub.id not in ids:
            t.qualified_subject_ids = ids + [sub.id]
        gs = list(t.qualified_grades or [])
        if gs and grade and grade not in gs:
            t.qualified_grades = gs + [grade]

    replace = bool(plan.get("ask_existing")) and _answer(answers, "existing", ("replace", "add")) == "replace"
    groups_by_key = {(_norm(g.grade or ""), _norm(g.name)): g for g in s["groups"]}

    for table in plan.get("tables", []):
        grade = table.get("grade")
        names = list(table.get("sections") or [])
        if table.get("sections_q"):
            a = _answer(answers, table["sections_q"], ("n:",))
            names = [chr(ord("A") + i) for i in range(max(1, min(int(a[2:]), 26)))]
        sections: list[ClassGroup] = []
        for nm in names:
            key = (_norm(grade or ""), _norm(nm))
            g = groups_by_key.get(key)
            if g is None:
                g = ClassGroup(school_id=school_id, grade=grade, name=nm[:40])
                db.add(g)
                db.flush()
                groups_by_key[key] = g
                created["sections"].append(f"{grade} {nm}".strip())
            elif replace:
                db.query(SubjectRequirement).filter(SubjectRequirement.class_group_id == g.id).delete()
                for b in db.query(ElectiveBlock).filter(ElectiveBlock.class_group_id == g.id).all():
                    db.delete(b)
                db.flush()
            sections.append(g)
        in_order = table.get("shared_q") and _answer(answers, table["shared_q"], ("order", "either")) == "order"

        def put(g: ClassGroup, sub: Subject, periods: int, who: list):
            """One section's periods of one subject, with its teacher(s)."""
            ts = [x for x in who if isinstance(x, Teacher)]
            if "class_teacher" in who and g.class_teacher_id:
                ct = db.get(Teacher, g.class_teacher_id)
                if ct:
                    ts.append(ct)
            for t in ts:
                qualify(t, sub, grade)
            req = (db.query(SubjectRequirement)
                   .filter(SubjectRequirement.class_group_id == g.id, SubjectRequirement.subject_id == sub.id).first())
            if req is None:
                req = SubjectRequirement(class_group_id=g.id, subject_id=sub.id, periods_per_week=periods)
                db.add(req)
            else:
                req.periods_per_week = periods
            req.preferred_teacher_id = ts[0].id if len(ts) == 1 else None
            req.allowed_teacher_ids = [t.id for t in ts] if len(ts) > 1 else None
            created["requirements"] += 1

        for it in table.get("items", []):
            periods = int(it.get("periods") or 0)
            if periods <= 0:
                continue
            who_all = [teacher(p) for p in it.get("teachers", [])]
            subs = [str(x) for x in it.get("subjects", []) if str(x).strip()]
            if len(subs) == 1:
                sub = subject(subs[0])
                for i, g in enumerate(sections):
                    real = [w for w in who_all if w is not None]
                    if in_order and len(real) == len(sections) and len(real) > 1:
                        put(g, sub, periods, [real[i]])
                    else:
                        put(g, sub, periods, real)
                continue
            how = _answer(answers, it.get("q"), ("choice", "separate", "split:", "one", "skip"))
            if how == "skip":
                continue
            if how == "one":
                sub = subject(_one_name(subs))
                for g in sections:
                    put(g, sub, periods, [w for w in who_all if w is not None])
            elif how and how.startswith("split:"):
                a = max(1, min(periods - 1, int(how.split(":")[1])))
                for g in sections:
                    put(g, subject(subs[0]), a, [w for w in who_all if w is not None])
                    put(g, subject(subs[1]), periods - a, [w for w in who_all if w is not None])
            elif how == "separate":
                paired = len(who_all) == len(subs)
                for g in sections:
                    for k, name in enumerate(subs):
                        if paired:
                            who = [who_all[k]] if who_all[k] is not None else []
                        else:
                            who = [w for w in who_all if w is not None]
                        put(g, subject(name), periods, who)
            elif how == "choice":
                paired = len(who_all) == len(subs)
                for g in sections:
                    options = []
                    for k, name in enumerate(subs):
                        sub = subject(name)
                        t = who_all[k] if paired and isinstance(who_all[k], Teacher) else None
                        if t:
                            qualify(t, sub, grade)
                        # A subject that is also a common subject of the
                        # section would be taught twice: the choice wins.
                        db.query(SubjectRequirement).filter(
                            SubjectRequirement.class_group_id == g.id, SubjectRequirement.subject_id == sub.id).delete()
                        options.append(ElectiveOption(subject_id=sub.id, preferred_teacher_id=t.id if t else None))
                    db.add(ElectiveBlock(school_id=school_id, class_group_id=g.id,
                                         name=" / ".join(subs)[:60], periods_per_week=periods, options=options))
                    created["blocks"] += 1
            db.flush()
    return created

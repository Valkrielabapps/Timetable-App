"""
Last year's timetable, read whatever way it was drawn.

Schools print the same week in many shapes:

  a grid per section, days down the side and periods across, with a bell-time
  row, break columns (sometimes spelt one letter per row: L / U / N / C / H)
  and the class teacher on a line above (Aditya Birla, BBPS, Keren);
  the same turned round, periods or clock times down and days across, breaks
  as whole rows (the KVS model timetable);
  every section on one sheet, a row each, the day merged over its periods
  (a coordinator's master sheet);
  a grid per teacher with the class in each cell, "VII B", "VI A/SCI", or
  "XI A+B+C" for a group taught together (KV Tezpur);
  and in the cells: "ENG", "ENG-SARA", "Maths (Mrs. Rao)", "Maths" over
  "K. Rao", or a legend code "VI L1" spelt out under the grid.

find_grids() finds every such grid on every sheet and turns it into one
shape - a week of cells per section (a teacher's grid is turned round into
its sections' weeks). read_timetable() then reads that into what the school
needs: each section's plan with its teachers (smart_import._timetables_from
does the name matching), every lesson where it was (to keep the timetable
as it is), the week with its bell times and breaks, the blocks (a language
or elective taught to a whole grade at once), the fixed periods (the class
teacher's period last thing every day), and anything that doesn't add up -
a teacher in two rooms at once, or a teacher's own sheet saying something
the class sheet doesn't.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12}
_GRADE = r"(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I|1[0-2]|[1-9])"
_TIME = re.compile(r"(\d{1,2})\s*[:.]\s*(\d{2})\s*(?:a\.?m\.?|p\.?m\.?)?\s*(?:-|–|—|to)\s*"
                   r"(\d{1,2})\s*[:.]\s*(\d{2})", re.I)
_BREAK = re.compile(r"\b(short\s*break|long\s*break|break|lunch|recess|interval|snacks?|tiffin)\b", re.I)
_BREAK_WORDS = ("break", "lunch", "recess", "interval", "snack", "snacks", "tiffin", "shortbreak", "longbreak")
# A teacher's grid: "VII B", "VI A/SCI", "XI A+B+C", "IX-C (MATHS)".
_TG_CELL = re.compile(rf"^\s*(?:class\s*|std\.?\s*|grade\s*)?{_GRADE}\s*[-–]?\s*([A-H](?:\s*[+,&]\s*[A-H])*)"
                      r"\s*(?:[/(:-]\s*([^()]+?)\s*\)?)?\s*$", re.I)
# "(VI L1- TAM/HIN/SKT)": a code in the cells, spelt out under the grid.
_LEGEND = re.compile(rf"\(?\s*((?:{_GRADE}\s*)?[A-Z]{{1,3}}\s*\d{{1,2}})\s*[-–:=]\s*"
                     r"([A-Za-z][A-Za-z .&]*(?:\s*/\s*[A-Za-z][A-Za-z .&]*)+)\s*\)?")
_POST = re.compile(r"\b(?:PRT|TGT|PGT|PET|PTI|LIB(?:RARIAN)?|HM|VP)\b\s*[:(\-]?\s*([A-Za-z][A-Za-z .&]*?)\s*\d*\s*\)?\s*$",
                   re.I)
_CLASS_TEACHER = re.compile(r"(?:class\s*teacher|teacher'?s?\s*name|tr'?s\s*name|c\.?\s*t\.?)\s*[-–:]*\s*(.+)$", re.I)


# ------------------------------------------------------------ small readers

def day_of(text) -> int | None:
    """"Monday", "MON", "Tues", "Th", "Frid", "Day 2" -> 0..6."""
    t = str(text or "").strip().lower()
    m = re.fullmatch(r"day\s*[-.]?\s*(\d)", t)
    if m and 1 <= int(m.group(1)) <= 7:
        return int(m.group(1)) - 1
    letters = re.sub(r"[^a-z]", "", t)
    if not 2 <= len(letters) <= 9:
        return None
    hits = [i for i, d in enumerate(_DAYS) if d.startswith(letters)]
    return hits[0] if len(hits) == 1 else None


def period_no(text) -> int | None:
    """"3", "3.0", "III", "P3", "PERIOD III", "3rd", "Period 3" -> 3."""
    t = str(text or "").strip().lower()
    if re.fullmatch(r"\d{1,2}\.0", t):
        t = t[:-2]
    t = re.sub(r"^(?:period|prd|pd)\s*[-:.]?\s*", "", t)
    t = re.sub(r"\s*(?:period|prd|pd)\.?$", "", t)
    t = re.sub(r"^p\s*[-.]?\s*(?=\d)", "", t)
    m = re.fullmatch(r"(\d{1,2})\s*(?:st|nd|rd|th)?", t)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 12 else None
    return _ROMAN.get(t.strip(" ."))


def time_of(text) -> str | None:
    """"8:40-9:20", "8.40 to 9.20", "08:40 AM - 09:20 AM" -> "8:40-9:20"."""
    m = _TIME.search(str(text or ""))
    if not m:
        return None
    return f"{int(m.group(1))}:{m.group(2)}-{int(m.group(3))}:{m.group(4)}"


def break_name(text) -> str | None:
    m = _BREAK.search(str(text or ""))
    return re.sub(r"\s+", " ", m.group(1)).title() if m else None


def section_of(text: str) -> tuple[str, str] | None:
    """The last section named in a line: "VII A", "7-A", "Class 7 A", "Grade
    7 - A", "Std VII A", "CLASS – VII - A". A class with no letter ("Class 7")
    is section A."""
    from app.services.smart_import import _SECTION_OF

    found = list(_SECTION_OF.finditer(text or ""))
    if found:
        m = found[-1]
        return m.group(1).upper(), m.group(2).upper()
    m = re.search(rf"\b(?:class|grade|std\.?|standard)\s*[-–:]?\s*{_GRADE}\b(?!\s*[-–]?\s*\d)", text or "", re.I)
    if m:
        return m.group(1).upper(), "A"
    return None


def grade_number(token: str) -> int | None:
    t = (token or "").strip().lower()
    if t.isdigit():
        return int(t)
    return _ROMAN.get(t)


def _cell(row: list[str], c: int) -> str:
    return row[c].strip() if c < len(row) and row[c] else ""


def _legend(rows: list[list[str]]) -> dict[str, str]:
    """{code key: "TAM/HIN/SKT"} from legend lines anywhere on the sheet."""
    from app.services.smart_import import _ck

    out = {}
    for r in rows:
        for v in r:
            if not v or "/" not in v:
                continue
            for m in _LEGEND.finditer(v):
                out[_ck(m.group(1))] = re.sub(r"\s*/\s*", "/", m.group(m.lastindex).strip())
    return out


# ------------------------------------------------------------ finding grids

def _period_header(row: list[str]) -> dict[int, int] | None:
    """{column: period} for a header row of period numbers (or of times
    alone), increasing left to right; None if it isn't one."""
    nums = {c: period_no(v) for c, v in enumerate(row) if c and v}
    nums = {c: n for c, n in nums.items() if n}
    if len(nums) >= 3:
        vals = [nums[c] for c in sorted(nums)]
        if all(b > a for a, b in zip(vals, vals[1:])):
            return nums
    times = [c for c, v in enumerate(row) if c and time_of(v)]
    if len(times) >= 3:
        return {c: i for i, c in enumerate(times, start=1)}
    return None


def _day_header(row: list[str]) -> dict[int, int] | None:
    days = {c: day_of(v) for c, v in enumerate(row) if c and v}
    days = {c: d for c, d in days.items() if d is not None}
    return days if len(set(days.values())) >= 3 else None


def _blank(row: list[str]) -> bool:
    return not any(v.strip() for v in row if v)


def _title_lines(rows, start, end) -> list[str]:
    return [" ".join(v.strip() for v in r if v and v.strip()) for r in rows[start:end] if not _blank(r)]


def _days_down(rows, h, cols) -> dict | None:
    """A grid with period numbers across row h and days down its first column."""
    label = min(cols) - 1
    first, last = min(cols), max(cols)
    bells: dict[int, str] = {}
    header_times = {c: time_of(_cell(rows[h], c)) for c in cols}
    if all(header_times.values()):
        bells = {cols[c]: t for c, t in header_times.items()}
    j = h + 1
    for k in (h - 1, h + 1):
        if 0 <= k < len(rows):
            ts = {c: time_of(_cell(rows[k], c)) for c in cols}
            if sum(1 for t in ts.values() if t) >= 3:
                bells = bells or {cols[c]: t for c, t in ts.items() if t}
                if k == h + 1:
                    j = h + 2
    cells: dict[tuple[int, int], str] = {}
    days: set[int] = set()
    day_rows = []
    while j < len(rows):
        row = rows[j]
        if _blank(row):
            if day_rows:
                break
            j += 1
            continue
        d = day_of(_cell(row, label))
        if d is None:
            break
        days.add(d)
        day_rows.append(row)
        for c, n in cols.items():
            v = _cell(row, c)
            if v:
                cells[(d, n)] = v
        j += 1
    if len(day_rows) < 2 or len(cells) < 4:
        return None
    # Break columns: any column inside the grid that isn't a period.
    width = max(len(r) for r in day_rows + [rows[h]])
    breaks = []
    for c in range(first, max(last + 2, width)):
        if c in cols:
            continue
        vals = [_cell(r, c) for r in day_rows]
        head = _cell(rows[h], c)
        name = break_name(head) or next((break_name(v) for v in vals if v), None)
        if not name and vals and all(len(v) <= 1 for v in vals) and any(vals):
            joined = "".join(vals).lower()
            name = next((w.title() for w in _BREAK_WORDS if joined.startswith(w) or w.startswith(joined)), None)
        if name:
            before = [n for cc, n in cols.items() if cc < c]
            if before:
                breaks.append({"after": max(before), "name": name})
    return {"cells": cells, "days": days, "bells": bells, "breaks": breaks, "end": j,
            "corner": _cell(rows[h], label)}


def _days_across(rows, h, days_at) -> dict | None:
    """Periods (or times) down the side, days across row h, breaks as rows."""
    label = min(days_at) - 1
    cells: dict[tuple[int, int], str] = {}
    bells: dict[int, str] = {}
    breaks = []
    n = 0
    j = h + 1
    while j < len(rows):
        row = rows[j]
        if _blank(row):
            if n:
                break
            j += 1
            continue
        head = _cell(row, label)
        vals = [_cell(row, c) for c in days_at]
        filled = [v for v in vals if v]
        bname = break_name(head) if head and not filled else None
        if not bname and not head and filled and len(set(v.lower() for v in filled)) == 1:
            bname = break_name(filled[0])
        if bname:
            if n:
                breaks.append({"after": n, "name": bname})
            j += 1
            continue
        p = period_no(head)
        t = time_of(head)
        if p is None and t is None:
            if day_of(head) is not None or n:
                break
            j += 1
            continue
        n = p if p else n + 1
        if t:
            bells[n] = t
        for c, d in days_at.items():
            v = _cell(row, c)
            if v:
                cells[(d, n)] = v
        j += 1
    if n < 3 or len(cells) < 4:
        return None
    return {"cells": cells, "days": set(days_at.values()), "bells": bells, "breaks": breaks, "end": j,
            "corner": _cell(rows[h], label)}


def _master(rows, h, days_at) -> list[dict] | None:
    """Every section a row: the day across row h (merged over its periods),
    period numbers under it, the section first in each row."""
    nums = {c: period_no(v) for c, v in enumerate(rows[h + 1]) if v}
    nums = {c: p for c, p in nums.items() if p}
    if len(nums) < 3 or len(nums) <= len(days_at):
        return None
    label = min(min(days_at), min(nums)) - 1
    col_at: dict[int, tuple[int, int]] = {}
    day = None
    for c in range(min(nums), max(nums) + 1):
        d = day_of(_cell(rows[h], c))
        if d is not None:
            day = d
        if c in nums and day is not None:
            col_at[c] = (day, nums[c])
    out = []
    j = h + 2
    while j < len(rows):
        row = rows[j]
        if _blank(row):
            if out:
                break
            j += 1
            continue
        sec = _cell(row, label)
        cells = {col_at[c]: _cell(row, c) for c in col_at if _cell(row, c)}
        if not section_of(sec) or len(cells) < 4:
            if out:
                break
            j += 1
            continue
        out.append({"cells": cells, "days": {d for d, _ in cells}, "bells": {}, "breaks": [], "end": j + 1,
                    "corner": "", "title": [sec]})
        j += 1
    return out or None


def find_grids(sheets: list[tuple[str, list[list[str]]]]) -> list[dict]:
    """Every week drawn on every sheet, as
    {"title": [lines above it], "sheet", "cells": {(day, period): text},
     "days", "bells": {period: "8:40-9:20"}, "breaks": [{"after", "name"}],
     "legend": {code key: options}}."""
    grids = []
    for title, rows in sheets:
        rows = [[("" if v is None else str(v)) for v in r] for r in rows]
        legend = _legend(rows)
        last_end = 0
        i = 0
        while i < len(rows):
            row = rows[i]
            found = None
            days_at = _day_header(row)
            if days_at and i + 1 < len(rows):
                masters = _master(rows, i, days_at)
                if masters:
                    above = _title_lines(rows, last_end, i)
                    for g in masters:
                        g.update(title=above + g["title"], sheet=title, legend=legend)
                        grids.append(g)
                    last_end = i = masters[-1]["end"]
                    continue
                found = _days_across(rows, i, days_at)
            if found is None and not days_at:
                cols = _period_header(row)
                if cols:
                    found = _days_down(rows, i, cols)
            if found:
                found.update(title=_title_lines(rows, last_end, i) + ([found["corner"]] if found["corner"] else []),
                             sheet=title, legend=legend)
                grids.append(found)
                last_end = i = found["end"]
                continue
            i += 1
    return grids


# ------------------------------------------------------- what each grid is

def _is_teacher_grid(g: dict) -> bool:
    vals = [v for v in g["cells"].values() if v]
    hits = sum(1 for v in vals if _TG_CELL.match(v))
    return bool(vals) and hits >= 0.6 * len(vals)


def _class_teacher(lines: list[str]) -> str:
    from app.services.smart_import import _SECTION_OF, _TITLED

    for ln in lines:
        m = _CLASS_TEACHER.search(ln)
        if not m:
            continue
        rest = m.group(1)
        t = _TITLED.search(rest)
        name = t.group(1) if t else rest
        name = _SECTION_OF.sub(" ", name)
        name = re.sub(r"\s+", " ", re.sub(r"[-–:]+", " ", name)).strip(" .-:")
        if name and len(name) <= 40:
            return name
    return ""


def _grid_section(g: dict) -> tuple[str, str] | None:
    for ln in reversed(g["title"]):
        if _LEGEND.search(ln) and "/" in ln:
            continue
        s = section_of(ln)
        if s:
            return s
    return section_of(g.get("sheet") or "")


def _teacher_of(lines: list[str], sheet: str) -> tuple[str, str]:
    """(name as written, subject as written) from a teacher grid's title:
    "Mrs. Kavitha Rao", "KAVITHA RAO (TGT English)", "TGT: MATHS 2"."""
    from app.services.smart_import import _TITLE

    corner = re.compile(r"^[\W_]*(?:(?:days?|periods?|time|class)[\W_]*)+$", re.I)
    text = next((ln for ln in reversed(lines) if ln.strip() and not corner.match(ln)), "") or sheet
    subject = ""
    m = _POST.search(text)
    if m:
        subject = m.group(1).strip()
    name = re.sub(r"\(.*?\)", "", text).strip()
    if not name or re.match(r"^(?:PRT|TGT|PGT|PET|PTI|LIB|HM|VP)\b", name, re.I):
        name = text.strip()  # titled only by post: that is all the file says
    else:
        name = _TITLE.sub("", name).strip(" .:-")
    return name, subject


def _sections_from_teacher_grids(grids: list[dict], staff: list[dict] | None) -> dict:
    """Each section's week, put together from the teachers' grids:
    {(grade, letter): {(day, period): [(subject, teacher), ...]}}."""
    from app.services.smart_import import _lk

    staff_subjects = {}
    for p in staff or []:
        k = _lk(p.get("name") or "")
        if k and p.get("subjects"):
            staff_subjects[k] = p["subjects"][0]
    out: dict = defaultdict(lambda: defaultdict(list))
    for g in grids:
        name, title_subject = _teacher_of(g["title"], g.get("sheet") or "")
        guess = title_subject
        if not guess:
            k = _lk(name)
            guess = next((s for n, s in staff_subjects.items() if n == k or (len(k) >= 4 and n.startswith(k))), "")
        for (d, n), v in g["cells"].items():
            m = _TG_CELL.match(v)
            if not m:
                continue
            grade = m.group(1).upper()
            subject = (m.group(3) or "").strip() or guess or "?"
            for letter in re.split(r"\s*[+,&]\s*", m.group(2).upper()):
                out[(grade, letter)][(d, n)].append((subject, name))
    return out


def _cell_from_entries(entries: list[tuple[str, str]]) -> tuple[str, list[str]]:
    subjects = list(dict.fromkeys(s for s, _ in entries))
    teachers = list(dict.fromkeys(t for _, t in entries if t))
    return "/".join(subjects), teachers


# --------------------------------------------------------------- the reading

def read_timetable(sheets: list[tuple[str, list[list[str]]]], staff: list[dict] | None = None) -> dict | None:
    """Everything last year's timetable says (see the module docstring), or
    None if the file isn't a timetable:

    {"tables": plan tables as smart_import.plan_tables gives them,
     "sections": [{"label", "class_teacher", "lessons": [{"day", "period", "subject", "teachers"}]}],
     "week": {"days", "periods", "bell_times": {period: "8:40-9:20"}, "breaks": [{"after", "name"}]},
     "blocks": [{"name", "grade", "sections", "periods", "options": [{"subject", "teacher"}], "slots"}],
     "fixed": [{"subject", "grades", "period", "days"}],
     "checks": [what doesn't add up], "view": "class" | "teacher"}
    """
    from app.services.smart_import import _ck, _timetables_from, _timetable_blocks

    grids = find_grids(sheets)
    class_grids = [g for g in grids if not _is_teacher_grid(g)]
    teacher_grids = [g for g in grids if _is_teacher_grid(g)]

    blocks: list[dict] = []
    seen: set = set()
    for g in class_grids:
        sec = _grid_section(g)
        if not sec or sec in seen:
            continue
        seen.add(sec)
        legend = g.get("legend") or {}
        cells = {k: legend.get(_ck(v), v) for k, v in g["cells"].items()}
        blocks.append({"section": sec, "class_teacher": _class_teacher(g["title"]), "cells": cells,
                       "days": set(g["days"]), "bells": g["bells"], "breaks": g["breaks"], "sure": True})
    view = "class"
    from_teachers = _sections_from_teacher_grids(teacher_grids, staff) if teacher_grids else {}
    if not blocks and from_teachers:
        view = "teacher"
        for sec, slots in sorted(from_teachers.items()):
            blocks.append({"section": sec, "class_teacher": "", "sure": True, "bells": {}, "breaks": [],
                           "cells": {k: _cell_from_entries(v) for k, v in slots.items()},
                           "days": {d for d, _ in slots}})
    # The older reader (Keren's own layout) when it finds more sections.
    old = [b for _, rows in sheets for b in _timetable_blocks(rows)]
    if len({b["section"] for b in old}) > len(blocks):
        blocks, view = old, "class"
    if not blocks:
        return None
    tables = _timetables_from(blocks, staff)
    if not tables or not any(t.get("lessons") for t in tables):
        return None

    sections = [{"label": t["label"], "class_teacher": t.get("class_teacher") or "",
                 "lessons": t.get("lessons") or []} for t in tables]
    week = dict(tables[0].get("week") or {})
    blocks = find_blocks(sections)
    out = {"tables": tables, "sections": sections, "week": week, "view": view,
           "blocks": blocks, "fixed": find_fixed(sections, week),
           "same_names": same_names(sections, blocks, staff)}
    asked = {n["name"] for n in out["same_names"]}
    out["checks"] = clashes(sections, out["blocks"], asked) + (
        cross_check(sections, from_teachers, staff) if from_teachers and view == "class" else [])
    for t in tables:
        t["block_items"] = _plain_items(t, out["blocks"])
    return out


def same_names(sections: list[dict], blocks: list[dict], staff: list[dict] | None = None) -> list[dict]:
    """One name that may be two people ("Mythili" for Mythili Nair and
    Mythili Rajan): the name is down for two classes at once. Their lessons
    are shared out between as few people as keep everyone in one place at a
    time, each subject kept with one person where it can be, and each named
    by what they teach: "Mythili (Computer Science)", "Mythili (Music)".
    Nothing is changed here - it may also be one teacher taking two classes
    together, so the school is asked. [{"name", "people": [label, ...],
    "who": {"subject concept|section label": label}, "example"}]"""
    from app.services.smart_import import _CONCEPT_NAMES, _concept

    in_block = {(lab, d, p) for b in blocks for lab in b["sections"] for d, p in b["slots"]}
    at: dict[tuple, set] = defaultdict(set)
    for s in sections:
        for l in s["lessons"]:
            if (s["label"], l["day"], l["period"]) in in_block:
                continue
            for t in l.get("teachers") or []:
                at[(t, l["day"], l["period"])].add(s["label"])
    clashing = sorted({t for (t, _, _), labs in at.items() if len(labs) > 1})
    # A name that is exactly one person on the staff list is one person: the
    # clash is two classes taken together, or a slip in last year's timetable,
    # and is reported as that, not offered as two teachers.
    on_list = defaultdict(int)
    for p in staff or []:
        on_list[re.sub(r"\s+", " ", (p.get("name") or "")).strip().lower()] += 1
    clashing = [t for t in clashing if on_list.get(t.lower(), 0) != 1]
    notes = []
    for name in clashing:
        units: dict[tuple, set] = defaultdict(set)   # (subject, section) -> slots
        nice: dict[str, str] = {}
        for s in sections:
            for l in s["lessons"]:
                if name in (l.get("teachers") or []) and (s["label"], l["day"], l["period"]) not in in_block:
                    c = _concept(l["subject"])
                    nice.setdefault(c, _CONCEPT_NAMES.get(c) or l["subject"].title())
                    units[(c, s["label"])].add((l["day"], l["period"]))
        colour: dict[tuple, int] = {}
        by_subject: dict[str, list[int]] = defaultdict(list)
        for u in sorted(units, key=lambda u: (-len(units[u]), u)):
            taken = {colour[v] for v in colour if units[v] & units[u]}
            prefer = [c for c in by_subject[u[0]] if c not in taken]
            c = prefer[0] if prefer else next(i for i in range(len(units) + 1) if i not in taken)
            colour[u] = c
            if c not in by_subject[u[0]]:
                by_subject[u[0]].append(c)
        people = sorted(set(colour.values()))
        if len(people) < 2:
            continue
        labels = {}
        for c in people:
            subs = sorted({nice[u[0]] for u, cc in colour.items() if cc == c})
            label = f"{name} ({', '.join(subs[:2])}{'…' if len(subs) > 2 else ''})"
            k = 2
            base = label
            while label in labels.values():
                # "Maivizhi 2 (Physical Education)": the second person teaching it.
                label = base.replace(f"{name} (", f"{name} {k} (", 1)
                k += 1
            labels[c] = label
        example = next(((t, d, p, sorted(labs)) for (t, d, p), labs in sorted(at.items(), key=lambda x: (x[0][1], x[0][2]))
                        if t == name and len(labs) > 1), None)
        notes.append({"name": name, "people": [labels[c] for c in people],
                      "who": {f"{u[0]}|{u[1]}": labels[c] for u, c in colour.items()},
                      "example": f"{' and '.join(example[3][:3])} on {_DAY_NAMES[example[1]]}, period {example[2]}"
                      if example else ""})
    return notes


def _plain_items(table: dict, blocks: list[dict]) -> list[tuple[str, str, str]]:
    """A section's plan lines without the periods its blocks take."""
    taken = {(lab, d, p) for b in blocks for lab in b["sections"] for d, p in b["slots"]}
    count: Counter = Counter()
    who: dict[str, Counter] = defaultdict(Counter)
    for l in table.get("lessons") or []:
        if (table["label"], l["day"], l["period"]) in taken:
            continue
        count[l["subject"]] += 1
        who[l["subject"]].update(l.get("teachers") or [])
    return [(code, str(n), "/".join(t for t, _ in who[code].most_common())) for code, n in count.items()]


# ------------------------------------------------------ blocks, fixed, checks

def _grade_of_label(label: str) -> str:
    s = section_of(label)
    return s[0] if s else label


def _blockish(code: str) -> bool:
    from app.services.smart_import import _concept

    if "/" in code:
        return True
    return _concept(code) in ("lang2", "lang3") or bool(re.search(r"\belect", code, re.I))


def _block_name(code: str, grade: str) -> str:
    from app.services.smart_import import _CONCEPT_NAMES, _concept

    n = grade_number(grade)
    g = f"Grade {n}" if n else grade
    c = _concept(code)
    if c in ("lang2", "lang3"):
        return f"{g} {_CONCEPT_NAMES[c]}"
    return f"{g} {code}"


def _same_block_codes(codes: set[str]) -> dict[str, str]:
    """code -> the code standing for its block: the fullest spelling among
    codes whose subjects are one within the other ("Bio/M" in "BIOLOGY/
    MATHEMATICS"; "TAMIL/HINDI" and "HINDI/SANS" stay two)."""
    from app.services.smart_import import _SUBJECT_ALIASES, _concept, _key

    def subjects(code):
        parts = [x for x in re.split(r"\s*/\s*", code) if x.strip()]
        known = {_concept(x) for x in parts if len(_key(x)) > 1 or _key(x) in _SUBJECT_ALIASES}
        return frozenset(known)

    sig = {c: subjects(c) for c in codes}
    parent = {c: c for c in codes}

    def find(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    ordered = sorted(codes)
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if sig[a] and sig[b] and (sig[a] <= sig[b] or sig[b] <= sig[a]):
                parent[find(a)] = find(b)
    groups: dict[str, list] = defaultdict(list)
    for c in codes:
        groups[find(c)].append(c)
    out = {}
    for members in groups.values():
        best = max(members, key=lambda c: (len(sig[c]), len(c)))
        for c in members:
            out[c] = best
    return out


def find_blocks(sections: list[dict]) -> list[dict]:
    """A language or elective taught at once to a whole grade: the same block
    code ("2LN", "TAM/HIN", a legend's options, "ELECTIVES") at the same
    periods in each of the grade's sections that have it."""
    from app.services.smart_import import _ck

    # One block spelt several ways ("Bio/M", "BIOLOGY/MATHEMATICS"): codes
    # whose subjects are one within the other are one block.
    codes = {l["subject"] for s in sections for l in s["lessons"] if _blockish(l["subject"])}
    same = _same_block_codes(codes)
    by: dict[tuple, dict] = {}
    for s in sections:
        grade = _grade_of_label(s["label"])
        per: dict[str, list] = defaultdict(list)
        for l in s["lessons"]:
            if _blockish(l["subject"]):
                per[same[l["subject"]]].append(l)
        for key, ls in per.items():
            slots = tuple(sorted((l["day"], l["period"]) for l in ls))
            rec = by.setdefault((grade, key, slots), {"code": key, "grade": grade, "sections": [],
                                                      "slots": slots, "teachers": []})
            rec["sections"].append(s["label"])
            for l in ls:
                rec["teachers"] += [t for t in l.get("teachers") or [] if t not in rec["teachers"]]
    out = []
    for (grade, key, slots), rec in by.items():
        subjects = [x.strip() for x in rec["code"].split("/") if x.strip()] if "/" in rec["code"] else [rec["code"]]
        if len(subjects) > 1 and len(rec["teachers"]) == len(subjects):
            options = [{"subject": s, "teacher": t} for s, t in zip(subjects, rec["teachers"])]
        elif len(subjects) > 1:
            options = [{"subject": s, "teacher": ""} for s in subjects]
        else:
            options = [{"subject": subjects[0], "teacher": t} for t in rec["teachers"]] or [
                {"subject": subjects[0], "teacher": ""}]
        out.append({"name": _block_name(rec["code"], grade), "code": rec["code"], "grade": grade,
                    "sections": rec["sections"], "periods": len(slots), "slots": [list(x) for x in slots],
                    "options": options})
    return out + _taught_together(sections)


def _taught_together(sections: list[dict]) -> list[dict]:
    """The same teacher with the same subject in two or more sections of a
    grade at the same time: one lesson for them all - an elective group
    ("BIO-NIRMA" in XI A and XI B), or two sections combined."""
    from app.services.smart_import import _ck

    at: dict[tuple, list] = defaultdict(list)
    for s in sections:
        grade = _grade_of_label(s["label"])
        for l in s["lessons"]:
            if _blockish(l["subject"]):
                continue
            for t in l.get("teachers") or []:
                at[(grade, _ck(l["subject"]), t, l["day"], l["period"])].append((s["label"], l["subject"]))
    # Each subject and teacher's own slots first; options held at exactly
    # the same times are one block.
    each: dict[tuple, dict] = {}
    for (grade, key, t, d, p), places in at.items():
        labels = tuple(sorted(dict.fromkeys(lab for lab, _ in places)))
        if len(labels) < 2:
            continue
        e = each.setdefault((grade, labels, key, t), {"slots": set(), "subject": places[0][1], "teacher": t})
        e["slots"].add((d, p))
    groups: dict[tuple, dict] = {}
    for (grade, labels, key, t), e in each.items():
        g = groups.setdefault((grade, labels, tuple(sorted(e["slots"]))),
                              {"grade": grade, "sections": list(labels), "slots": e["slots"], "options": {}})
        g["options"][(key, t)] = {"subject": e["subject"], "teacher": t}
    out = []
    for g in groups.values():
        subjects = list(dict.fromkeys(o["subject"] for o in g["options"].values()))
        out.append({"name": _block_name("/".join(subjects), g["grade"]), "code": "/".join(subjects),
                    "grade": g["grade"], "sections": g["sections"], "periods": len(g["slots"]),
                    "slots": [list(x) for x in sorted(g["slots"])], "options": list(g["options"].values()),
                    "together": True})
    return out


def find_fixed(sections: list[dict], week: dict) -> list[dict]:
    """A subject held at one period and nowhere else, the same in every
    section of a grade: every day (the class teacher's period last thing), or
    on the same two or more days in two or more sections."""
    from app.services.smart_import import _ck

    days_n = len(week.get("days") or []) or 5
    by_grade: dict[str, list] = defaultdict(list)
    for s in sections:
        by_grade[_grade_of_label(s["label"])].append(s)
    found: dict[tuple, dict] = {}
    for grade, secs in by_grade.items():
        per_sec = []
        for s in secs:
            m: dict[str, list] = defaultdict(list)
            for l in s["lessons"]:
                if not _blockish(l["subject"]):
                    m[_ck(l["subject"])].append((l["day"], l["period"], l["subject"]))
            per_sec.append(m)
        common = set(per_sec[0]).intersection(*per_sec[1:]) if per_sec else set()
        for key in common:
            shapes = []
            for m in per_sec:
                periods = {p for _, p, _ in m[key]}
                days = sorted({d for d, _, _ in m[key]})
                shapes.append((tuple(periods), tuple(days), len(m[key])))
            if len(set(shapes)) != 1:
                continue
            periods, days, count = shapes[0]
            if len(periods) != 1 or count != len(days):
                continue
            # Every day, or the same three days or more in two sections or
            # more: twice a week at one period is as likely to be chance.
            every_day = len(days) >= days_n
            if not every_day and not (len(secs) >= 2 and len(days) >= 3):
                continue
            name = per_sec[0][key][0][2]
            rec = found.setdefault((key, periods[0], None if every_day else days),
                                   {"subject": name, "grades": [], "period": periods[0],
                                    "days": None if every_day else list(days)})
            rec["grades"].append(grade)
    return list(found.values())


_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def clashes(sections: list[dict], blocks: list[dict], skip=()) -> list[str]:
    """A teacher down for two sections at once, unless it's one block taught
    to both together: one line per teacher, with how often and when first.
    `skip`: names asked about already (one name, maybe two people)."""
    from app.services.smart_import import _ck

    where: dict[tuple, list] = defaultdict(list)
    for s in sections:
        for l in s["lessons"]:
            for t in l.get("teachers") or []:
                where[(t, l["day"], l["period"])].append((s["label"], _ck(l["subject"])))
    per: dict[str, list] = defaultdict(list)
    for (t, d, p), places in sorted(where.items(), key=lambda x: (x[0][1], x[0][2], x[0][0])):
        labels = list(dict.fromkeys(lab for lab, _ in places))
        codes = {c for _, c in places}
        if t in skip:
            continue
        if len(labels) > 1 and not (len(codes) == 1 and _blockish(places[0][1]) or len(codes) == 1 and
                                    any(set(labels) <= set(b["sections"]) for b in blocks)):
            per[t].append(f"{' and '.join(labels)} ({_DAY_NAMES[d]}, period {p})")
    out = []
    for t, cases in sorted(per.items(), key=lambda x: -len(x[1])):
        more = f", and {len(cases) - 1} more time{'s' if len(cases) > 2 else ''}" if len(cases) > 1 else ""
        out.append(f"{t} is down for two classes at once: {cases[0]}{more}. Taught together, or a slip "
                   "in last year's timetable?")
    if len(out) > 8:
        out = out[:8] + [f"…and {len(out) - 8} more teachers down for two classes at once."]
    return out


def cross_check(sections: list[dict], from_teachers: dict, staff: list[dict] | None) -> list[str]:
    """The class sheets against the teachers' own: each teacher's lesson
    should be in that section's week at that time, with that teacher."""
    from app.services.smart_import import _lk

    by_label = {}
    for s in sections:
        sec = section_of(s["label"])
        if sec:
            g = grade_number(sec[0])
            by_label[(g, sec[1])] = s
    out = []
    for (grade, letter), slots in from_teachers.items():
        s = by_label.get((grade_number(grade), letter))
        if not s:
            continue
        lessons = {(l["day"], l["period"]): l for l in s["lessons"]}
        for (d, p), entries in sorted(slots.items()):
            l = lessons.get((d, p))
            for _, teacher in entries:
                k = _lk(teacher)
                names = [_lk(t) for t in (l.get("teachers") or [])] if l else []
                if not l or (names and not any(n.startswith(k[:4]) or k.startswith(n[:4]) for n in names if n)):
                    out.append(f"{teacher}'s own timetable has {s['label']} on {_DAY_NAMES[d]}, period {p}, "
                               f"but the class timetable has {('“' + l['subject'] + '”') if l else 'nothing'} then.")
    if len(out) > 6:
        out = out[:6] + [f"…and {len(out) - 6} more differences between the class and teacher timetables."]
    return out

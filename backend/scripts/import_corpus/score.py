"""
Score the importers against the test corpus.

    python scripts/import_corpus/score.py                         # school-imports/generated
    python scripts/import_corpus/score.py --save before.json      # keep this run
    python scripts/import_corpus/score.py --compare before.json   # what changed since

Each case is run through the same code the website uses - smart_rows for a
subject or staff list, plan_tables for last year's timetable - and what comes
back is checked against the truth the case was generated from:

  Subjects   every subject found once (a short form found counts; two rows for
             one subject is a duplicate, a row that isn't a subject is extra),
             and named well (a full name, not "SST").
  Teachers   every teacher found, with a clean full name when the file gives
             one ("Kavitha Rao", not "Mrs. Kavitha Rao (TGT)"); their
             subjects; their grades, where the file says.
  Timetable  every section found; its weekly plan - each subject with the right
             number of periods (a language group or elective block counts as
             one line); who teaches each, where the cells say; the week's days
             and periods.
  Rules      each note's facts read back - only with --rules, which needs the
             AI key (the reading is done by Claude).

A case's score is 0-100. A file the importer refuses scores 0, with why.
The overall score per area is the mean of its cases'.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[2]))  # backend/, for app.services

from school import SUBJECTS  # noqa: E402

TITLES = {"mr", "mrs", "ms", "miss", "dr", "smt", "shri", "sri", "sh", "fr", "sr", "prof", "sis", "bro", "md"}
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11,
         "xii": 12}
# Names the app's own catalogue uses for a subject, beyond the school's short forms.
EXTRA_NAMES = {
    "Social Science": ["Social Studies", "Social", "SST", "Soc Sci", "SS"],
    "Mathematics": ["Maths", "Math"],
    "Physical Education": ["PE", "Games", "Sports", "PET", "Physical Training"],
    "Computer Science": ["Computer", "Computers", "Computer Studies", "IT", "Comp"],
    "Art": ["Arts", "Art and Craft", "Fine Arts", "Drawing"],
    "Class Teacher Period": ["Class Teacher", "CT", "C.T.", "Class Teacher Period"],
    "SUPW": ["Work Education", "Work Experience"],
    "General Knowledge": ["GK"],
    "Value Education": ["Moral Science", "Moral Education", "Value Ed"],
    "EVS": ["Environmental Studies", "Environmental Science"],
    "Library": ["Lib", "Library Period", "Reading"],
    # The app's clean name for the language blocks (smart_import._CONCEPT_NAMES).
    "Second Language": ["2nd Language"],
    "Third Language": ["3rd Language"],
}


def norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def norm_person(s: str) -> str:
    words = norm(s).split()
    while words and words[0] in TITLES:
        words = words[1:]
    return " ".join(words)


# ------------------------------------------------------------------ resolving

class Resolver:
    """Turns what an importer returned back into truth: which subject, block,
    teacher or section a string means, given how this file wrote them."""

    def __init__(self, truth: dict, expected: dict):
        self.truth = truth
        self.expected = expected
        self.subject_names: dict[str, set[str]] = defaultdict(set)
        for subj, forms in SUBJECTS.items():
            self.subject_names[subj] |= {norm(subj), *map(norm, forms)}
        for subj, forms in EXTRA_NAMES.items():
            self.subject_names[subj] |= set(map(norm, forms))
        for subj, forms in expected["written"].get("subjects", {}).items():
            self.subject_names[subj] |= set(map(norm, forms))
        self.teacher_by_name = {norm_person(t["name"]): t["name"] for t in truth["teachers"]}
        self.teacher_written: dict[str, set[str]] = defaultdict(set)
        for name, forms in expected["written"].get("teachers", {}).items():
            self.teacher_written[name] |= {norm_person(f) for f in forms}
        self.legend = {norm(v): k for k, v in (expected.get("options", {}).get("legend") or {}).items()}

    def subject(self, text: str) -> str | None:
        n = norm(text)
        if not n:
            return None
        hits = [s for s, names in self.subject_names.items() if n in names]
        if len(hits) == 1:
            return hits[0]
        return hits[0] if hits and norm(hits[0]) == n else (hits[0] if hits else None)

    def block_or_subject(self, text: str, grade: int | None) -> str | None:
        """A plan line's subject: a block name when it names one (2LN, the
        options 'Maths/Biology', a legend code), else a subject."""
        blocks = [b for b in self.truth["blocks"] if grade is None or b["grade"] == grade]
        n = norm(text)
        if n in self.legend:
            return self.legend[n]
        subj = self.subject(text)
        for b in blocks:
            kind = "Second Language" if "Second Language" in b["name"] else \
                "Third Language" if "Third Language" in b["name"] else None
            if kind and subj == kind:
                return b["name"]
        parts = [p for p in re.split(r"[/,]", text) if p.strip()]
        if len(parts) > 1:
            subs = {self.subject(p) for p in parts}
            for b in blocks:
                if subs and subs <= {g["subject"] for g in b["groups"]}:
                    return b["name"]
        return subj

    def teacher(self, text: str) -> tuple[str | None, str]:
        """(truth teacher, 'exact' | 'recognisable' | 'wrong'). Exact is the
        full name, clean; recognisable is the way the file wrote them, a
        unique start of their name, or their name with clutter around it."""
        n = norm_person(text)
        if not n:
            return None, "wrong"
        if n in self.teacher_by_name:
            return self.teacher_by_name[n], "exact"
        written = [t for t, forms in self.teacher_written.items() if n in forms]
        if len(written) == 1:
            return written[0], "recognisable"
        inside = [full for k, full in self.teacher_by_name.items() if k and (k in n or n.startswith(k.split()[0]))]
        if len(inside) == 1:
            return inside[0], "recognisable"
        starts = [full for k, full in self.teacher_by_name.items() if len(n) >= 4 and k.startswith(n)]
        if len(starts) == 1:
            return starts[0], "recognisable"
        return None, "wrong"

    def section(self, label: str) -> str | None:
        words = norm(label).split()
        grade, letter = None, None
        for i, w in enumerate(words):
            m = re.fullmatch(r"(\d{1,2})([a-h])?", w)
            if m and 1 <= int(m.group(1)) <= 12:
                grade = int(m.group(1))
                letter = m.group(2) or letter
            elif w in ROMAN and grade is None and (i + 1 < len(words) or len(words) > 1):
                grade = ROMAN[w]
            elif len(w) == 1 and w in "abcdefgh" and grade is not None:
                letter = w
            else:
                m = re.fullmatch(r"(x{0,1}i{1,3}|iv|v|vi{1,3}|ix|x|xi{1,2})([a-h])", w)
                if m and m.group(1) in ROMAN:
                    grade, letter = ROMAN[m.group(1)], m.group(2)
        if grade is None:
            return None
        cand = f"{grade}{(letter or 'A').upper()}"
        return cand if cand in self.truth["sections"] else None


def _f1(tp: float, fp: float, fn: float) -> float:
    if tp == 0:
        return 0.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return 2 * p * r / (p + r)


def _split_list(text: str) -> list[str]:
    parts = re.split(r"\s*(?:;|,|&|\band\b|/)\s*", text or "")
    return [re.sub(r"\s*-\s*\d+\s*$", "", p).strip() for p in parts if p.strip()]


def _grades(text: str) -> set[int]:
    out: set[int] = set()
    for a, b in re.findall(r"(\d{1,2})\s*(?:to|-)\s*(\d{1,2})", text or ""):
        out |= set(range(int(a), int(b) + 1))
    rest = re.sub(r"(\d{1,2})\s*(?:to|-)\s*(\d{1,2})", " ", text or "")
    out |= {int(n) for n in re.findall(r"\b(\d{1,2})\b", rest) if 1 <= int(n) <= 12}
    return out


# -------------------------------------------------------------------- scoring

def score_subjects(path: Path, res: Resolver, ai) -> dict:
    from app.services.smart_import import smart_rows
    rows, info = smart_rows("subjects", path.name, path.read_bytes(), ai=ai)
    truth = set(res.expected["written"]["subjects"])
    seen: dict[str, int] = defaultdict(int)
    extra, well = [], 0
    for r in rows:
        key = res.subject(r.get("name", ""))
        if key in truth:
            seen[key] += 1
            if len(r["name"].replace(".", "").replace(" ", "")) > 4:
                well += 1
        else:
            extra.append(r.get("name"))
    dup = sum(n - 1 for n in seen.values())
    tp = len(seen)
    score = _f1(tp, len(extra) + dup, len(truth - set(seen)))
    return {"score": round(100 * score), "found": f"{tp}/{len(truth)}", "duplicates": dup, "extra": extra[:6],
            "named_well": f"{well}/{max(1, sum(seen.values()))}",
            "missing": sorted(truth - set(seen))[:6]}


def score_teachers(path: Path, res: Resolver, ai) -> dict:
    from app.services.smart_import import smart_rows
    rows, info = smart_rows("teachers", path.name, path.read_bytes(), ai=ai)
    truth_names = set(res.expected["written"].get("teachers", {}))
    by_name = {t["name"]: t for t in res.truth["teachers"]}
    found: dict[str, str] = {}
    extra, messy = [], []
    subj_ok = subj_n = grade_ok = grade_n = 0
    for r in rows:
        who, how = res.teacher(r.get("name", ""))
        if who not in truth_names:
            extra.append(r.get("name"))
            continue
        if who in found:
            extra.append(r.get("name") + " (again)")
            continue
        found[who] = how
        if how != "exact":
            messy.append(r.get("name"))
        t = by_name[who]
        got = {res.subject(s) for s in _split_list(r.get("qualified_subjects", ""))} - {None}
        subj_n += 1
        subj_ok += got == set(t["subjects"])
        if res.expected["layout"] in ("free_text", "by_department", "allotment"):
            grade_n += 1
            grade_ok += _grades(r.get("qualified_grades", "")) == set(t["grades"]) or (
                res.expected["layout"] == "allotment" and not r.get("qualified_grades"))
    tp = sum(1.0 if h == "exact" else 0.6 for h in found.values())
    names = _f1(tp, len(extra), len(truth_names - set(found)))
    parts = [(0.6, names), (0.3, subj_ok / subj_n if subj_n else 0.0)]
    if grade_n:
        parts.append((0.1, grade_ok / grade_n))
    score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    return {"score": round(100 * score), "found": f"{len(found)}/{len(truth_names)}",
            "clean_names": f"{sum(1 for h in found.values() if h == 'exact')}/{len(found)}",
            "subjects_right": f"{subj_ok}/{subj_n}", "grades_right": f"{grade_ok}/{grade_n}" if grade_n else "-",
            "extra": extra[:6], "messy_names": messy[:6], "missing": sorted(truth_names - set(found))[:6]}


def _truth_plan(truth: dict, section: str) -> dict:
    """section's weekly plan: {subject or block name: (periods, {teachers})}."""
    out: dict[str, tuple[int, set]] = {}
    for p in truth["plan"]:
        if p["section"] == section:
            out[p["subject"]] = (p["periods"], {p["teacher"]} if p["teacher"] else set())
    for b in truth["blocks"]:
        if section in b["sections"]:
            out[b["name"]] = (b["periods"], {g["teacher"] for g in b["groups"]})
    return out


def score_timetable(path: Path, res: Resolver, staff: list[dict] | None) -> dict:
    from app.services.smart_import import plan_tables, read_sheets
    content = path.read_bytes()
    how, tables = plan_tables(read_sheets(path.name, content), staff,
                              timetable_sheets=read_sheets(path.name, content, "timetable"))
    shown = res.expected["shows"]["sections"]
    teachers_shown = res.expected["layout"] == "keren" or res.expected.get("options", {}).get("teacher_in_cell") not in (None, "none")
    got_sections: dict[str, dict] = {}
    unplaced = []
    for tb in tables:
        sec = res.section(tb.get("label", ""))
        if sec and sec in shown and sec not in got_sections:
            got_sections[sec] = tb
        else:
            unplaced.append(tb.get("label"))
    lines_right = lines_found = lines_total = extra_lines = 0
    t_exact = t_recog = t_total = 0
    wrong = []
    for sec in shown:
        want = _truth_plan(res.truth, sec)
        lines_total += len(want)
        tb = got_sections.get(sec)
        if not tb:
            continue
        grade = int(sec[:-1])
        got: dict[str, list] = defaultdict(lambda: [0, []])
        for item in tb.get("items", []):
            subj, count, teacher = (list(item) + ["", "", ""])[:3]
            key = res.block_or_subject(str(subj), grade)
            try:
                n = int(float(count))
            except (TypeError, ValueError):
                n = 0
            if key is None:
                extra_lines += 1
                continue
            got[key][0] += n
            if teacher:
                got[key][1].append(str(teacher))
        for key, (periods, tset) in want.items():
            if key not in got:
                continue
            lines_found += 1
            if got[key][0] == periods:
                lines_right += 1
            elif len(wrong) < 6:
                wrong.append(f"{sec} {key}: {got[key][0]} not {periods}")
            if teachers_shown and tset:
                t_total += 1
                verdicts = [res.teacher(t) for t in got[key][1]]
                if any(w in tset and h == "exact" for w, h in verdicts):
                    t_exact += 1
                elif any(w in tset for w, h in verdicts):
                    t_recog += 1
        extra_lines += sum(1 for k in got if k not in want)
    week = None
    weeks = [tb.get("week") for tb in tables if tb.get("week")]
    if weeks:
        w = weeks[0]
        week = (len(w.get("days", [])) == len(res.truth["days"])) and w.get("periods") == res.truth["periods_per_day"]
    sections_part = len(got_sections) / len(shown) if shown else 0
    lines_part = lines_right / max(lines_total, lines_right + extra_lines) if lines_total else 0
    parts = [(0.25, sections_part), (0.5, lines_part)]
    if teachers_shown and t_total:
        parts.append((0.25, (t_exact + 0.5 * t_recog) / t_total))
    score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
    return {"score": round(100 * score), "sections": f"{len(got_sections)}/{len(shown)}",
            "plan_lines_right": f"{lines_right}/{lines_total}", "plan_lines_found": f"{lines_found}/{lines_total}",
            "extra_lines": extra_lines,
            "teachers": f"{t_exact} exact + {t_recog} recognisable of {t_total}" if teachers_shown else "-",
            "week_right": week, "wrong_counts": wrong, "unplaced_tables": unplaced[:4]}


def _clock(text: str) -> str:
    """"8:40-9:20", "8.40 to 9.20", "08:40 - 09:20" -> "8:40-9:20"."""
    nums = re.findall(r"(\d{1,2})[:.](\d{2})", text or "")
    return "-".join(f"{int(h)}:{m}" for h, m in nums[:2])


def score_timetable_more(path: Path, res: Resolver, staff: list[dict] | None) -> dict:
    """What a timetable holds beyond the plan, read by
    timetable_reader.read_timetable: every lesson where it was (for importing
    it as it is), the week's bell times and breaks, the blocks and the fixed
    periods. 0-100 over the parts this file shows; None when it shows none."""
    try:
        from app.services.smart_import import read_sheets
        from app.services.timetable_reader import read_timetable
    except ImportError:
        return {"more": 0, "more_parts": "no reader"}
    reading = read_timetable(read_sheets(path.name, path.read_bytes(), "timetable"), staff) or {}
    opts = res.expected.get("options", {})
    layout = res.expected["layout"]
    shown = res.expected["shows"]["sections"]
    truth = res.truth
    parts: dict[str, float] = {}

    # Lessons: each of the truth's, in a shown section, at the right day and
    # period with the right subject (or block).
    got: dict[tuple, str] = {}
    for sec in reading.get("sections", []):
        key = res.section(sec.get("label", ""))
        if key not in shown:
            continue
        for l in sec.get("lessons", []):
            got.setdefault((key, l.get("day"), l.get("period")), l.get("subject") or "")
    want = [l for l in truth["lessons"] if l["section"] in shown]
    right = 0
    for l in want:
        text = got.get((l["section"], l["day"], l["period"]))
        if text is None:
            continue
        grade = int(l["section"][:-1])
        k = res.block_or_subject(text, grade)
        if k == (l["block"] or l["subject"]) or (l["block"] and k == l["subject"]):
            right += 1
    extra = max(0, len(got) - len(want))
    parts["lessons"] = right / max(len(want) + extra, 1) if want else 0.0

    week = reading.get("week") or {}
    if opts.get("bell_row") and layout in ("class_grids", "transposed"):  # the only ones that draw them
        bells = {int(k): _clock(v) for k, v in (week.get("bell_times") or {}).items()}
        parts["bells"] = sum(1 for i, b in enumerate(truth["bell_times"], start=1) if bells.get(i) == _clock(b)) \
            / len(truth["bell_times"])
    if (layout == "class_grids" and opts.get("break_style") != "none") or layout == "transposed":
        want_b = {b["after_period"] for b in truth["breaks"]}
        got_b = {b.get("after") for b in week.get("breaks") or []}
        parts["breaks"] = _f1(len(want_b & got_b), len(got_b - want_b), len(want_b - got_b))

    grades = {int(s[:-1]) for s in shown}
    blocks = [b for b in truth["blocks"] if set(b["sections"]) & set(shown)]
    if blocks:
        found = 0.0
        for b in blocks:
            need = set(b["sections"]) & set(shown)
            for rb in reading.get("blocks", []):
                secs = {res.section(x) for x in rb.get("sections", [])}
                if need <= secs and rb.get("periods") == b["periods"]:
                    subs = {res.subject(o.get("subject", "")) for o in rb.get("options", [])}
                    found += 1.0 if {g["subject"] for g in b["groups"]} <= subs else 0.75
                    break
        parts["blocks"] = found / len(blocks)
    fixed = [f for f in truth["fixed_periods"] if set(f["grades"]) & grades]
    if fixed:
        ok = 0
        for f in fixed:
            for rf in reading.get("fixed", []):
                if rf.get("period") == f["period"] and res.subject(rf.get("subject", "")) == f["subject"]:
                    ok += 1
                    break
        parts["fixed"] = ok / len(fixed)
    score = sum(parts.values()) / len(parts) if parts else 0.0
    return {"more": round(100 * score), "more_parts": {k: round(100 * v) for k, v in parts.items()},
            "checks": (reading.get("checks") or [])[:3]}


# ----------------------------------------------------------------------- main

def run(root: Path, rules: bool, use_staff: bool, only: str | None) -> list[dict]:
    from app.services.smart_import import LiveAI
    ai = LiveAI()
    results = []
    cases = sorted(p for p in (root / "cases").iterdir() if p.is_dir())
    truths: dict[str, dict] = {}
    for folder in cases:
        exp = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
        if only and only not in exp["id"]:
            continue
        truth = truths.setdefault(exp["school"], json.loads((root / exp["school"]).read_text(encoding="utf-8")))
        res = Resolver(truth, exp)
        path = folder / exp["input"]
        row = {"id": exp["id"], "kind": exp["kind"], "layout": exp["layout"], "format": exp["format"]}
        try:
            if exp["kind"] == "subjects":
                row.update(score_subjects(path, res, ai))
            elif exp["kind"] == "teachers":
                row.update(score_teachers(path, res, ai))
            elif exp["kind"] == "timetable":
                staff = [{"name": t["name"], "subjects": t["subjects"]} for t in truth["teachers"]] if use_staff else None
                row.update(score_timetable(path, res, staff))
                try:
                    row.update(score_timetable_more(path, res, staff))
                except ValueError:
                    row.update(more=0)
                except Exception as e:  # noqa: BLE001
                    row.update(more=0, more_crashed=f"{type(e).__name__}: {str(e)[:100]}")
            elif exp["kind"] == "rules":
                if not rules:
                    row.update(score=None, skipped="rules need --rules and the AI key")
                else:
                    row.update(score=None, skipped="rules scoring: not built yet (Phase 5)")
        except ValueError as e:  # the importer's own "can't read this" message
            row.update(score=0, refused=str(e)[:120])
        except Exception as e:  # noqa: BLE001 - a crash is a finding, scored 0
            row.update(score=0, crashed=f"{type(e).__name__}: {str(e)[:100]}")
        results.append(row)
    return results


def report(results: list[dict], compare: list[dict] | None) -> None:
    before = {r["id"]: r for r in compare or []}
    by_kind = defaultdict(list)
    for r in results:
        by_kind[r["kind"]].append(r)
    print("\nOVERALL")
    for kind in ("timetable", "subjects", "teachers", "rules"):
        rs = [r for r in by_kind.get(kind, []) if r.get("score") is not None]
        if not rs:
            if by_kind.get(kind):
                print(f"  {kind:<10} skipped ({by_kind[kind][0].get('skipped')})")
            continue
        mean = sum(r["score"] for r in rs) / len(rs)
        refused = sum(1 for r in rs if "refused" in r or "crashed" in r)
        line = f"  {kind:<10} {mean:5.1f} / 100   over {len(rs)} files ({refused} refused or crashed)"
        if before:
            prev = [before[r["id"]]["score"] for r in rs if r["id"] in before and before[r["id"]].get("score") is not None]
            if prev:
                line += f"   was {sum(prev) / len(prev):5.1f}"
        print(line)
        if kind == "timetable":
            ms = [r for r in rs if r.get("more") is not None]
            if ms:
                line = (f"  {'  + more':<10} {sum(r['more'] for r in ms) / len(ms):5.1f} / 100   lessons where they "
                        "are, bell times, breaks, blocks, fixed periods")
                prev = [before[r["id"]].get("more", 0) for r in ms if r["id"] in before]
                if before and prev:
                    line += f"   was {sum(prev) / len(prev):5.1f}"
                print(line)
                part_sum: dict[str, list] = defaultdict(list)
                for r in ms:
                    for k, v in (r.get("more_parts") or {}).items() if isinstance(r.get("more_parts"), dict) else []:
                        part_sum[k].append(v)
                if part_sum:
                    print("             " + ", ".join(f"{k} {sum(v) / len(v):.0f} ({len(v)})" for k, v in part_sum.items()))
    print("\nBY LAYOUT AND FORMAT (mean score, files)")
    groups = defaultdict(list)
    for r in results:
        if r.get("score") is not None:
            groups[(r["kind"], r["layout"], r["format"])].append(r["score"])
    for (kind, layout, fmt), scores in sorted(groups.items()):
        print(f"  {kind:<10} {layout:<14} {fmt:<10} {sum(scores) / len(scores):5.1f}  ({len(scores)})")
    reasons = defaultdict(int)
    for r in results:
        if r.get("refused") or r.get("crashed"):
            reasons[(r.get("refused") or r.get("crashed"))[:90]] += 1
    if reasons:
        print("\nREFUSED / CRASHED")
        for why, n in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {n:3d}  {why}")
    if before:
        moved = [(r["id"], before[r["id"]].get("score"), r.get("score")) for r in results
                 if r["id"] in before and before[r["id"]].get("score") != r.get("score")]
        more_down = [(r["id"], before[r["id"]].get("more", 0), r.get("more")) for r in results
                     if r["id"] in before and r.get("more") is not None and r["more"] < before[r["id"]].get("more", 0)]
        if more_down:
            print(f"\n'MORE' WENT DOWN: {len(more_down)} files")
            for cid, a, b in more_down[:25]:
                print(f"  {cid:<55} {a} -> {b}")
        print(f"\nCHANGED SINCE THE SAVED RUN: {len(moved)} files")
        for cid, a, b in sorted(moved, key=lambda m: (m[2] or 0) - (m[1] or 0))[:25]:
            print(f"  {cid:<55} {a} -> {b}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", nargs="?", type=Path, default=HERE.parents[3] / "school-imports" / "generated")
    ap.add_argument("--save", type=Path, help="write every case's result here")
    ap.add_argument("--compare", type=Path, help="a saved run to show changes against")
    ap.add_argument("--rules", action="store_true", help="also score rule messages (needs the AI key)")
    ap.add_argument("--no-staff", action="store_true",
                    help="read timetables without the staff list (the website asks for it first)")
    ap.add_argument("--only", help="only cases whose id contains this")
    ap.add_argument("--detail", action="store_true", help="print every case's findings")
    args = ap.parse_args(argv)
    results = run(args.corpus, args.rules, not args.no_staff, args.only)
    if args.detail:
        for r in results:
            print(json.dumps(r, ensure_ascii=False))
    report(results, json.loads(args.compare.read_text()) if args.compare else None)
    if args.save:
        args.save.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\nsaved {len(results)} results to {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

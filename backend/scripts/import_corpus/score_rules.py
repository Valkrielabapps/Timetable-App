"""
Score how the rules page reads pasted messages (rules_corpus.py's).

    python scripts/import_corpus/score_rules.py                  # splitting and clock times (no AI)
    python scripts/import_corpus/score_rules.py --naive          # the same, splitting at line ends only (the old way)
    python scripts/import_corpus/score_rules.py --ai             # also reads every rule with the AI (needs the key)
    ... --save FILE / --compare FILE / --only TEXT / --detail

Without the AI, two things the app does before the AI sees anything:

  split    the message cut into one rule each (rule_splitter.split_rules):
           greetings, timestamps and sign-offs left out, two rules on one
           line cut apart. Each piece is matched to the rule it should be -
           the person or subject it names, and whether it's a daily limit -
           and scored as F1 over pieces and rules.
  clock    every clock time ("leaves at 12.40") turned into the right period
           from the school's bell times (rule_text_hints' reading aids).

With --ai, every piece goes through the same parser the website uses
(llm_ir_parser.parse_rule_llm), and the rules it makes are checked against
what was meant by trying lessons against them: a lesson of that teacher in
each period of the week is allowed or not, exactly where the fact says; a
day of N lessons passes and N+1 doesn't. So it doesn't matter which words or
which rule shape the parser chose, only whether the timetable would come out
right.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]))  # backend/

_MAX = re.compile(r"more than|\bmax|maximum|not more|at most|\bupto\b|up to", re.I)


def _f1(tp, fp, fn):
    if tp == 0:
        return 0.0
    p, r = tp / (tp + fp), tp / (tp + fn)
    return 2 * p * r / (p + r)


def school_context(truth: dict):
    teachers = [t["name"] for t in truth["teachers"]]
    subjects = sorted({p["subject"] for p in truth["plan"]} | {g["subject"] for b in truth["blocks"] for g in b["groups"]})
    labels = []
    for s in truth["sections"]:
        g = f"Grade {s[:-1]}"
        if g not in labels:
            labels.append(g)
        labels.append(f"{g} - {s[-1]}")
    breaks = {b["after_period"]: b["name"] for b in truth["breaks"]}
    periods = []
    for d in range(len(truth["days"])):
        order = 0
        for n, bell in enumerate(truth["bell_times"], start=1):
            periods.append((d, order, f"Period {n} ({bell})", "lesson"))
            order += 1
            if n in breaks and n < len(truth["bell_times"]):
                periods.append((d, order, breaks[n], "break"))
                order += 1
    return teachers, subjects, labels, periods


def _entity(fact: dict, written: dict) -> list[str]:
    if "teacher" in fact:
        # As written, or the school's own name for them (a piece carrying the
        # person into a second rule writes it the school's way).
        return list(dict.fromkeys(written["teachers"].get(fact["teacher"], []) + [fact["teacher"]]))
    return [fact["subject"]]


def score_split(text: str, exp: dict, truth: dict, naive: bool) -> dict:
    from app.services.rule_splitter import split_rules
    teachers, subjects, _, _ = school_context(truth)
    units = [ln.strip() for ln in text.splitlines() if ln.strip()] if naive else split_rules(text, teachers, subjects)
    facts = exp["facts"]
    used, tp, missed = set(), 0, []
    # Longer names first, and whole words: "Science" mustn't take the piece
    # that says "Computer Science".
    for f in sorted(facts, key=lambda f: -max(len(n) for n in _entity(f, exp["written"]))):
        names = [n.lower() for n in _entity(f, exp["written"])]
        want_max = f["type"] == "teacher_max_per_day"

        def says(u):
            low = u.lower()
            for n in names:
                for m in re.finditer(rf"(?<![a-z]){re.escape(n)}(?![a-z])", low):
                    longer = [x.lower() for x in exp["written"]["subjects"] if n in x.lower() and x.lower() != n]
                    if not any(x in low for x in longer):
                        return True
            return False
        hit = next((i for i, u in enumerate(units) if i not in used and says(u)
                    and bool(_MAX.search(u)) == want_max), None)
        if hit is None:
            missed.append(f"{f['type']} {f.get('teacher') or f.get('subject')}")
        else:
            used.add(hit)
            tp += 1
    extra = [u for i, u in enumerate(units) if i not in used]
    return {"split": round(100 * _f1(tp, len(extra), len(facts) - tp)), "units": len(units), "rules": len(facts),
            "extra_pieces": extra[:3], "missed": missed[:3], "pieces": units}


def score_clock(units: list[str], exp: dict, truth: dict) -> dict | None:
    from app.services.rule_text_hints import _clock_hints
    if not exp["clock"]:
        return None
    _, _, _, periods = school_context(truth)
    ok = 0
    for c in exp["clock"]:
        unit = next((u for u in units if c["text"] in u), c["text"])
        hints = " ".join(_clock_hints(unit, periods))
        first_after = (c.get("periods_after") or [None])[0]
        last_before = (c.get("periods_before") or [None])[-1]
        n = first_after if first_after else (last_before + 1 if last_before else None)
        if n and (f"start of period {n} " in hints + " " or f"end of period {n - 1} " in hints + " "):
            ok += 1
    return {"clock": round(100 * ok / len(exp["clock"])), "clock_times": len(exp["clock"])}


# ------------------------------------------------------------------ with the AI

def _index(truth: dict):
    from app.services.constraint_ir_compiler import SchoolIndex
    teachers, subjects, labels, _ = school_context(truth)
    n = truth["periods_per_day"]
    days = range(len(truth["days"]))
    sec_ids = {s: i + 1 for i, s in enumerate(truth["sections"])}
    cg = {}
    for s, i in sec_ids.items():
        cg.setdefault(f"Grade {s[:-1]}", []).append(i)
        cg[f"Grade {s[:-1]} - {s[-1]}"] = [i]
    subject_ids = {s: i + 1 for i, s in enumerate(subjects + ["Probe Subject"])}
    teacher_ids = {t: i + 1 for i, t in enumerate(teachers + ["Probe Teacher"])}
    index = SchoolIndex(subject_ids=subject_ids, teacher_ids=teacher_ids, class_group_ids=cg,
                        orders_by_day={d: list(range(n)) for d in days},
                        first_order_by_day={d: 0 for d in days}, last_order_by_day={d: n - 1 for d in days})
    return index, sec_ids


def _violates(rules, placements, index) -> bool:
    from app.services.constraint_ir_checker import check_rule
    from app.services.constraint_ir_compiler import UnknownName
    for r in rules:
        try:
            if check_rule(placements, r, index):
                return True
        except UnknownName:
            continue
    return False


def score_ai(units: list[str], exp: dict, truth: dict) -> dict:
    from app.services.constraint_ir_checker import Placement
    from app.services.llm_ir_parser import parse_rule_llm
    teachers, subjects, labels, periods = school_context(truth)
    rules, unread = [], []
    for u in units:
        res = parse_rule_llm(u, teachers, subjects, labels, periods)
        if res is None:
            return {"ai": None, "ai_skipped": "no AI key"}
        if getattr(res, "rule", None) is not None:
            rules.append(res.rule)
        else:
            unread.append(u)
    index, sec_ids = _index(truth)
    n, days = truth["periods_per_day"], list(range(len(truth["days"])))
    day_ix = {d: i for i, d in enumerate(truth["days"])}
    sec = next(iter(sec_ids.values()))

    def lesson(teacher, subject, d, p, k=0):
        return Placement(entry_id=k + 1, class_group_id=list(sec_ids.values())[k % len(sec_ids)],
                         subject_id=index.subject_ids[subject], teacher_id=index.teacher_ids[teacher],
                         period_id=d * 100 + p, day_of_week=d, order=p - 1)

    forbidden: dict[str, set] = defaultdict(set)
    for f in exp["facts"]:
        if f["type"] == "teacher_unavailable":
            for s in f["slots"]:
                forbidden[f["teacher"]] |= {(day_ix[s["day"]], p) for p in s["periods"]}
    scores, wrong = [], []
    for t, want in forbidden.items():
        got = {(d, p) for d in days for p in range(1, n + 1)
               if _violates(rules, [lesson(t, "Probe Subject", d, p)], index)}
        scores.append(_f1(len(got & want), len(got - want), len(want - got)))
        if got != want:
            wrong.append(f"{t}: blocks {len(got)} periods, should block {len(want)}")
    for f in exp["facts"]:
        if f["type"] == "subject_not_in_period":
            want = {(d, p) for d in days for p in f["periods"]}
            got = {(d, p) for d in days for p in range(1, n + 1)
                   if _violates(rules, [lesson("Probe Teacher", f["subject"], d, p)], index)}
            scores.append(_f1(len(got & want), len(got - want), len(want - got)))
            if got != want:
                wrong.append(f"{f['subject']}: blocks {len(got)} periods, should block {len(want)}")
        elif f["type"] == "teacher_max_per_day":
            v, t = f["value"], f["teacher"]
            free = next((d for d in days if len([p for p in range(1, n + 1) if (d, p) not in forbidden[t]]) > v), None)
            if free is None:
                continue
            ps = [p for p in range(1, n + 1) if (free, p) not in forbidden[t]][:v + 1]
            ok_v = not _violates(rules, [lesson(t, "Probe Subject", free, p, k) for k, p in enumerate(ps[:v])], index)
            bad = _violates(rules, [lesson(t, "Probe Subject", free, p, k) for k, p in enumerate(ps)], index)
            scores.append(1.0 if ok_v and bad else 0.0)
            if not (ok_v and bad):
                wrong.append(f"{t}: at most {v} a day not kept")
    return {"ai": round(100 * sum(scores) / len(scores)) if scores else None, "unread": unread[:3],
            "ai_wrong": wrong[:4]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus", nargs="?", type=Path, default=HERE.parents[3] / "school-imports" / "generated")
    ap.add_argument("--naive", action="store_true")
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--save", type=Path)
    ap.add_argument("--compare", type=Path)
    ap.add_argument("--only")
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args(argv)
    results = []
    truths: dict[str, dict] = {}
    for folder in sorted((args.corpus / "rules").iterdir()):
        exp = json.loads((folder / "expected.json").read_text(encoding="utf-8"))
        if args.only and args.only not in exp["id"]:
            continue
        truth = truths.setdefault(exp["school"], json.loads((args.corpus / exp["school"]).read_text(encoding="utf-8")))
        text = (folder / "input.txt").read_text(encoding="utf-8")
        row = {"id": exp["id"], "style": exp["style"]}
        row.update(score_split(text, exp, truth, args.naive))
        clock = score_clock(row["pieces"], exp, truth) if not args.naive else (
            {"clock": 0, "clock_times": len(exp["clock"])} if exp["clock"] else None)
        if clock:
            row.update(clock)
        if args.ai:
            row.update(score_ai(row["pieces"], exp, truth))
        if not args.detail:
            row.pop("pieces")
        results.append(row)
        if args.detail:
            print(json.dumps(row, ensure_ascii=False))
    before = {r["id"]: r for r in json.loads(args.compare.read_text())} if args.compare else {}

    def mean(key, rows):
        xs = [r[key] for r in rows if r.get(key) is not None]
        return sum(xs) / len(xs) if xs else None

    print(f"\nRULE MESSAGES ({len(results)})")
    for key, what in (("split", "each rule its own piece"), ("clock", "clock times as periods"),
                      ("ai", "rules read right (AI)")):
        m = mean(key, results)
        if m is None:
            continue
        line = f"  {key:<6} {m:5.1f} / 100   {what}"
        b = mean(key, list(before.values())) if before else None
        if b is not None:
            line += f"   was {b:5.1f}"
        print(line)
    by_style = defaultdict(list)
    for r in results:
        by_style[r["style"]].append(r["split"])
    print("  split by layout: " + ", ".join(f"{k} {sum(v) / len(v):.0f}" for k, v in sorted(by_style.items())))
    if before:
        down = [(r["id"], before[r["id"]].get("split"), r["split"]) for r in results
                if r["id"] in before and r["split"] < (before[r["id"]].get("split") or 0)]
        print(f"  went down: {len(down)}" + "".join(f"\n    {a} {b} -> {c}" for a, b, c in down[:10]))
    if args.save:
        args.save.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"saved to {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

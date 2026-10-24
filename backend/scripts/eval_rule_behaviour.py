"""
Check what each parsed rule DOES, not what it looks like.

eval_ir_parser.py asks whether a sentence became a valid rule and prints the
English for a person to judge. That can't catch the worst failure: a rule that
reads plausibly and constrains the timetable differently from what was meant.
Two rules can be written differently and mean the same thing, so comparing them
field by field fails good readings too.

This compares behaviour instead. Every case in docs/research/behaviour-cases.json
is a sentence plus the rule it should mean (the reference). On a small eval
school the script asks the solver two questions:

  1. Keeping the PARSED rule, can it break the reference?   yes -> LOOSER
     (the reading allows something the sentence forbids)
  2. Keeping the REFERENCE, can it break the parsed rule?   yes -> STRICTER
     (the reading forbids something the sentence allows)

Neither -> OK: on this school the two readings can't be told apart. Each
"can it break" is a real search (the solver is told to violate the rule as
much as it can while keeping the other), and the result is confirmed with the
same checker the app uses to flag broken rules.

It also reports, per case:
  WEAK      the reference never bites on the eval school, so OK means little -
            fix the case or the school.
  ASKED     the parser asked a question instead. Right for 'expect: ask'.
  GUESSED   the parser produced a rule where it should have asked.
  INVALID   the parser produced something the rule checker refused.
  STRENGTH  the strictness differs (rule vs "try to").

    python scripts/eval_rule_behaviour.py               # every case, calls the API
    python scripts/eval_rule_behaviour.py --only B04 B09
    python scripts/eval_rule_behaviour.py --dry-run     # no API: checks the cases
                                                        # and the school themselves

Writes docs/research/behaviour-run-<date>.tsv. Run it before shipping any
change to the parser prompt or the rule checker, and compare with the last run:
anything that was OK and isn't any more is a regression.

Requires ANTHROPIC_API_KEY (except --dry-run). Nothing here touches the app's
database: the eval school lives in memory.
"""
import argparse
import csv
import datetime
import json
import pathlib
import sys
import time
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.database import Base  # noqa: E402
import app.models.payment  # noqa: E402,F401 - every table, for create_all
import app.models.user  # noqa: E402,F401
from app.models.school import (  # noqa: E402
    ClassGroup, Constraint, Period, School, Subject, SubjectRequirement, Teacher,
)
from app.schemas.timetable_structure import BreakSlot, TimetableStructure  # noqa: E402
from app.services import solver as solver_mod  # noqa: E402
from app.services import timetable_structure  # noqa: E402
from app.services.constraint_ir import IRError, rule_from_dict, rule_to_dict  # noqa: E402
from app.services.constraint_ir_checker import Placement, check_rules  # noqa: E402
from app.services.constraint_ir_compiler import SchoolIndex  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "docs" / "research" / "behaviour-cases.json"

# ---------------------------------------------------------------------------
# The eval school. Small enough to solve in a second, with slack everywhere so
# that a rule, not the setup, decides what is possible: every section has a few
# free periods and every subject a spare teacher's worth of time.
# ---------------------------------------------------------------------------

SUBJECTS = ["English", "Maths", "Science", "Hindi", "Social Studies", "PE", "Art", "Physics", "Chemistry", "Library"]
TEACHERS = [
    ("Mrs. Rao", ["Maths"]), ("Mr. Menon", ["Maths"]),
    ("Mr. Iyer", ["English"]), ("Ms. Thomas", ["English"]),
    ("Ms. Das", ["Science", "Physics"]), ("Mr. Nair", ["Chemistry", "Science"]),
    ("Mr. Khan", ["Hindi"]), ("Mrs. Pillai", ["Social Studies", "Hindi"]),
    ("Coach Biju", ["PE"]), ("Ms. Mary", ["Art", "Library"]),
]
JUNIOR = {"English": 5, "Maths": 6, "Science": 5, "Hindi": 4, "Social Studies": 4, "PE": 2, "Art": 2}
SENIOR = {"English": 5, "Maths": 6, "Physics": 4, "Chemistry": 4, "Hindi": 3, "Social Studies": 3, "PE": 2, "Library": 1}
SECTIONS = [("Grade 6", "A", JUNIOR), ("Grade 6", "B", JUNIOR), ("Grade 9", "A", SENIOR)]


def build_school():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    school = School(name="Eval School")
    db.add(school)
    db.commit()
    # Monday to Saturday, 6 periods (3 on Saturday), short break after 2,
    # lunch after 4.
    timetable_structure.apply(db, school.id, TimetableStructure(
        days=[0, 1, 2, 3, 4, 5], periods_per_day=6, short_days={5: 3},
        breaks=[BreakSlot(after=2, label="Short break"), BreakSlot(after=4, label="Lunch")],
    ))
    subjects = {n: Subject(school_id=school.id, name=n) for n in SUBJECTS}
    db.add_all(subjects.values())
    db.commit()
    for name, subs in TEACHERS:
        db.add(Teacher(school_id=school.id, name=name, qualified_subject_ids=[subjects[s].id for s in subs]))
    for grade, name, plan in SECTIONS:
        cg = ClassGroup(school_id=school.id, grade=grade, name=name)
        db.add(cg)
        db.commit()
        for subject, n in plan.items():
            db.add(SubjectRequirement(class_group_id=cg.id, subject_id=subjects[subject].id, periods_per_week=n))
    db.commit()
    return db, school.id


def _index(db, school_id):
    from app.routers.timetables import _edge_orders, _orders_by_day
    periods = [p for p in db.query(Period).filter(Period.school_id == school_id).all()]
    return SchoolIndex(
        subject_ids={s.name: s.id for s in db.query(Subject).filter(Subject.school_id == school_id)},
        teacher_ids={t.name: t.id for t in db.query(Teacher).filter(Teacher.school_id == school_id)},
        class_group_ids=solver_mod._class_group_labels(db.query(ClassGroup).filter(ClassGroup.school_id == school_id).all()),
        orders_by_day=_orders_by_day(periods),
        first_order_by_day=_edge_orders(periods, first=True),
        last_order_by_day=_edge_orders(periods, first=False),
    ), {p.id: p for p in periods}


# How many differently-steered searches look for a counterexample. More finds
# subtler differences and takes longer.
TRIES = 4
# Quick solves: the eval school is tiny, and each search only needs to land
# somewhere new, not prove it is the best.
solver_mod.SETTLE_SECONDS = 1.0
solver_mod.IMPROVE_SECONDS = 4


def solve(db, school_id, keep: list, adversary, seed: int = 0):
    """Solve keeping `keep` (rules, as hard), steered towards breaking
    `adversary`. Returns (status, assignments)."""
    db.query(Constraint).filter(Constraint.school_id == school_id).delete()
    for rule in keep:
        db.add(Constraint(school_id=school_id, type="ir", parameters=rule_to_dict(replace(rule, strength="required")),
                          is_hard=True, description=rule.description or "rule"))
    db.commit()
    tokens = [
        solver_mod._ADVERSARY.set((adversary, seed) if adversary is not None else None),
        solver_mod._DEFAULT_HABITS.set(False),
        solver_mod._TIME_LIMIT.set(20),
    ]
    try:
        result = solver_mod.generate_school_timetable(db, school_id)
    finally:
        solver_mod._TIME_LIMIT.reset(tokens[2])
        solver_mod._DEFAULT_HABITS.reset(tokens[1])
        solver_mod._ADVERSARY.reset(tokens[0])
    return result.status, result.assignments


def can_break(db, school_id, keep: list, rule, index, periods) -> bool:
    """Keeping `keep`, is there a timetable that breaks `rule`? Searches TRIES
    times, each steered differently, and confirms with the app's checker."""
    for seed in range(TRIES):
        status, assignments = solve(db, school_id, keep, rule, seed)
        if status in ("optimal", "feasible") and breaks(rule, assignments, index, periods):
            return True
    return False


def breaks(rule, assignments, index, periods) -> int:
    placements = [
        Placement(entry_id=i, class_group_id=a["class_group_id"], subject_id=a["subject_id"],
                  teacher_id=a["teacher_id"], period_id=a["period_id"],
                  day_of_week=periods[a["period_id"]].day_of_week, order=periods[a["period_id"]].order,
                  occupies_teacher=a["teacher_id"] is not None)
        for i, a in enumerate(assignments)
    ]
    return len(check_rules(placements, [(None, replace(rule, strength="required"))], index))


def compare(db, school_id, parsed: list, refs: list, index, periods) -> tuple[str, str]:
    """(verdict, note) for parsed rule(s) against the reference rule(s)."""
    status, _ = solve(db, school_id, parsed, None)
    if status not in ("optimal", "feasible"):
        return "IMPOSSIBLE", "the parsed reading leaves no timetable on the eval school"
    looser = [r for r in refs if can_break(db, school_id, parsed, r, index, periods)]
    stricter = [p for p in parsed if can_break(db, school_id, refs, p, index, periods)]
    if looser and stricter:
        return "DIFFERENT", "allows what the sentence forbids, and forbids what it allows"
    if looser:
        return "LOOSER", "allows something the sentence forbids"
    if stricter:
        return "STRICTER", "forbids something the sentence allows"
    return "OK", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="case ids")
    ap.add_argument("--dry-run", action="store_true", help="use each reference as the parse: checks the cases, no API")
    args = ap.parse_args()

    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]

    db, school_id = build_school()
    index, periods = _index(db, school_id)
    data = None
    if not args.dry_run:
        from app.core.config import settings
        if not settings.anthropic_api_key:
            sys.exit("ANTHROPIC_API_KEY isn't set. Use --dry-run to check the cases without it.")
        from app.routers.constraints import _load_resolution_data
        from app.services.llm_ir_parser import parse_rule_llm
        data = _load_resolution_data(db, school_id)

    rows = []
    started = time.monotonic()
    for case in cases:
        expect = case.get("expect", "rule")
        refs = []
        for key in ("reference", "also"):
            if case.get(key):
                refs.append(rule_from_dict({**case[key], "strength": "required"}))
        want_strength = case.get("strength", "required")
        verdict, note, read_as, got_strength = "", "", "", ""

        # The case itself first: a reference that never bites proves nothing.
        weak = [r for r in refs if not can_break(db, school_id, [], r, index, periods)]

        if args.dry_run:
            parsed, read_as, got_strength = list(refs), "(reference)", want_strength
            if expect == "ask":
                verdict = "ASKED"
        else:
            result = parse_rule_llm(case["typed"], data.teacher_names, data.subject_names,
                                    data.class_group_labels, data.periods)
            parsed = []
            if result is None:
                verdict, note = "ERROR", "the API call failed"
            elif result.invalid is not None:
                verdict, note = "INVALID", str(result.invalid)[:200]
            elif result.unclear is not None:
                verdict = "ASKED"
                read_as = result.unclear.question or result.unclear.explanation or ""
            else:
                parsed = [result.rule]
                read_as = result.sentence
                got_strength = result.rule.strength

        if parsed and refs and not verdict:
            verdict, note = compare(db, school_id, parsed, refs, index, periods)
            if expect == "ask":
                note = (note + "; " if note else "") + "should have asked"
                verdict = "GUESSED" if verdict == "OK" else verdict
        elif parsed and expect == "ask" and not verdict:
            verdict, note = "GUESSED", "should have asked"
        if verdict == "ASKED" and expect not in ("ask", "either"):
            note = "asked where a rule was expected"
        if verdict == "OK" and got_strength != want_strength:
            verdict, note = "STRENGTH", f"read as {got_strength}, meant {want_strength}"
        if weak and verdict in ("OK", "STRENGTH"):
            note = (note + "; " if note else "") + "WEAK: the reference never bites on the eval school"

        passed = verdict == "OK" or (verdict == "ASKED" and expect in ("ask", "either"))
        rows.append({"ID": case["id"], "VERDICT": verdict, "PASS": "yes" if passed else "no",
                     "TYPED": case["typed"], "READ_AS": read_as, "NOTE": note})
        print(f"{case['id']:5} {verdict:10} {'' if passed else 'FAIL '}{case['typed']}"
              + (f"\n      read as: {read_as}" if read_as and not passed else "")
              + (f"\n      {note}" if note else ""))

    passed = sum(r["PASS"] == "yes" for r in rows)
    print(f"\n{passed}/{len(rows)} pass  ({time.monotonic() - started:.0f}s)")
    if not args.dry_run:
        out = ROOT / "docs" / "research" / f"behaviour-run-{datetime.date.today().isoformat()}{'-partial' if args.only else ''}.tsv"
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
        print(f"written to {out.relative_to(ROOT)}")
    sys.exit(0 if passed == len(rows) else 1)


if __name__ == "__main__":
    main()

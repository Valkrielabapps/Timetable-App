"""
Score the IR parser against the rule catalogue.

eval_constraint_parser.py measures the nine legacy types, where the question is
"did the rule reach the right type". The IR has no types, so the question
changes: a rule either becomes something the solver can execute, or the parser
says honestly that it can't. This measures both, and it is the number that
decides whether the IR was worth building.

What it reports
---------------
  EXPRESSED      the parser produced a valid rule. Against the 144 rules the
                 nine types could not represent at all, this is the headline:
                 it is the coverage the IR bought.

  DECLINED       the parser used report_unclear instead. For a vague or
                 ambiguous row that is the right answer, so it is counted
                 separately rather than as a failure.

  INVALID        the parser produced something that failed validation. A real
                 defect - the schema or the prompt is not carrying the shape.

Crucially, EXPRESSED is not the same as CORRECT. A rule can be valid, applied,
and mean something other than what the admin said - which is the risk the IR
introduces and the echo-back exists to catch. This script prints the rendered
English for every rule so that a person can read down the column and judge, and
--check turns that into the only honest measure: how many read right.

    python scripts/eval_ir_parser.py                 # all 170, a few cents
    python scripts/eval_ir_parser.py --missing-only  # the 144 the types missed
    python scripts/eval_ir_parser.py --check         # print every sentence
    python scripts/eval_ir_parser.py --only R012 R049

Requires ANTHROPIC_API_KEY, the same one the app uses.
"""
import argparse
import csv
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.llm_ir_parser import parse_rule_llm  # noqa: E402

CATALOGUE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "research" / "constraint-catalogue.tsv"

# The school the catalogue was written against. These lists have to contain
# every name the rules mention, or a correct parse still declines for an
# unknown reference and the score measures the fixture rather than the parser.
TEACHERS = [
    "Mrs. Rao", "Mr. Khan", "Ms. Das", "Arjun", "Priya", "Mr. Iyer",
    "Ms. Kavya", "Ms. Fernandez", "Mr. Suresh", "Lakshmi",
]
SUBJECTS = [
    "Maths", "Science", "English", "Hindi", "Tamil", "Physics", "Chemistry",
    "Biology", "Computer Science", "PE", "Art", "Music", "Library",
    "Social Science", "Sanskrit", "French", "Kannada",
]
CLASS_GROUPS = (
    [f"Grade {g}" for g in range(1, 13)]
    + [f"Grade {g} - {s}" for g in (6, 7, 8, 9, 10, 11, 12) for s in ("A", "B", "C", "D")]
)
# 5x8 plus a short Saturday, with the two breaks the catalogue's rules lean on
# ("just after the short break", "not right after lunch").
PERIODS = (
    [(d, o, "Short break" if o == 4 else "Lunch" if o == 6 else None, o in (4, 6))
     for d in range(5) for o in range(1, 9)]
    + [(5, o, None, False) for o in range(1, 5)]
)


def load_catalogue():
    with CATALOGUE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N rules")
    ap.add_argument("--only", nargs="+", metavar="ID", help="specific ids, e.g. R012")
    ap.add_argument("--missing-only", action="store_true",
                    help="only the rules the nine legacy types could not express")
    ap.add_argument("--check", action="store_true",
                    help="print every rendered sentence, for reading against the input")
    args = ap.parse_args()

    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY is not set, so there is nothing to evaluate.")

    rows = [r for r in load_catalogue() if r["VERDICT"] not in ("SETUP", "NOT-A-RULE")]
    if args.missing_only:
        rows = [r for r in rows if r["VERDICT"] == "MISSING"]
    if args.only:
        rows = [r for r in rows if r["ID"] in set(args.only)]
    if args.limit:
        rows = rows[: args.limit]

    print(f"Evaluating {len(rows)} rules against model={settings.llm_model}\n")

    outcomes = Counter()
    by_capability = Counter()
    declines = Counter()
    lines = []

    for row in rows:
        result = parse_rule_llm(row["TYPED"], TEACHERS, SUBJECTS, CLASS_GROUPS, PERIODS)
        if result is None:
            sys.exit("  parser unavailable (no key, or the call failed) - stopping")

        if result.rule is not None:
            outcomes["expressed"] += 1
            by_capability[row["CAPABILITY"]] += 1
            lines.append((row["ID"], "OK", row["TYPED"], result.sentence))
        elif result.unclear is not None:
            outcomes["declined"] += 1
            declines[result.unclear.reason] += 1
            lines.append((row["ID"], f"ASK[{result.unclear.reason}]", row["TYPED"],
                          result.unclear.explanation))
        else:  # pragma: no cover - defensive
            outcomes["invalid"] += 1
            lines.append((row["ID"], "BAD", row["TYPED"], ""))

    if args.check:
        print("Read the right-hand column against the left. A sentence that")
        print("reads wrong is a rule that would have been applied wrongly.\n")
        for rid, status, typed, said in lines:
            print(f"{rid} {status}")
            print(f"   typed: {typed}")
            print(f"   read : {said}\n")

    total = sum(outcomes.values())
    print("=" * 66)
    print(f"EXPRESSED  {outcomes['expressed']:3d}/{total}  "
          f"({100 * outcomes['expressed'] / total:.0f}%)  became a rule the solver can run")
    print(f"DECLINED   {outcomes['declined']:3d}/{total}  "
          f"({100 * outcomes['declined'] / total:.0f}%)  asked instead of guessing")
    if outcomes["invalid"]:
        print(f"INVALID    {outcomes['invalid']:3d}/{total}  failed validation - a real defect")

    if declines:
        print("\nWhy it declined:")
        for reason, n in declines.most_common():
            print(f"  {n:3d}  {reason}")

    if by_capability:
        print("\nExpressed, by the capability the nine types were missing:")
        for capability, n in by_capability.most_common():
            print(f"  {n:3d}  {capability}")

    print("\nEXPRESSED counts rules that are valid, not rules that are right.")
    print("Run with --check and read the sentences: that is the only measure")
    print("that says whether the timetable would do what was asked.")
    print("=" * 66)


if __name__ == "__main__":
    main()

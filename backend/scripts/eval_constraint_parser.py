"""
Score the constraint parser against the rule catalogue.

Why this exists
---------------
Until now there was no way to tell whether a change to the prompt or the tool
schema made parsing better or worse. A rule that came back as scheduling_rule
looked identical to a rule that came back wrong, and both looked identical to
a rule the solver was never going to enforce anyway. So prompt changes were
judged by trying two or three sentences by hand.

docs/research/constraint-catalogue.tsv is 187 rules written the way school
staff actually write them, each already classified by whether today's
constraint types can express it at all. That turns "is the parser any good"
into an arithmetic question, and this script is the arithmetic.

What it measures
----------------
Two numbers that must not be confused:

  RECALL ON EXPRESSIBLE - of the rules the solver *can* enforce, how many did
      the parser actually route to the right type? This is the parser's score.
      It is the number that should go up when the prompt improves.

  HONESTY ON THE REST - of the rules the solver *cannot* enforce, how many did
      the parser correctly drop into scheduling_rule instead of forcing into a
      type that would half-apply them? A wrong type here is worse than no type:
      it silently changes the timetable and reports itself as enforced.

Running it costs real API calls (one per rule, ~187), so it is a script you run
deliberately, not a test. At Haiku pricing the whole catalogue is a few cents.

    python scripts/eval_constraint_parser.py            # the whole catalogue
    python scripts/eval_constraint_parser.py --only R005 R012
    python scripts/eval_constraint_parser.py --limit 20 --verbose

Requires ANTHROPIC_API_KEY, the same one the app uses.
"""
import argparse
import csv
import pathlib
import sys
from collections import Counter

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.services.llm_constraint_parser import parse_constraint_llm  # noqa: E402

CATALOGUE = pathlib.Path(__file__).resolve().parents[2] / "docs" / "research" / "constraint-catalogue.tsv"

# The school the catalogue was written against: a CBSE secondary school with
# named staff. The parser is grounded on these lists, so they have to contain
# every name the rules mention or a correct parse still returns null and the
# score measures the fixture rather than the parser.
TEACHERS = [
    "Mrs. Rao", "Mr. Khan", "Ms. Das", "Arjun", "Priya", "Mr. Iyer",
    "Ms. Kavya", "Ms. Fernandez", "Mr. Suresh", "Lakshmi",
]
SUBJECTS = [
    "Maths", "Science", "English", "Hindi", "Tamil", "Physics", "Chemistry",
    "Biology", "Computer Science", "PE", "Art", "Music", "Library",
    "Social Science", "Sanskrit", "French", "Kannada",
]
CLASS_GROUPS = [
    f"Grade {g}" for g in range(1, 13)
] + [
    f"Grade {g} - {s}" for g in (6, 7, 8, 9, 10, 11, 12) for s in ("A", "B", "C", "D")
]
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


def evaluate(rows, verbose=False):
    expressible = Counter()   # right / wrong-type / dropped
    honest = Counter()        # honest / forced
    confusion = Counter()

    for row in rows:
        parsed = parse_constraint_llm(row["TYPED"], TEACHERS, SUBJECTS, CLASS_GROUPS, PERIODS)
        if parsed is None:
            print(f"  {row['ID']}: parser unavailable (no key, or the call failed) - stopping")
            return None
        got = parsed.type

        if row["VERDICT"] in ("EXPRESSIBLE", "PARTIAL"):
            want = row["CAPABILITY"]
            # `strength` is a modifier on another type rather than a type, so
            # any specific type carrying strength counts as right.
            if want == "strength":
                ok = got != "scheduling_rule"
            else:
                ok = got == want
            if ok:
                expressible["right"] += 1
            elif got == "scheduling_rule":
                expressible["dropped"] += 1
                confusion[f"{want} -> dropped"] += 1
            else:
                expressible["wrong-type"] += 1
                confusion[f"{want} -> {got}"] += 1
            if verbose and not ok:
                print(f"  {row['ID']} want={want} got={got}\n      {row['TYPED']}")
        else:
            # Nothing the solver can enforce. scheduling_rule is the honest
            # answer; anything else half-applies a rule and claims it worked.
            if got == "scheduling_rule":
                honest["honest"] += 1
            else:
                honest["forced"] += 1
                confusion[f"(unenforceable) -> {got}"] += 1
                if verbose:
                    print(f"  {row['ID']} forced into {got}\n      {row['TYPED']}")

    return expressible, honest, confusion


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the first N rules, for a quick check")
    ap.add_argument("--only", nargs="+", metavar="ID", help="specific catalogue ids, e.g. R005")
    ap.add_argument("--verbose", action="store_true", help="print every miss as it happens")
    args = ap.parse_args()

    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY is not set, so there is nothing to evaluate.")

    rows = load_catalogue()
    # SETUP and NOT-A-RULE rows belong to the Data tab and the edit-command
    # path, not the constraint parser, so scoring them here would measure the
    # wrong thing.
    rows = [r for r in rows if r["VERDICT"] not in ("SETUP", "NOT-A-RULE")]
    if args.only:
        rows = [r for r in rows if r["ID"] in set(args.only)]
    if args.limit:
        rows = rows[: args.limit]

    print(f"Evaluating {len(rows)} rules against model={settings.llm_model}\n")
    result = evaluate(rows, verbose=args.verbose)
    if result is None:
        sys.exit(1)
    expressible, honest, confusion = result

    total_e = sum(expressible.values())
    total_h = sum(honest.values())

    print("\n" + "=" * 62)
    if total_e:
        pct = 100 * expressible["right"] / total_e
        print(f"RECALL ON EXPRESSIBLE   {expressible['right']}/{total_e}  ({pct:.0f}%)")
        print(f"  wrong type  {expressible['wrong-type']}   (applied, but not the rule that was asked for)")
        print(f"  dropped     {expressible['dropped']}   (recorded, never applied)")
    if total_h:
        pct = 100 * honest["honest"] / total_h
        print(f"\nHONESTY ON THE REST     {honest['honest']}/{total_h}  ({pct:.0f}%)")
        print(f"  forced      {honest['forced']}   (silently half-applied, and shown as enforced)")

    if confusion:
        print("\nWhere it went wrong:")
        for pair, n in confusion.most_common(12):
            print(f"  {n:3d}  {pair}")
    print("=" * 62)


if __name__ == "__main__":
    main()

"""
Rewrite eval sentences in other people's styles, so the tests stop sharing one
author's habits.

Every behaviour case was written by one person, and the parser has been tuned
until it reads that person's phrasing perfectly. Real admins write differently.
This asks a model - at full creativity, unlike the parser - to rewrite a sample
of cases the way different people would type them: Hinglish, typo-heavy, a
rambling WhatsApp message, a formal circular, voice-typed with no punctuation.
The meaning is kept, so each rewrite inherits its case's reference rule and is
checked by eval_rule_behaviour.py like any other case:

    python scripts/make_paraphrases.py                 # 25 cases x 4 styles, ~5 cents
    python scripts/eval_rule_behaviour.py --split paraphrase

Rewrites are written to docs/research/behaviour-cases.json with split
"paraphrase", replacing any from an earlier run. Read a few before trusting
them: a rewrite that changed the meaning is a bad test, not a parser failure -
delete it, or fix its wording.

Spends at most --budget dollars (default 0.10).
"""
import argparse
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ROOT / "docs" / "research" / "behaviour-cases.json"
PRICE_IN, PRICE_OUT = 1.00, 5.00  # Claude Haiku 4.5, $ per million tokens

STYLES = [
    "Hinglish, the way a Delhi or Mumbai school coordinator types on WhatsApp (mix Hindi words in Latin script)",
    "very informal with typos, abbreviations and no capital letters, typed fast on a phone",
    "a long, rambling message that gives the reason for the rule as well as the rule",
    "formal, like a line in a printed school circular",
    "voice-typed: no punctuation, numbers as words, filler words like 'okay so'",
    "Indian-English as a Kerala school office would write it, short and direct",
]

PROMPT = """You rewrite one school timetable rule in a different person's voice.

Keep the MEANING exactly: the same teachers, subjects, classes, days and periods,
the same limits, and the same strictness (a firm rule stays firm; a "try to" stays
a "try to"). Do not add or drop any condition. Names may be written informally
(e.g. "Mrs. Rao" -> "rao maam", "Grade 6" -> "6th std", "PE" -> "PT") but must
still clearly refer to the same thing.

Rule: {typed}

Write {n} rewrites, one in each of these styles:
{styles}

Answer with only a JSON list of {n} strings."""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", type=int, default=25, help="how many cases to rewrite (default 25)")
    ap.add_argument("--styles", type=int, default=4, help="rewrites per case (default 4)")
    ap.add_argument("--budget", type=float, default=0.10, help="stop once this many dollars are spent")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not settings.anthropic_api_key:
        sys.exit("ANTHROPIC_API_KEY isn't set.")
    import anthropic
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=2)

    data = json.loads(CASES.read_text(encoding="utf-8"))
    # Rules with a reference only (questions are judged differently), and only
    # from the held-out sets, so a rewrite never shadows a worked example.
    pool = [c for c in data["cases"] if c.get("reference") and str(c.get("split", "")).startswith("held_out")]
    rng = random.Random(args.seed)
    picked = rng.sample(pool, min(args.cases, len(pool)))

    out, spent = [], 0.0
    for case in picked:
        if spent >= args.budget:
            print(f"budget of ${args.budget:.2f} reached after {len(out)} rewrites")
            break
        styles = rng.sample(STYLES, args.styles)
        msg = PROMPT.format(typed=case["typed"], n=len(styles),
                            styles="\n".join(f"{i + 1}. {s}" for i, s in enumerate(styles)))
        try:
            resp = client.messages.create(model=settings.llm_model, max_tokens=600, temperature=1,
                                          messages=[{"role": "user", "content": msg}])
        except Exception as exc:  # noqa: BLE001
            print(f"{case['id']}: API call failed ({exc}); skipped")
            continue
        spent += (resp.usage.input_tokens * PRICE_IN + resp.usage.output_tokens * PRICE_OUT) / 1e6
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        try:
            rewrites = json.loads(text[text.index("["): text.rindex("]") + 1])
        except ValueError:
            print(f"{case['id']}: unreadable answer; skipped")
            continue
        for i, typed in enumerate(r for r in rewrites if isinstance(r, str) and r.strip()):
            new = {"id": f"P{case['id']}{chr(97 + i)}", "split": "paraphrase", "typed": typed.strip(),
                   "reference": case["reference"], "from": case["id"]}
            for key in ("also", "strength", "expect"):
                if key in case:
                    new[key] = case[key]
            out.append(new)
            print(f"{new['id']:8} {new['typed']}")

    data["cases"] = [c for c in data["cases"] if c.get("split") != "paraphrase"] + out
    CASES.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"\n{len(out)} rewrites saved (split 'paraphrase'). Spent ${spent:.3f}.")
    print("Skim them: delete any that changed the meaning, then run")
    print("    python scripts/eval_rule_behaviour.py --split paraphrase")


if __name__ == "__main__":
    main()

"""
Rule messages with known meanings, for scoring how rules are read.

    python scripts/import_corpus/rules_corpus.py     # -> school-imports/generated/rules/

For each made-up school (schools/*.json, from generate.py) a dozen messages
the way coordinators send them: a WhatsApp forward with its timestamp, a
greeting and a sign-off, numbered or bulleted or one paragraph, several rules
in one line ("Priya is off on Monday and can't take more than 4 a day"),
clock times instead of period numbers ("leaves at 12.40", "no PE after
1:20 pm"), day ranges ("Mon to Wed"). Every rule's meaning is in
expected.json as facts the scorer can check whatever words the parser used:

    teacher_unavailable   {teacher, slots: [{day, periods}]}
    subject_not_in_period {subject, periods}            (every day)
    teacher_max_per_day   {teacher, value}

plus "units": how many separate rules the message holds, and "clock": each
clock time written and the periods it should be read as.

Separate from generate.py (its own seed and folder) so the main corpus, and
every saved score of it, stays exactly as it was.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SHORT = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri",
         "Saturday": "Sat"}


def _mins(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _clock(rng, t: str) -> str:
    """"12:40" as a person types it: 12:40, 12.40, 12:40 pm, 12.40pm."""
    h, m = (int(x) for x in t.split(":"))
    h12 = h - 12 if h > 12 else h
    suffix = "pm" if h >= 12 else "am"
    return rng.choice([f"{h12}:{m:02d}", f"{h12}.{m:02d}", f"{h12}:{m:02d} {suffix}", f"{h12}.{m:02d}{suffix}"])


class Maker:
    def __init__(self, rng: random.Random, truth: dict):
        self.rng, self.t = rng, truth
        self.days = truth["days"]
        self.n = truth["periods_per_day"]
        self.starts = [b.split("-")[0] for b in truth["bell_times"]]
        self.lunch = next((b["after_period"] for b in truth["breaks"] if "Lunch" in b["name"]), self.n // 2)

    def name(self, teacher: dict) -> str:
        t = teacher
        style = self.rng.choice(["plain", "titled", "first", "caps"])
        if style == "titled":
            return f"{t['title']} {t['name']}"
        if style == "first":
            return t["name"].split()[0]
        if style == "caps":
            return t["name"].upper()
        return t["name"]

    def days_text(self, ds: list[str]) -> str:
        r = self.rng.random()
        idx = [self.days.index(d) for d in ds]
        if len(ds) >= 3 and idx == list(range(idx[0], idx[-1] + 1)) and r < 0.4:
            a, b = SHORT[ds[0]], SHORT[ds[-1]]
            return self.rng.choice([f"{a} to {b}", f"{a}-{b}", f"{ds[0]} to {ds[-1]}"])
        short = r < 0.7
        names = [SHORT[d] if short else d for d in ds]
        return ", ".join(names[:-1]) + self.rng.choice([" and ", " & "]) + names[-1] if len(names) > 1 else names[0]

    # Each returns (text with {T}/{S} filled, fact, clock entries)
    def only_days(self, t, nm):
        ds = sorted(self.rng.sample(self.days, k=min(3, len(self.days) - 1)), key=self.days.index)
        text = self.rng.choice([f"{nm} can take classes only on {self.days_text(ds)}",
                                f"{nm} comes only on {self.days_text(ds)}",
                                f"{nm} - only {self.days_text(ds)}"])
        off = [d for d in self.days if d not in ds]
        return text, {"type": "teacher_unavailable", "teacher": t["name"],
                      "slots": [{"day": d, "periods": list(range(1, self.n + 1))} for d in off]}, []

    def off_day(self, t, nm):
        d = self.rng.choice(self.days)
        dn = self.rng.choice([d, SHORT[d], d + "s"])
        text = self.rng.choice([f"{nm} is off on {dn}", f"{nm} won't be available on {dn}",
                                f"no classes for {nm} on {dn}"])
        return text, {"type": "teacher_unavailable", "teacher": t["name"],
                      "slots": [{"day": d, "periods": list(range(1, self.n + 1))}]}, []

    def leaves(self, t, nm):
        if self.rng.random() < 0.4:
            k = self.lunch
            text = f"{nm} leaves after lunch every day"
            clock = []
        else:
            k = self.rng.randint(max(2, self.n // 2), self.n - 1)
            tm = _clock(self.rng, self.starts[k])     # the start of period k+1
            text = self.rng.choice([f"{nm} leaves at {tm}", f"{nm} has to leave by {tm} every day"])
            clock = [{"text": tm, "periods_after": list(range(k + 1, self.n + 1))}]
        return text, {"type": "teacher_unavailable", "teacher": t["name"],
                      "slots": [{"day": d, "periods": list(range(k + 1, self.n + 1))} for d in self.days]}, clock

    def arrives(self, t, nm):
        k = self.rng.randint(1, 3)                     # free for periods 1..k
        tm = _clock(self.rng, self.starts[k])
        text = self.rng.choice([f"{nm} comes only at {tm}", f"{nm} can't take classes before {tm}",
                                f"{nm} reaches school by {tm} only"])
        return text, {"type": "teacher_unavailable", "teacher": t["name"],
                      "slots": [{"day": d, "periods": list(range(1, k + 1))} for d in self.days]}, \
            [{"text": tm, "periods_before": list(range(1, k + 1))}]

    def part_time(self, t, nm):
        d1, d2 = self.rng.sample(self.days, k=2)
        text = f"{nm} is part time - not available {self.rng.choice([d1, SHORT[d1]])} morning and " \
               f"{self.rng.choice([d2, SHORT[d2]])} afternoon"
        return text, {"type": "teacher_unavailable", "teacher": t["name"],
                      "slots": [{"day": d1, "periods": list(range(1, self.lunch + 1))},
                                {"day": d2, "periods": list(range(self.lunch + 1, self.n + 1))}]}, []

    def max_day(self, t, nm):
        v = self.rng.choice([4, 5, 6])
        text = self.rng.choice([f"{nm} should not have more than {v} periods a day",
                                f"max {v} periods per day for {nm}", f"not more than {v} classes a day for {nm}"])
        return text, {"type": "teacher_max_per_day", "teacher": t["name"], "value": v}, []

    def no_last(self, s):
        text = self.rng.choice([f"no {s} in the last period", f"{s} should not be in the last period",
                                f"avoid {s} last period"])
        return text, {"type": "subject_not_in_period", "subject": s, "periods": [self.n]}, []

    def no_first(self, s):
        text = self.rng.choice([f"no {s} in the first period", f"{s} not in period 1"])
        return text, {"type": "subject_not_in_period", "subject": s, "periods": [1]}, []

    def subject_after(self, s):
        k = self.rng.randint(self.n // 2, self.n - 1)
        tm = _clock(self.rng, self.starts[k])
        text = self.rng.choice([f"no {s} after {tm}", f"{s} only before {tm}"])
        return text, {"type": "subject_not_in_period", "subject": s, "periods": list(range(k + 1, self.n + 1))}, \
            [{"text": tm, "periods_after": list(range(k + 1, self.n + 1))}]


TEACHER_KINDS = ["only_days", "off_day", "leaves", "arrives", "part_time", "max_day"]
SUBJECT_KINDS = ["no_last", "no_first", "subject_after"]
# A second rule for the same teacher in one line, the subject left out.
CARRY = {"off_day": "and can't take more than {v} periods a day", "only_days": "and leaves after lunch"}


def message(rng: random.Random, truth: dict, case: int) -> tuple[str, dict]:
    mk = Maker(rng, truth)
    teachers = [t for t in truth["teachers"]]
    subjects = sorted({p["subject"] for p in truth["plan"]} - {"Class Teacher Period"})
    picked = rng.sample(teachers, k=min(len(teachers), rng.randint(3, 5)))
    units, facts, clocks, written = [], [], [], {"teachers": {}, "subjects": {}}
    for t in picked:
        kind = rng.choice(TEACHER_KINDS)
        nm = mk.name(t)
        written["teachers"].setdefault(t["name"], []).append(nm)
        text, fact, clock = getattr(mk, kind)(t, nm)
        facts.append(fact)
        clocks += clock
        # Sometimes a second rule rides on the same line without the name.
        if kind in CARRY and rng.random() < 0.35:
            v = rng.choice([4, 5])
            extra = CARRY[kind].format(v=v)
            text += " " + extra
            if "leaves" in extra:
                facts.append({"type": "teacher_unavailable", "teacher": t["name"],
                              "slots": [{"day": d, "periods": list(range(mk.lunch + 1, mk.n + 1))} for d in mk.days]})
            else:
                facts.append({"type": "teacher_max_per_day", "teacher": t["name"], "value": v})
            units.append([text])   # one line, two rules
            continue
        units.append([text])
    for s in rng.sample(subjects, k=rng.randint(1, 2)):
        kind = rng.choice(SUBJECT_KINDS)
        text, fact, clock = getattr(mk, kind)(s)
        written["subjects"].setdefault(s, []).append(s)
        facts.append(fact)
        clocks += clock
        units.append([text])
    # Two separate rules joined on one line.
    lines = [u[0] for u in units]
    if len(lines) >= 4 and rng.random() < 0.5:
        i = rng.randrange(len(lines) - 1)
        lines[i:i + 2] = [lines[i] + rng.choice(["; ", ". Also ", ", and "]) + lines[i + 1]]
    rng.shuffle(lines)
    style = rng.choice(["numbered", "bracket", "bullets", "plain", "paragraph"])
    if style == "numbered":
        body = [f"{i}. {ln[0].upper() + ln[1:]}" for i, ln in enumerate(lines, start=1)]
    elif style == "bracket":
        body = [f"{i}) {ln}" for i, ln in enumerate(lines, start=1)]
    elif style == "bullets":
        body = [f"{rng.choice(['-', '•', '*'])} {ln}" for ln in lines]
    elif style == "plain":
        body = [ln[0].upper() + ln[1:] for ln in lines]
    else:
        body = [". ".join(ln[0].upper() + ln[1:] for ln in lines) + "."]
    head = rng.choice(["Good eve sir.", "Hello sir,", "Dear Sir/Madam,", "Sir pls note the following for next "
                       "year's TT:", "Respected Sir, please find the requests below", ""])
    tail = rng.choice(["Thank you", "Thanks 🙏", "Regards,\nCoordinator", "Sent from my iPhone", ""])
    text = "\n".join(x for x in [head, *body, tail] if x)
    if rng.random() < 0.4:
        text = f"[{rng.randint(1, 28)}/0{rng.randint(1, 9)}/25, {rng.randint(1, 11)}:{rng.randint(10, 59)} am] " \
               f"{rng.choice(['Principal', 'Coordinator', 'Vice Principal'])}: " + text
    return text, {"facts": facts, "units": len(facts), "clock": clocks, "written": written, "style": style}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, default=ROOT / "school-imports" / "generated")
    ap.add_argument("--per-school", type=int, default=12)
    ap.add_argument("--seed", type=int, default=5)
    args = ap.parse_args(argv)
    out = args.corpus / "rules"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rng = random.Random(args.seed)
    n = 0
    for path in sorted((args.corpus / "schools").glob("*.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        for i in range(1, args.per_school + 1):
            text, exp = message(random.Random(rng.randint(0, 10**9)), truth, i)
            cid = f"{path.stem}_rules_{i:02d}"
            (out / cid).mkdir()
            (out / cid / "input.txt").write_text(text, encoding="utf-8")
            exp.update(id=cid, school=f"schools/{path.name}")
            (out / cid / "expected.json").write_text(json.dumps(exp, indent=1, ensure_ascii=False), encoding="utf-8")
            n += 1
    print(f"{n} rule messages in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

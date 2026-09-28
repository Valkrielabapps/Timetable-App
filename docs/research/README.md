# Research

Product research feeding design decisions, kept in the repo so both of us work
from the same data and it survives past whoever collected it.

## What's here

| File | What it is |
|---|---|
| `Timetablz_merged_rules.tsv` | The raw merge, as collected. Source of truth for the text |
| `constraint-catalogue.tsv` | 187 weekly rules, one per row, with a verdict on whether the app can express each one |
| `constraint-traps.tsv` | 32 sentences that parse wrong, and what the right reading is |
| `build_catalogue.py` | Regenerates both from the raw merge. Holds the verdicts |

Regenerate after changing a verdict:

```
python docs/research/build_catalogue.py
```

## Where we actually stand

Of the 187 rules, 10 are setup data (belong on the Data tab) and 7 aren't
weekly rules at all (swap/lock/substitute). That leaves **170 real scheduling
rules**, and of those:

| Verdict | Count | Meaning |
|---|---:|---|
| `EXPRESSIBLE` | 21 | A constraint type says exactly this |
| `PARTIAL` | 5 | A type says a weaker or wider version |
| `MISSING` | 144 | Needs a capability that doesn't exist |

**So roughly one rule in seven survives the trip from a sentence to the
solver.** The other six are recorded, shown in the UI, and never applied.

That number is the reason this folder exists. It isn't a parser problem — the
LLM understands these sentences fine. It's that there are nine constraint types
between the parser and the solver, and a principal's vocabulary is much wider
than nine.

### What the missing 144 need, ranked

| Capability | Rules | What it covers |
|---|---:|---|
| `M9-rooms` | 19 | Room availability, capacity, shared spaces, equipment counts, movement between blocks |
| `M11-conditional-meta` | 17 | If-then across days, either/or, exceptions, rule priorities, budgeted violations |
| `M8-parallel` | 16 | Same-slot coordination: combined sections, electives, grade-wide subjects, staff meetings, co-teaching |
| `M2-daily-load` | 15 | Per-day counts for a teacher or a class — max/min periods, free periods, distinct subjects |
| `M5-day-spread` | 12 | Same/different day pairing, alternate days, even spread, fixed daily slot |
| `M4-period-window` | 12 | A subject at period N, or within a window (before lunch, after the break) |
| `M10-calendar` | 12 | Date ranges, term-limited rules, leave, exam weeks, day-order cycles |
| `M6-blocks-adjacency` | 11 | Required doubles, where a double may start, blocks not split by lunch |
| `M7-assignment` | 10 | Who may teach whom — grade limits, section caps, continuity |
| `M3-weekly-shape` | 7 | Minimum weekly load, compact days, idle gaps, fairness across the week |
| `M1-slot-availability` | 7 | Reserved slots for a class or activity (the teacher half of this now works) |
| `M12-cohort` | 6 | Student subgroups inside a section |

Ranked by count, not by cost. `M9-rooms` leads the list but is the most
expensive: rooms are assigned in a separate pass *after* the schedule is fixed
(`_assign_rooms` in `backend/app/services/solver.py`), so no room rule can be a
hard constraint without moving rooms into the main model. `M2` and `M4`, lower
down, are close to what the solver already does.

## Measuring the parser

`backend/scripts/eval_constraint_parser.py` runs the catalogue through the real
parser and reports two numbers:

- **Recall on expressible** — of the rules the solver *can* enforce, how many
  reached the right type. This is the parser's score.
- **Honesty on the rest** — of the rules it *can't*, how many were correctly
  left as `scheduling_rule`. A rule forced into a type that half-fits is worse
  than one that's dropped: it silently changes the timetable and reports itself
  as enforced.

```
cd backend
python scripts/eval_constraint_parser.py            # all 170, a few cents
python scripts/eval_constraint_parser.py --limit 20 --verbose
```

It makes one API call per rule, so it's a script you run deliberately before
and after a prompt change — not a test.

## constraint-catalogue.tsv

| Column | Meaning |
|---|---|
| `ID` | Stable row id (`R001`…). Cite these in commits and issues |
| `TYPED` | Exactly as a user would type it — messy, abbreviated, typos kept |
| `MEANT` | What they actually meant, stated precisely |
| `KIND` | `HARD` (timetable invalid without it) or `PREFERENCE` (try, may break) |
| `CATEGORY` | Rough grouping — rooms, teacher load, day shape, etc. |
| `VERDICT` | `EXPRESSIBLE` / `PARTIAL` / `MISSING` / `SETUP` / `NOT-A-RULE` |
| `CAPABILITY` | The constraint type that covers it, or the missing capability |
| `SOURCE` | Where the row came from |

## constraint-traps.tsv

Sentences where the reading forks and the obvious branch is wrong. `'Only'
flips meaning` is the sharpest: "Arjun only comes on Monday" read as an
availability rule *for* Monday is the exact opposite of what was said.

The traps whose right answer is the same in every school are compiled into the
parser prompt — see `_READING_RULES` in
`backend/app/services/llm_constraint_parser.py`. The ones that depend on the
school ("juniors" = which grades?) are deliberately left out; those belong in
an ask-the-user path, not in a prompt that would have to guess.

## Adding rules

Append to the raw TSV, add a verdict in `build_catalogue.py`, re-run it. A rule
that's already in the file in a different phrasing is still worth adding — the
phrasings are half the data.

**No real staff names.** Use "Teacher A". The rule shapes are the point; the
names are a real school's employee data and carry nothing useful.

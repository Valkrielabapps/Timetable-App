"""Rebuild constraint-catalogue.tsv and constraint-traps.tsv from the raw merge.

Run from the repo root:  python docs/research/build_catalogue.py

Timetablz_merged_rules.tsv is the raw artefact - Allen's catalogue, the
principal set and the synthetic rules merged, with section headers left
interleaved among the data rows, which is fine for reading and useless for
counting. This splits it into the weekly rules and the problem cases, gives
every row a stable id, and records the one thing the raw file doesn't: whether
the app can express that rule today.

VERDICT is the point of the file:

  EXPRESSIBLE   one of the parser's constraint types says exactly this
  PARTIAL       a type says a weaker or wider version of it
  MISSING       needs a capability that does not exist; CAPABILITY names which
  SETUP         belongs on the Data tab, not the constraint parser
  NOT-A-RULE    an edit command or a substitution decision, not a weekly rule

The verdicts live in this file rather than in the TSV so that adding a
capability is a two-line edit here followed by a re-run, instead of hand-editing
187 rows and hoping none were missed. When a capability lands, move its rules
and re-run - the counts in README.md come straight out of this.
"""
import csv, pathlib

RAW = pathlib.Path("docs/research/Timetablz_merged_rules.tsv")
OUT_RULES = pathlib.Path("docs/research/constraint-catalogue.tsv")
OUT_TRAPS = pathlib.Path("docs/research/constraint-traps.tsv")

# Verdict per raw line number. EXPRESSIBLE names the existing type that
# covers it; MISSING names the capability group that would be needed.
V = {}
def mark(verdict, capability, *lines):
    for n in lines:
        V[n] = (verdict, capability)

# Availability covers whole days, specific periods, or specific periods on a
# named day (Teacher.unavailable_period_ids + ParsedConstraint.period_orders).
mark("EXPRESSIBLE", "availability", 3, 5, 7, 11, 21)
mark("EXPRESSIBLE", "workload_limit", 12)
mark("EXPRESSIBLE", "max_consecutive_periods", 16, 51, 52)
mark("EXPRESSIBLE", "subject_period_position", 31, 32, 33, 34)
mark("EXPRESSIBLE", "subject_day_position", 42, 43)
mark("EXPRESSIBLE", "max_subject_periods_per_day", 45, 46)
mark("EXPRESSIBLE", "subject_sequence", 56)
mark("EXPRESSIBLE", "min_gap_between_subjects", 58, 59)
mark("EXPRESSIBLE", "strength", 90)

# R004 and R006 name a clock time and "mornings". Both resolve only if the
# school happens to label its periods with times; the Period row has no
# start/end column, so nothing else can map 12:30 to a period number.
mark("PARTIAL", "availability", 4, 6, 8)
mark("PARTIAL", "subject_day_position", 44)
mark("PARTIAL", "workload_limit", 95)

mark("SETUP", "data-tab", 24, 50, 70, 74, 81, 82, 83, 84, 85, 94)
mark("NOT-A-RULE", "edit-command", 96, 97, 98)
mark("NOT-A-RULE", "substitution", 183, 184, 185, 186)

mark("MISSING", "M1-slot-availability", 9, 66, 72, 89, 99, 100, 101)
mark("MISSING", "M2-daily-load", 14, 15, 17, 22, 47, 62, 63, 64, 65, 109, 111, 112, 126, 127, 130)
mark("MISSING", "M3-weekly-shape", 13, 18, 19, 20, 23, 108, 129)
mark("MISSING", "M4-period-window", 35, 36, 37, 38, 39, 41, 102, 105, 106, 107, 122, 128)
mark("MISSING", "M5-day-spread", 40, 48, 49, 60, 61, 103, 118, 119, 121, 123, 124, 125)
mark("MISSING", "M6-blocks-adjacency", 53, 54, 55, 57, 104, 113, 114, 115, 116, 117, 120)
mark("MISSING", "M7-assignment", 25, 26, 27, 29, 30, 150, 151, 152, 153, 154)
mark("MISSING", "M8-parallel", 28, 67, 68, 69, 71, 86, 87, 88, 110, 131, 132, 133, 134, 135, 136, 137)
mark("MISSING", "M9-rooms", 73, 75, 76, 77, 78, 79, 80, 138, 139, 140, 141, 142, 143, 144,
     145, 146, 147, 148, 149)
mark("MISSING", "M10-calendar", 10, 93, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168)
mark("MISSING", "M11-conditional-meta", 91, 92, 155, 156, 157, 158, 169, 170, 171, 172, 173,
     174, 175, 176, 187, 188, 189)
mark("MISSING", "M12-cohort", 177, 178, 179, 180, 181, 182)

rows = list(csv.reader(RAW.open(encoding="utf-8-sig"), delimiter="\t"))

rules, traps = [], []
for n, row in enumerate(rows, start=1):
    row = row + [""] * (7 - len(row))
    if 3 <= n <= 189:
        if not row[0].strip():
            continue
        verdict, capability = V.get(n, ("UNCLASSIFIED", ""))
        rules.append([f"R{n - 2:03d}", row[0], row[1], row[2], row[3], verdict, capability, row[6]])
    elif 210 <= n <= 241:
        if not row[0].strip():
            continue
        traps.append([f"T{n - 209:03d}", row[0], row[1], row[2], row[3], row[4]])

with OUT_RULES.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["ID", "TYPED", "MEANT", "KIND", "CATEGORY", "VERDICT", "CAPABILITY", "SOURCE"])
    w.writerows(rules)

with OUT_TRAPS.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["ID", "TYPED", "PROBLEM", "WHY", "RIGHT HANDLING", "SOURCE"])
    w.writerows(traps)

missing = [r for r in rules if r[5] == "UNCLASSIFIED"]
print(f"rules={len(rules)} traps={len(traps)} unclassified={len(missing)}")
for r in missing:
    print("  UNCLASSIFIED:", r[0], r[1][:70])

"""
Read-only diagnostic: dumps everything the solver looks at for every
school in the database, and flags common reasons generation would be
infeasible:

  - a class group whose total periods/week (summed across its subject
    requirements) exceeds the number of periods that exist
  - more than one class group with the same name/grade (a possible sign
    of an accidental duplicate section)
  - a subject requirement with zero qualified teachers
  - a teacher whose combined periods/week across all their subjects
    exceeds their own max_periods_per_week

Doesn't change anything - safe to run anytime, including while the
backend server is running.

Usage (from the backend/ folder, with your venv active):
    python diagnose_timetable.py
"""
import sqlite3
import sys
from collections import defaultdict

DB_PATH = "dev.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    schools = cur.execute("SELECT * FROM schools").fetchall()
    if not schools:
        print("No schools found.")
        return

    for school in schools:
        print(f"\n{'=' * 60}")
        print(f"School: {school['name']} (id={school['id']})")
        print(f"{'=' * 60}")

        periods = cur.execute(
            "SELECT * FROM periods WHERE school_id = ?", (school["id"],)
        ).fetchall()
        print(f"\nPeriods: {len(periods)} total")

        subjects = {
            s["id"]: s["name"]
            for s in cur.execute(
                "SELECT * FROM subjects WHERE school_id = ?", (school["id"],)
            ).fetchall()
        }

        teachers = cur.execute(
            "SELECT * FROM teachers WHERE school_id = ?", (school["id"],)
        ).fetchall()
        print(f"Teachers: {len(teachers)}")
        for t in teachers:
            import json
            qualified = json.loads(t["qualified_subject_ids"] or "[]")
            qualified_names = [subjects.get(sid, f"#{sid}") for sid in qualified]
            max_pw = t["max_periods_per_week"]
            print(
                f"  - {t['name']}: qualified for {qualified_names or '(none!)'}"
                f"{f', max {max_pw}/week' if max_pw else ''}"
            )

        class_groups = cur.execute(
            "SELECT * FROM class_groups WHERE school_id = ?", (school["id"],)
        ).fetchall()

        # Flag possible accidental duplicate sections.
        seen = defaultdict(list)
        for cg in class_groups:
            seen[(cg["grade"], cg["name"])].append(cg["id"])
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        if dupes:
            print("\n*** POSSIBLE DUPLICATE SECTIONS (same grade+name, different IDs): ***")
            for (grade, name), ids in dupes.items():
                print(f"  {grade} / Section {name}: class_group ids {ids}")

        teacher_totals = defaultdict(int)
        teacher_names = {t["id"]: t["name"] for t in teachers}

        for cg in class_groups:
            print(f"\nClass group: {cg['grade']} / Section {cg['name']} (id={cg['id']})")
            reqs = cur.execute(
                "SELECT * FROM subject_requirements WHERE class_group_id = ?", (cg["id"],)
            ).fetchall()
            total_periods_needed = 0
            for r in reqs:
                subj_name = subjects.get(r["subject_id"], f"#{r['subject_id']}")
                total_periods_needed += r["periods_per_week"]

                qualified_teacher_ids = []
                for t in teachers:
                    import json
                    if r["subject_id"] in json.loads(t["qualified_subject_ids"] or "[]"):
                        qualified_teacher_ids.append(t["id"])
                        teacher_totals[t["id"]] += r["periods_per_week"] / max(len(qualified_teacher_ids), 1)

                flag = " <-- NO QUALIFIED TEACHER" if not qualified_teacher_ids else ""
                if subj_name.startswith("#"):
                    flag += " <-- ORPHANED (subject was deleted; run dedupe_orphaned_requirements.py)"
                print(f"  - {subj_name}: {r['periods_per_week']}/week{flag}")

            status = "OK" if total_periods_needed <= len(periods) else "*** EXCEEDS AVAILABLE PERIODS ***"
            print(f"  Total periods needed: {total_periods_needed} / {len(periods)} available -- {status}")

        print("\nTeacher workload (rough estimate, split evenly if multiple teachers share a subject):")
        overloaded = False
        for t in teachers:
            approx_load = teacher_totals.get(t["id"], 0)
            max_pw = t["max_periods_per_week"]
            if max_pw and approx_load > max_pw:
                print(f"  *** {t['name']}: ~{approx_load:.1f} periods needed but capped at {max_pw}/week ***")
                overloaded = True
            elif approx_load:
                print(f"  {t['name']}: ~{approx_load:.1f} periods/week")
        if not overloaded and not dupes:
            print("\nNo obvious data problem found by this script - the actual solver "
                  "constraints may be more subtle (e.g. a teacher's specific "
                  "unavailable periods clashing with when they're needed).")

    conn.close()


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as e:
        print(f"Could not open {DB_PATH}: {e}")
        print("Make sure you're running this from the backend/ folder.")
        sys.exit(1)

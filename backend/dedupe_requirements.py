"""
One-off cleanup script: removes duplicate subject_requirements rows caused
by a since-fixed frontend race condition (see DataEntryTab.jsx and
app/routers/class_groups.py for the fix).

For each (class_group_id, subject_id) pair with more than one row, this
keeps the MOST RECENTLY UPDATED one (highest id, since rows are only ever
inserted or updated in place) and deletes the rest.

Usage (from the backend/ folder, with your venv active):
    python dedupe_requirements.py

Safe to run multiple times - if there are no duplicates, it does nothing.
Stop the backend server first so nothing else is writing to dev.db while
this runs.
"""
import sqlite3
import sys

DB_PATH = "dev.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT class_group_id, subject_id, COUNT(*) as cnt
        FROM subject_requirements
        GROUP BY class_group_id, subject_id
        HAVING cnt > 1
    """)
    duplicates = cur.fetchall()

    if not duplicates:
        print("No duplicates found. Nothing to do.")
        return

    print(f"Found {len(duplicates)} subject(s) with duplicate requirement rows:\n")

    total_deleted = 0
    for class_group_id, subject_id, count in duplicates:
        cur.execute("""
            SELECT id, periods_per_week FROM subject_requirements
            WHERE class_group_id = ? AND subject_id = ?
            ORDER BY id
        """, (class_group_id, subject_id))
        rows = cur.fetchall()

        keep_id = rows[-1][0]  # highest id = most recently created/updated
        delete_ids = [r[0] for r in rows[:-1]]

        print(
            f"  class_group_id={class_group_id} subject_id={subject_id}: "
            f"{count} rows {rows} -> keeping id={keep_id}, deleting {delete_ids}"
        )

        cur.executemany(
            "DELETE FROM subject_requirements WHERE id = ?",
            [(i,) for i in delete_ids],
        )
        total_deleted += len(delete_ids)

    conn.commit()
    conn.close()
    print(f"\nDone. Deleted {total_deleted} duplicate row(s).")


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as e:
        print(f"Could not open {DB_PATH}: {e}")
        print("Make sure you're running this from the backend/ folder, "
              "and that the backend server is stopped (Ctrl+C) first.")
        sys.exit(1)

"""
One-off cleanup script: removes subject_requirements rows that point at a
subject_id which no longer exists in the subjects table.

Root cause (now fixed in app/routers/subjects.py): deleting a subject used
to leave its requirement rows behind instead of cleaning them up. Those
orphaned rows are invisible in Data Entry (it only lists requirements for
subjects that still exist) but the solver still sums every requirement row
for a class group as real demand - so an orphan silently inflates a
section's periods/week total and can make generation infeasible for no
visible reason (a "needs 80 periods/week but the school only has 40"-style
error with no obvious cause in the UI).

Usage (from the backend/ folder, with your venv active, SERVER STOPPED):
    python dedupe_orphaned_requirements.py

Safe to run multiple times - if there are no orphans, it does nothing.
IMPORTANT: stop the backend server (Ctrl+C) first. Editing dev.db while
something else has it open is unreliable - writes can silently get lost
or reverted, especially if the project folder is synced by OneDrive.
"""
import sqlite3
import sys

DB_PATH = "dev.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id FROM subjects")
    valid_ids = {r[0] for r in cur.fetchall()}

    cur.execute("SELECT id, class_group_id, subject_id, periods_per_week FROM subject_requirements")
    all_rows = cur.fetchall()
    orphans = [r for r in all_rows if r[2] not in valid_ids]

    if not orphans:
        print("No orphaned requirement rows found. Nothing to do.")
        return

    print(f"Found {len(orphans)} orphaned requirement row(s):\n")
    for row_id, cg_id, subject_id, periods in orphans:
        print(f"  id={row_id} class_group_id={cg_id} subject_id={subject_id} (deleted) periods_per_week={periods}")

    cur.executemany("DELETE FROM subject_requirements WHERE id = ?", [(r[0],) for r in orphans])
    conn.commit()

    # Verify the write actually landed before declaring victory.
    cur.execute("SELECT COUNT(*) FROM subject_requirements WHERE subject_id NOT IN (SELECT id FROM subjects)")
    remaining = cur.fetchone()[0]
    conn.close()

    if remaining == 0:
        print(f"\nDone. Deleted {len(orphans)} orphaned row(s) and verified none remain.")
    else:
        print(f"\nWARNING: {remaining} orphaned row(s) still remain after the delete+commit. "
              f"This usually means something else has dev.db open (the backend server, or a "
              f"sync client). Fully stop the backend, wait a few seconds, and run this again.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except sqlite3.OperationalError as e:
        print(f"Could not open/write {DB_PATH}: {e}")
        print("Make sure you're running this from the backend/ folder, that the backend "
              "server is fully stopped, and that no sync client (OneDrive) is mid-sync.")
        sys.exit(1)

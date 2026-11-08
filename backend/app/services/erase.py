"""
Deleting a school or a user account for good, from the admin page.

Everything that belongs to it goes - sections, teachers, subjects, rooms,
periods, rules, timetables, memberships, invites, offers, logs - found by
following the database's own foreign keys, so a table added later is
covered without changing this file. A few records are kept on purpose,
with the link to what was deleted cleared:

  invoices, payment_orders  tax law requires keeping payment records
  terms_acceptances         the proof of what someone agreed to

Anything else that merely points at a deleted row through an optional
column (an invite "sent by" a deleted user, an offer "created by" one) is
kept with that column cleared - unless the column says ON DELETE CASCADE
(problem reports and rule-reading logs about a school), which goes with it.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select, update, delete
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import outreach, payment, problems, school, user  # noqa: F401 - registers every table

KEEP = {"invoices", "payment_orders", "terms_acceptances"}


def _tables():
    return {t.name: t for t in Base.metadata.sorted_tables}


def _referencing(table_name):
    """(child table, its column, nullable) for every foreign key to `table_name`."""
    out = []
    for t in Base.metadata.sorted_tables:
        for fk in t.foreign_keys:
            if fk.column.table.name == table_name:
                out.append((t, fk.parent, fk.parent.nullable, (fk.ondelete or "").upper()))
    return out


def plan(db: Session, table_name: str, ids: list[int]) -> tuple[dict, list]:
    """What deleting these rows takes: {table: ids to delete} and the
    (table, column, ids) references to clear instead."""
    to_delete: dict[str, set] = defaultdict(set)
    to_delete[table_name] |= set(ids)
    clear: list = []
    queue = [(table_name, set(ids))]
    while queue:
        name, new_ids = queue.pop()
        if not new_ids:
            continue
        for child, col, nullable, ondelete in _referencing(name):
            # Logs declared to go with what they log (ON DELETE CASCADE) go,
            # even through an optional column - a problem report holds a copy
            # of the school's setup.
            if child.name in KEEP or (nullable and ondelete != "CASCADE"):
                clear.append((child, col, set(new_ids)))
                continue
            if "id" not in child.c:
                continue  # a link table with no id: removed by condition below
            found = {r for (r,) in db.execute(select(child.c.id).where(col.in_(new_ids)))}
            fresh = found - to_delete[child.name]
            if fresh:
                to_delete[child.name] |= fresh
                queue.append((child.name, fresh))
    return dict(to_delete), clear


def erase(db: Session, table_name: str, ids: list[int]) -> dict[str, int]:
    """Delete the rows and everything that depends on them. Returns how many
    rows went from each table. Commits."""
    tables = _tables()
    to_delete, clear = plan(db, table_name, ids)
    # Keep what must be kept, and break every optional link first, so the
    # order of the deletes below never trips a foreign key.
    for child, col, ref_ids in clear:
        db.execute(update(child).where(col.in_(ref_ids)).values({col.name: None}))
    for name, row_ids in to_delete.items():
        t = tables[name]
        for fk in t.foreign_keys:
            if fk.parent.nullable and name not in KEEP:
                db.execute(update(t).where(t.c.id.in_(row_ids)).values({fk.parent.name: None}))
    counts: dict[str, int] = {}
    for t in reversed(Base.metadata.sorted_tables):
        # Link tables without an id go with whatever they link.
        if "id" not in t.c:
            for fk in t.foreign_keys:
                gone = to_delete.get(fk.column.table.name)
                if gone:
                    res = db.execute(delete(t).where(fk.parent.in_(gone)))
                    counts[t.name] = counts.get(t.name, 0) + (res.rowcount or 0)
            continue
        row_ids = to_delete.get(t.name)
        if row_ids:
            res = db.execute(delete(t).where(t.c.id.in_(row_ids)))
            counts[t.name] = res.rowcount or 0
    db.commit()
    return {k: v for k, v in counts.items() if v}

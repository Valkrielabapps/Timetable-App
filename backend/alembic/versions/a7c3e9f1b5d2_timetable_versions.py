"""Timetable versions: which one is current, their names and numbers, and the
version a frozen section is kept from

Revision ID: a7c3e9f1b5d2
Revises: f2b6d8a4c1e9
Create Date: 2026-10-27 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c3e9f1b5d2'
down_revision: Union[str, None] = 'f2b6d8a4c1e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('current_timetable_id', sa.Integer(), nullable=True))
    op.add_column('timetables', sa.Column('name', sa.String(length=80), nullable=True))
    op.add_column('timetables', sa.Column('version_number', sa.Integer(), nullable=True))
    op.add_column('class_groups', sa.Column('frozen_from_timetable_id', sa.Integer(), nullable=True))

    conn = op.get_bind()
    # Number existing timetables 1, 2, 3... per school, in the order they were made.
    rows = conn.execute(sa.text("SELECT id, school_id FROM timetables ORDER BY school_id, id")).fetchall()
    counter: dict = {}
    for tid, sid in rows:
        counter[sid] = counter.get(sid, 0) + 1
        conn.execute(sa.text("UPDATE timetables SET version_number = :n WHERE id = :id"), {"n": counter[sid], "id": tid})
    # The current version is the newest successful one, as the app showed before.
    latest = conn.execute(sa.text(
        "SELECT school_id, MAX(id) FROM timetables WHERE status IN ('draft', 'published') GROUP BY school_id"
    )).fetchall()
    for sid, tid in latest:
        conn.execute(sa.text("UPDATE schools SET current_timetable_id = :t WHERE id = :s"), {"t": tid, "s": sid})
        # Sections already frozen were frozen from what was on screen: that one.
        conn.execute(sa.text(
            "UPDATE class_groups SET frozen_from_timetable_id = :t WHERE school_id = :s AND frozen"
        ), {"t": tid, "s": sid})


def downgrade() -> None:
    op.drop_column('class_groups', 'frozen_from_timetable_id')
    op.drop_column('timetables', 'version_number')
    op.drop_column('timetables', 'name')
    op.drop_column('schools', 'current_timetable_id')

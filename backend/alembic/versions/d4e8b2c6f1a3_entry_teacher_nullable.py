"""timetable_entries.teacher_id nullable - lessons with no teacher yet

Revision ID: d4e8b2c6f1a3
Revises: c3e7a9b1d4f2
Create Date: 2026-10-23 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8b2c6f1a3'
down_revision: Union[str, None] = 'c3e7a9b1d4f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch mode so SQLite (tests, local dev) can rebuild the table.
    with op.batch_alter_table('timetable_entries') as batch:
        batch.alter_column('teacher_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.execute('DELETE FROM timetable_entries WHERE teacher_id IS NULL')
    with op.batch_alter_table('timetable_entries') as batch:
        batch.alter_column('teacher_id', existing_type=sa.Integer(), nullable=False)

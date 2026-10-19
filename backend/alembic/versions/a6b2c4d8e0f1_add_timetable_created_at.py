"""add timetables.created_at

Revision ID: a6b2c4d8e0f1
Revises: f9a3c6d8e2b1
Create Date: 2026-10-18 12:00:00.000000

Existing timetables are left NULL on purpose: their generation time is
unknown, and NULL makes them keep checking every rule as before. Only new
timetables get a time, from the server default added after the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a6b2c4d8e0f1'
down_revision: Union[str, None] = 'f9a3c6d8e2b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Added with its default, then emptied for the rows that already exist -
    # one way that works on Postgres and SQLite alike (SQLite can't ALTER a
    # column's default afterwards).
    op.add_column(
        'timetables',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
    )
    op.execute("UPDATE timetables SET created_at = NULL")


def downgrade() -> None:
    op.drop_column('timetables', 'created_at')

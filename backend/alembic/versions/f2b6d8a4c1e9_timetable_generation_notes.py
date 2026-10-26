"""timetables.generation_notes - what a successful generation wants the admin to know

Revision ID: f2b6d8a4c1e9
Revises: c949f9c5171e
Create Date: 2026-10-26 20:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2b6d8a4c1e9'
down_revision: Union[str, None] = 'c949f9c5171e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('timetables', sa.Column('generation_notes', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('timetables', 'generation_notes')

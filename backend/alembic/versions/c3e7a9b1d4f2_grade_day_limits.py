"""schools.grade_day_limits - shorter school days for some grades

Revision ID: c3e7a9b1d4f2
Revises: b8d1e5f3a2c7
Create Date: 2026-10-21 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3e7a9b1d4f2'
down_revision: Union[str, None] = 'b8d1e5f3a2c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('grade_day_limits', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'grade_day_limits')

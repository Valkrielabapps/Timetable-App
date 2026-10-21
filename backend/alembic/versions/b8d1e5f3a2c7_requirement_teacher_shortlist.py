"""subject_requirements.allowed_teacher_ids - a teacher shortlist

Revision ID: b8d1e5f3a2c7
Revises: a6b2c4d8e0f1
Create Date: 2026-10-21 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d1e5f3a2c7'
down_revision: Union[str, None] = 'a6b2c4d8e0f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subject_requirements', sa.Column('allowed_teacher_ids', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('subject_requirements', 'allowed_teacher_ids')

"""Elective block options can be shared between two or more teachers

Revision ID: a8c4e2f6b1d3
Revises: f3a7c1e9d5b2
Create Date: 2026-11-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a8c4e2f6b1d3"
down_revision = "f3a7c1e9d5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("elective_options", sa.Column("allowed_teacher_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("elective_options") as batch:
        batch.drop_column("allowed_teacher_ids")

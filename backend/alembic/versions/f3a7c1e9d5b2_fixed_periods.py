"""Subjects held at a fixed period for some grades (a class teacher period
in period 8 for Grades 1-5, say).

Revision ID: f3a7c1e9d5b2
Revises: e4b8c2d6f0a1
"""
import sqlalchemy as sa
from alembic import op

revision: str = "f3a7c1e9d5b2"
down_revision = "e4b8c2d6f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("schools", sa.Column("fixed_periods", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("schools") as batch:
        batch.drop_column("fixed_periods")

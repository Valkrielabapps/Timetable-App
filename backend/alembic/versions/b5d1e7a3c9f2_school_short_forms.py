"""Short forms each school confirmed once (MAT -> Mathematics, BEAUL -> Beula Rao)

Revision ID: b5d1e7a3c9f2
Revises: a8c4e2f6b1d3
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5d1e7a3c9f2"
down_revision = "a8c4e2f6b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "school_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("text", sa.String(100), nullable=False),
        sa.Column("meaning", sa.String(100), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("school_id", "kind", "key", name="uq_alias_school_kind_key"),
    )
    op.create_index("ix_school_aliases_school_id", "school_aliases", ["school_id"])


def downgrade() -> None:
    op.drop_index("ix_school_aliases_school_id", table_name="school_aliases")
    op.drop_table("school_aliases")

"""Which teachers were emailed about a day's cover.

Revision ID: e4b8c2d6f0a1
Revises: d1f7b3a9c5e2
"""
import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c2d6f0a1"
down_revision = "d1f7b3a9c5e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("substitution_logs", sa.Column("notified", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("substitution_logs") as batch:
        batch.drop_column("notified")

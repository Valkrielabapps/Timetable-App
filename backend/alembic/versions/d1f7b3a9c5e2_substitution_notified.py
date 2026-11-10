"""Which teachers were emailed about a day's cover.

Revision ID: d1f7b3a9c5e2
Revises: c9e5a1f3b7d4
"""
import sqlalchemy as sa
from alembic import op

revision: str = "d1f7b3a9c5e2"
down_revision = "c9e5a1f3b7d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("substitution_logs", sa.Column("notified", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("substitution_logs") as batch:
        batch.drop_column("notified")

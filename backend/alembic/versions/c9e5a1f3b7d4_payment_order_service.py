"""Whether an order was for the software or done for you.

Revision ID: c9e5a1f3b7d4
Revises: b8d4f0e2a6c3
"""
import sqlalchemy as sa
from alembic import op

revision: str = "c9e5a1f3b7d4"
down_revision = "b8d4f0e2a6c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payment_orders", sa.Column("service", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch:
        batch.drop_column("service")

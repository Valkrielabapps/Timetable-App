"""Keep invoices and payment orders when a school is deleted from the admin page.

Revision ID: b8d4f0e2a6c3
Revises: a7c3e9d1f5b2
"""
import sqlalchemy as sa
from alembic import op

revision: str = "b8d4f0e2a6c3"
down_revision = "a7c3e9d1f5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # app/services/erase.py clears school_id on these before deleting a
    # school, so the payment records the law requires keeping stay.
    with op.batch_alter_table("invoices") as batch:
        batch.alter_column("school_id", existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table("payment_orders") as batch:
        batch.alter_column("school_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("payment_orders") as batch:
        batch.alter_column("school_id", existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table("invoices") as batch:
        batch.alter_column("school_id", existing_type=sa.Integer(), nullable=False)

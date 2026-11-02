"""Outreach can send from a Zoho Mail mailbox as well as Gmail.

Revision ID: e5c9f2a8b3d1
Revises: d4b8e1f3a7c2
"""
import sqlalchemy as sa
from alembic import op

revision: str = "e5c9f2a8b3d1"
down_revision = "d4b8e1f3a7c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outreach_settings") as b:
        b.add_column(sa.Column("mailbox_provider", sa.String(), nullable=True))
        b.add_column(sa.Column("zoho_account_id", sa.String(), nullable=True))
        b.add_column(sa.Column("zoho_api_domain", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("outreach_settings") as b:
        b.drop_column("zoho_api_domain")
        b.drop_column("zoho_account_id")
        b.drop_column("mailbox_provider")

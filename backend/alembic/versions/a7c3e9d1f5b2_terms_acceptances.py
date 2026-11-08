"""Record of each acceptance of the Terms of Service.

Revision ID: a7c3e9d1f5b2
Revises: f6d1a9c4e2b7
"""
import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9d1f5b2"
down_revision = "f6d1a9c4e2b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terms_acceptances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(400), nullable=True),
    )
    op.create_index("ix_terms_acceptances_user_id", "terms_acceptances", ["user_id"])


def downgrade() -> None:
    op.drop_table("terms_acceptances")

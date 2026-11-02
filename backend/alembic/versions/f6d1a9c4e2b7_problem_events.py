"""Where schools get stuck: problem_events for the admin page.

Revision ID: f6d1a9c4e2b7
Revises: e5c9f2a8b3d1
"""
import sqlalchemy as sa
from alembic import op

revision: str = "f6d1a9c4e2b7"
down_revision = "e5c9f2a8b3d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problem_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("school_id", sa.Integer(), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("timetable_id", sa.Integer(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_problem_events_created_at", "problem_events", ["created_at"])
    op.create_index("ix_problem_events_school_id", "problem_events", ["school_id"])
    op.create_index("ix_problem_events_kind", "problem_events", ["kind"])
    op.create_index("ix_problem_events_status", "problem_events", ["status"])


def downgrade() -> None:
    op.drop_table("problem_events")

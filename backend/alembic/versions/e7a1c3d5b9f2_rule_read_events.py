"""rule_read_events - what happened when sentences were read into rules

Revision ID: e7a1c3d5b9f2
Revises: d4e8b2c6f1a3
Create Date: 2026-10-24 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7a1c3d5b9f2'
down_revision: Union[str, None] = 'd4e8b2c6f1a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rule_read_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=True),
        sa.Column('constraint_id', sa.Integer(), nullable=True),
        sa.Column('triage', sa.String(length=16), nullable=True),
    )
    op.create_index('ix_rule_read_events_created_at', 'rule_read_events', ['created_at'])
    op.create_index('ix_rule_read_events_school_id', 'rule_read_events', ['school_id'])
    op.create_index('ix_rule_read_events_kind', 'rule_read_events', ['kind'])


def downgrade() -> None:
    op.drop_index('ix_rule_read_events_kind', 'rule_read_events')
    op.drop_index('ix_rule_read_events_school_id', 'rule_read_events')
    op.drop_index('ix_rule_read_events_created_at', 'rule_read_events')
    op.drop_table('rule_read_events')

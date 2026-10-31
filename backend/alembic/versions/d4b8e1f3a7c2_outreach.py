"""sales outreach: schools, emails, settings

Revision ID: d4b8e1f3a7c2
Revises: 0ee16a4c4226
Create Date: 2026-10-31 12:00:00.000000

Timetablz's own sales pipeline, run from the admin page - see
app/models/outreach.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b8e1f3a7c2'
down_revision: Union[str, None] = '0ee16a4c4226'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outreach_schools',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('district', sa.String(), nullable=True),
        sa.Column('area', sa.String(), nullable=True),
        sa.Column('board', sa.String(), nullable=True),
        sa.Column('classes_up_to', sa.String(), nullable=True),
        sa.Column('school_type', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), nullable=True),
        sa.Column('group_name', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.Column('emails', sa.JSON(), nullable=True),
        sa.Column('to_email', sa.String(), nullable=True),
        sa.Column('email_source', sa.String(), nullable=True),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('principal_name', sa.String(), nullable=True),
        sa.Column('contact_name', sa.String(), nullable=True),
        sa.Column('contact_role', sa.String(), nullable=True),
        sa.Column('contact_source', sa.String(), nullable=True),
        sa.Column('contacts_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='not_contacted'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('next_step', sa.String(), nullable=True),
        sa.Column('next_date', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'outreach_messages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('outreach_schools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('step', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('to_email', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('not_before', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_message_id', sa.String(), nullable=True),
        sa.Column('provider_thread_id', sa.String(), nullable=True),
        sa.Column('rfc_message_id', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_outreach_messages_school_id', 'outreach_messages', ['school_id'])
    op.create_index('ix_outreach_messages_status', 'outreach_messages', ['status'])
    op.create_table(
        'outreach_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sender_name', sa.String(), nullable=True),
        sa.Column('signature', sa.Text(), nullable=True),
        sa.Column('templates', sa.JSON(), nullable=True),
        sa.Column('daily_limit', sa.Integer(), nullable=False, server_default='15'),
        sa.Column('follow_up_days', sa.JSON(), nullable=True),
        sa.Column('sending_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('gmail_address', sa.String(), nullable=True),
        sa.Column('gmail_refresh_token', sa.Text(), nullable=True),
        sa.Column('last_reply_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('first_sent_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('outreach_settings')
    op.drop_index('ix_outreach_messages_status', 'outreach_messages')
    op.drop_index('ix_outreach_messages_school_id', 'outreach_messages')
    op.drop_table('outreach_messages')
    op.drop_table('outreach_schools')

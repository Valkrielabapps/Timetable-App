"""custom plan offers, invoices, and custom limits on schools

Revision ID: f9a3c6d8e2b1
Revises: e5f1a2b3c4d6
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9a3c6d8e2b1'
down_revision: Union[str, None] = 'e5f1a2b3c4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('custom_limits', sa.JSON(), nullable=True))
    op.add_column('schools', sa.Column('custom_plan_name', sa.String(length=80), nullable=True))

    op.create_table(
        'plan_offers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('price_inr', sa.Integer(), nullable=False),
        sa.Column('period_days', sa.Integer(), nullable=False),
        sa.Column('max_sections', sa.Integer(), nullable=True),
        sa.Column('max_members', sa.Integer(), nullable=True),
        sa.Column('max_owned_schools', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_plan_offers_school_id', 'plan_offers', ['school_id'])

    with op.batch_alter_table('payment_orders') as batch:
        batch.add_column(sa.Column('offer_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('period_days', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_payment_orders_offer_id', 'plan_offers', ['offer_id'], ['id'])

    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('number', sa.String(length=20), nullable=False),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('payment_order_id', sa.Integer(), sa.ForeignKey('payment_orders.id'), nullable=True),
        sa.Column('description', sa.String(length=200), nullable=False),
        sa.Column('amount_paise', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('method', sa.String(length=20), nullable=False),
        sa.Column('reference', sa.String(length=100), nullable=True),
        sa.Column('billed_to', sa.JSON(), nullable=True),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_invoices_number', 'invoices', ['number'], unique=True)
    op.create_index('ix_invoices_school_id', 'invoices', ['school_id'])


def downgrade() -> None:
    op.drop_index('ix_invoices_school_id', table_name='invoices')
    op.drop_index('ix_invoices_number', table_name='invoices')
    op.drop_table('invoices')
    with op.batch_alter_table('payment_orders') as batch:
        batch.drop_constraint('fk_payment_orders_offer_id', type_='foreignkey')
        batch.drop_column('period_days')
        batch.drop_column('offer_id')
    op.drop_index('ix_plan_offers_school_id', table_name='plan_offers')
    op.drop_table('plan_offers')
    op.drop_column('schools', 'custom_plan_name')
    op.drop_column('schools', 'custom_limits')

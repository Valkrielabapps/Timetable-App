"""add payment_orders and schools.plan

Revision ID: c7d2f4a9e1b6
Revises: 7433831f2744
Create Date: 2026-10-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d2f4a9e1b6'
down_revision: Union[str, None] = '7433831f2744'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable: every existing school is on the Free plan.
    op.add_column('schools', sa.Column('plan', sa.String(length=20), nullable=True))
    op.add_column('schools', sa.Column('plan_valid_until', sa.DateTime(), nullable=True))

    op.create_table(
        'payment_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.String(length=45), nullable=False),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('amount_paise', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('cf_order_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_payment_orders_order_id', 'payment_orders', ['order_id'], unique=True)
    op.create_index('ix_payment_orders_school_id', 'payment_orders', ['school_id'])


def downgrade() -> None:
    op.drop_index('ix_payment_orders_school_id', table_name='payment_orders')
    op.drop_index('ix_payment_orders_order_id', table_name='payment_orders')
    op.drop_table('payment_orders')
    op.drop_column('schools', 'plan_valid_until')
    op.drop_column('schools', 'plan')

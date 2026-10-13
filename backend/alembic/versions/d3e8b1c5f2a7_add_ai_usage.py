"""add schools.ai_usage_month / ai_usage_count

Revision ID: d3e8b1c5f2a7
Revises: c7d2f4a9e1b6
Create Date: 2026-10-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3e8b1c5f2a7'
down_revision: Union[str, None] = 'c7d2f4a9e1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('ai_usage_month', sa.String(length=7), nullable=True))
    op.add_column('schools', sa.Column('ai_usage_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'ai_usage_count')
    op.drop_column('schools', 'ai_usage_month')

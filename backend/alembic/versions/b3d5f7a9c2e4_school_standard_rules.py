"""schools.standard_rules - the tick-box rules on the Constraints page

Revision ID: b3d5f7a9c2e4
Revises: 79b3014e7797
Create Date: 2026-10-27 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3d5f7a9c2e4'
down_revision: Union[str, None] = '79b3014e7797'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('standard_rules', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'standard_rules')

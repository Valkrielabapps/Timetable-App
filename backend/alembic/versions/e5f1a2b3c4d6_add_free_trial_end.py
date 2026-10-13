"""add schools.free_trial_ends_at; existing free schools get 14 days from now

Revision ID: e5f1a2b3c4d6
Revises: d3e8b1c5f2a7
Create Date: 2026-10-13 18:00:00.000000

"""
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f1a2b3c4d6'
down_revision: Union[str, None] = 'd3e8b1c5f2a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('free_trial_ends_at', sa.DateTime(), nullable=True))
    # Every school that exists when this ships gets a fresh 14 days from the
    # moment it's deployed, rather than being locked straight away.
    ends = (datetime.now(timezone.utc) + timedelta(days=14)).replace(tzinfo=None)
    schools = sa.table('schools', sa.column('free_trial_ends_at', sa.DateTime()))
    op.execute(schools.update().values(free_trial_ends_at=ends))


def downgrade() -> None:
    op.drop_column('schools', 'free_trial_ends_at')

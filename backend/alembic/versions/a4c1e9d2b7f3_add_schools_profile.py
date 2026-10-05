"""add schools.profile

Revision ID: a4c1e9d2b7f3
Revises: f0d72579b20b
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4c1e9d2b7f3'
down_revision: Union[str, None] = 'f0d72579b20b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no default: existing schools simply have no profile yet,
    # which the frontend shows as "Not provided".
    op.add_column('schools', sa.Column('profile', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('schools', 'profile')

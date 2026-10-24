"""freeze sections

Revision ID: c949f9c5171e
Revises: e7a1c3d5b9f2
Create Date: 2026-10-24 19:31:21.766225

Frozen sections: a section's timetable kept exactly as it is through later
generations, with what it looked like when frozen so later changes can be
pointed out. See generate_school_timetable in app/services/solver.py.

sa.false() rather than the text 'false': SQLite stores the text as-is and
reads it back as true - every existing section would arrive frozen.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c949f9c5171e'
down_revision: Union[str, None] = 'e7a1c3d5b9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('class_groups', sa.Column('frozen', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('class_groups', sa.Column('frozen_at', sa.DateTime(), nullable=True))
    op.add_column('class_groups', sa.Column('frozen_signature', sa.String(), nullable=True))
    op.add_column('class_groups', sa.Column('frozen_lessons', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('class_groups', 'frozen_lessons')
    op.drop_column('class_groups', 'frozen_signature')
    op.drop_column('class_groups', 'frozen_at')
    op.drop_column('class_groups', 'frozen')

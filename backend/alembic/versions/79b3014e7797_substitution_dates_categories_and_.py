"""substitution dates, categories and absences

Revision ID: 79b3014e7797
Revises: a7c3e9f1b5d2
Create Date: 2026-10-27 00:50:42.733096

Substitutions arranged for a real date and a part of the school.

  schools.grade_categories       a school's own choice of part per grade
                                 (pre-primary, primary, middle, high), over
                                 the defaults read from grade names
  substitution_logs.date         the day the cover is for
  substitution_logs.category     the part it was arranged for; null = whole
                                 school
  substitution_logs.absences     who was away, whole day or which periods

All nullable: records saved before this keep working, shown by the day they
were saved.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79b3014e7797'
down_revision: Union[str, None] = 'a7c3e9f1b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('schools', sa.Column('grade_categories', sa.JSON(), nullable=True))
    op.add_column('substitution_logs', sa.Column('date', sa.Date(), nullable=True))
    op.add_column('substitution_logs', sa.Column('category', sa.String(), nullable=True))
    op.add_column('substitution_logs', sa.Column('absences', sa.JSON(), nullable=True))
    op.create_index(op.f('ix_substitution_logs_date'), 'substitution_logs', ['date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_substitution_logs_date'), table_name='substitution_logs')
    op.drop_column('substitution_logs', 'absences')
    op.drop_column('substitution_logs', 'category')
    op.drop_column('substitution_logs', 'date')
    op.drop_column('schools', 'grade_categories')

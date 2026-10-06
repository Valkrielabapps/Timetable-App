"""add elective blocks

Revision ID: a1e3c7b2d904
Revises: f0d72579b20b
Create Date: 2026-10-07 12:00:00.000000

Elective blocks: sets of subjects a section studies at the same time, each
student taking one. Two new tables, and a nullable link from a timetable entry
back to the block it was scheduled as part of.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1e3c7b2d904'
down_revision: Union[str, None] = 'f0d72579b20b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'elective_blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('school_id', sa.Integer(), nullable=False),
        sa.Column('class_group_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('periods_per_week', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['school_id'], ['schools.id']),
        sa.ForeignKeyConstraint(['class_group_id'], ['class_groups.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'elective_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('preferred_teacher_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['block_id'], ['elective_blocks.id']),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id']),
        sa.ForeignKeyConstraint(['preferred_teacher_id'], ['teachers.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('block_id', 'subject_id'),
    )
    # batch_alter_table so the same migration runs on SQLite, which cannot
    # add a foreign key to an existing table in place.
    with op.batch_alter_table('timetable_entries') as batch:
        batch.add_column(sa.Column('elective_block_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_timetable_entries_elective_block_id',
            'elective_blocks', ['elective_block_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('timetable_entries') as batch:
        batch.drop_constraint('fk_timetable_entries_elective_block_id', type_='foreignkey')
        batch.drop_column('elective_block_id')
    op.drop_table('elective_options')
    op.drop_table('elective_blocks')

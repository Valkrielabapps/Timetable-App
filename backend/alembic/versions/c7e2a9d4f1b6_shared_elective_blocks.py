"""elective blocks shared between sections

Revision ID: c7e2a9d4f1b6
Revises: 0310cad2a254
Create Date: 2026-10-30 12:00:00.000000

A block can now span several sections, and each option is a teaching group
drawn from some or all of them:

  - elective_block_sections: the further sections in a block
  - elective_options.class_group_ids / label: which sections a group's
    students come from, and a name to tell two groups of one subject apart
  - the (block_id, subject_id) unique constraint goes, so one subject can be
    split into several groups
  - timetable_entries.elective_option_id: which group an entry is
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7e2a9d4f1b6'
down_revision: Union[str, None] = '0310cad2a254'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _option_unique_names(bind) -> list[str]:
    insp = sa.inspect(bind)
    names = []
    for uc in insp.get_unique_constraints('elective_options'):
        if sorted(uc.get('column_names') or []) == ['block_id', 'subject_id']:
            names.append(uc.get('name'))
    return names


def upgrade() -> None:
    op.create_table(
        'elective_block_sections',
        sa.Column('block_id', sa.Integer(), nullable=False),
        sa.Column('class_group_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['block_id'], ['elective_blocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['class_group_id'], ['class_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('block_id', 'class_group_id'),
    )

    bind = op.get_bind()
    names = _option_unique_names(bind)
    if bind.dialect.name == 'sqlite':
        # SQLite's unique constraint from the original table has no name, so
        # it can only go by rebuilding the table from a definition without it.
        without_unique = sa.Table(
            'elective_options', sa.MetaData(),
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('block_id', sa.Integer(), sa.ForeignKey('elective_blocks.id'), nullable=False),
            sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id'), nullable=False),
            sa.Column('preferred_teacher_id', sa.Integer(), sa.ForeignKey('teachers.id'), nullable=True),
        )
        with op.batch_alter_table('elective_options', recreate='always', copy_from=without_unique) as batch:
            batch.add_column(sa.Column('class_group_ids', sa.JSON(), nullable=True))
            batch.add_column(sa.Column('label', sa.String(), nullable=True))
    else:
        op.add_column('elective_options', sa.Column('class_group_ids', sa.JSON(), nullable=True))
        op.add_column('elective_options', sa.Column('label', sa.String(), nullable=True))
        for name in names:
            if name:
                op.drop_constraint(name, 'elective_options', type_='unique')

    with op.batch_alter_table('timetable_entries') as batch:
        batch.add_column(sa.Column('elective_option_id', sa.Integer(), nullable=True))
        batch.create_foreign_key(
            'fk_timetable_entries_elective_option_id',
            'elective_options', ['elective_option_id'], ['id'], ondelete='SET NULL',
        )


def downgrade() -> None:
    with op.batch_alter_table('timetable_entries') as batch:
        batch.drop_constraint('fk_timetable_entries_elective_option_id', type_='foreignkey')
        batch.drop_column('elective_option_id')
    with op.batch_alter_table('elective_options') as batch:
        batch.drop_column('label')
        batch.drop_column('class_group_ids')
    op.drop_table('elective_block_sections')

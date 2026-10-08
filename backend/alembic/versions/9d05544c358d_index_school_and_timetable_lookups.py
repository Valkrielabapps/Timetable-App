"""index school and timetable lookups

Revision ID: 9d05544c358d
Revises: a1e3c7b2d904
Create Date: 2026-10-09 01:59:49.723232

Postgres does not index foreign keys on its own, and nearly every query here
filters by school_id - and every timetable read by timetable_id. Without these
each read scans every row of its table across every school, and
timetable_entries grows by about a thousand rows per Generate.

Tables whose school_id already leads a unique constraint (periods,
school_memberships) or whose lookup column does (subject_requirements,
elective_options) are already indexed by it and are left alone.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d05544c358d'
down_revision: Union[str, None] = 'a1e3c7b2d904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_class_groups_school_id'), 'class_groups', ['school_id'], unique=False)
    op.create_index(op.f('ix_constraints_school_id'), 'constraints', ['school_id'], unique=False)
    op.create_index(op.f('ix_elective_blocks_class_group_id'), 'elective_blocks', ['class_group_id'], unique=False)
    op.create_index(op.f('ix_elective_blocks_school_id'), 'elective_blocks', ['school_id'], unique=False)
    op.create_index(op.f('ix_rooms_school_id'), 'rooms', ['school_id'], unique=False)
    op.create_index(op.f('ix_school_invites_school_id'), 'school_invites', ['school_id'], unique=False)
    op.create_index(op.f('ix_school_memberships_user_id'), 'school_memberships', ['user_id'], unique=False)
    op.create_index(op.f('ix_schools_owner_id'), 'schools', ['owner_id'], unique=False)
    op.create_index(op.f('ix_subjects_school_id'), 'subjects', ['school_id'], unique=False)
    op.create_index(op.f('ix_substitution_logs_school_id'), 'substitution_logs', ['school_id'], unique=False)
    op.create_index(op.f('ix_teachers_school_id'), 'teachers', ['school_id'], unique=False)
    op.create_index('ix_timetable_entries_timetable_class_period', 'timetable_entries', ['timetable_id', 'class_group_id', 'period_id'], unique=False)
    op.create_index('ix_timetable_entries_timetable_period', 'timetable_entries', ['timetable_id', 'period_id'], unique=False)
    op.create_index(op.f('ix_timetables_school_id'), 'timetables', ['school_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_timetables_school_id'), table_name='timetables')
    op.drop_index('ix_timetable_entries_timetable_period', table_name='timetable_entries')
    op.drop_index('ix_timetable_entries_timetable_class_period', table_name='timetable_entries')
    op.drop_index(op.f('ix_teachers_school_id'), table_name='teachers')
    op.drop_index(op.f('ix_substitution_logs_school_id'), table_name='substitution_logs')
    op.drop_index(op.f('ix_subjects_school_id'), table_name='subjects')
    op.drop_index(op.f('ix_schools_owner_id'), table_name='schools')
    op.drop_index(op.f('ix_school_memberships_user_id'), table_name='school_memberships')
    op.drop_index(op.f('ix_school_invites_school_id'), table_name='school_invites')
    op.drop_index(op.f('ix_rooms_school_id'), table_name='rooms')
    op.drop_index(op.f('ix_elective_blocks_school_id'), table_name='elective_blocks')
    op.drop_index(op.f('ix_elective_blocks_class_group_id'), table_name='elective_blocks')
    op.drop_index(op.f('ix_constraints_school_id'), table_name='constraints')
    op.drop_index(op.f('ix_class_groups_school_id'), table_name='class_groups')

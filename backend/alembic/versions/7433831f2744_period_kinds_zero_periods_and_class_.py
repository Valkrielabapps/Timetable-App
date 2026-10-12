"""period kinds, zero periods and class teachers

Revision ID: 7433831f2744
Revises: 9d05544c358d
Create Date: 2026-10-12 19:24:03.677184

Three schema changes and one data change.

  periods.kind        replaces periods.is_break: "lesson", "break",
                      "class_teacher" or "zero". Every break stays a break.
  zero_periods        a lesson slot kept free for one grade (or everyone) -
                      the form a zero period takes when it differs by grade or
                      by day. See app/services/timetable_structure.py.
  class_groups.class_teacher_id

The data change is what keeps saved rules meaning the same thing. Until now a
rule saying "period 5" meant the fifth ROW of the day, breaks included, because
the timetable labelled rows that way: with lunch fourth, the lesson after it
was shown as "Period 5". From here on only lessons are numbered - that lesson
is shown as "Period 4" - so a rule saved as "period 5" is renumbered to 4 and
keeps pointing at the same lesson. Schools without breaks are untouched; their
rows and lessons were already the same thing.
"""
import logging
from collections import Counter, defaultdict
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7433831f2744'
down_revision: Union[str, None] = '9d05544c358d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

log = logging.getLogger("alembic.runtime.migration")

_periods = sa.table(
    "periods",
    sa.column("id", sa.Integer), sa.column("school_id", sa.Integer),
    sa.column("day_of_week", sa.Integer), sa.column("order", sa.Integer),
    # Untyped, and read through _truthy: an older SQLite migration stored the
    # default as the text 'false', which a Boolean column reads back as true.
    sa.column("is_break"), sa.column("kind", sa.String),
)


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "t", "yes")
    return bool(value)
_constraints = sa.table(
    "constraints",
    sa.column("id", sa.Integer), sa.column("school_id", sa.Integer), sa.column("type", sa.String),
    sa.column("parameters", sa.JSON), sa.column("description", sa.String),
)


def _row_to_lesson_maps(conn, reverse: bool = False) -> dict[int, dict[int, int]]:
    """school_id -> {old row position: new lesson number}, for schools where
    the two differ. A position that was a break on most days maps to a number
    past the end of the day, so a rule that matched nothing still does.

    reverse=True gives {lesson number: row position} instead, for the
    downgrade - so going down and back up leaves rules where they were."""
    rows = conn.execute(sa.select(
        _periods.c.school_id, _periods.c.day_of_week, _periods.c.order, _periods.c.is_break,
    )).fetchall()
    days: dict[int, dict[int, list]] = defaultdict(lambda: defaultdict(list))
    for school_id, day, order, is_break in rows:
        days[school_id][day].append((order, _truthy(is_break)))

    maps: dict[int, dict[int, int]] = {}
    for school_id, by_day in days.items():
        votes: dict[int, Counter] = defaultdict(Counter)
        most_lessons = 0
        for day_rows in by_day.values():
            lesson = 0
            for position, (_order, is_break) in enumerate(sorted(day_rows), start=1):
                if is_break:
                    if not reverse:
                        votes[position][None] += 1
                else:
                    lesson += 1
                    if reverse:
                        votes[lesson][position] += 1
                    else:
                        votes[position][lesson] += 1
            most_lessons = max(most_lessons, lesson)
        mapping = {}
        for position, counter in votes.items():
            target = counter.most_common(1)[0][0]
            mapping[position] = most_lessons + 1 if target is None else target
        if any(old != new for old, new in mapping.items()):
            maps[school_id] = mapping
    return maps


def _renumber(node, mapping: dict[int, int]) -> bool:
    """Rewrite every period_orders list in a stored rule, in place."""
    changed = False
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "period_orders" and isinstance(value, list):
                new = []
                for n in value:
                    m = mapping.get(n, n) if isinstance(n, int) else n
                    if m not in new:
                        new.append(m)
                if new != value:
                    node[key] = new
                    changed = True
            else:
                changed |= _renumber(value, mapping)
    elif isinstance(node, list):
        for item in node:
            changed |= _renumber(item, mapping)
    return changed


def _remap_rules(conn, reverse: bool = False) -> None:
    maps = _row_to_lesson_maps(conn, reverse)
    if not maps:
        return
    rules = conn.execute(
        sa.select(_constraints.c.id, _constraints.c.school_id, _constraints.c.parameters,
                  _constraints.c.description)
        .where(_constraints.c.type == "ir", _constraints.c.school_id.in_(list(maps)))
    ).fetchall()
    changed = 0
    for rule_id, school_id, parameters, description in rules:
        if not isinstance(parameters, dict) or not _renumber(parameters, maps[school_id]):
            continue
        # The sentence on the card names the period too; re-rendered so it
        # says the new number. Best effort - the rule is what the solver reads.
        try:
            from app.services.constraint_ir import rule_from_dict
            from app.services.constraint_ir_english import render
            description = render(rule_from_dict(parameters))
        except Exception:  # noqa: BLE001
            pass
        conn.execute(
            _constraints.update().where(_constraints.c.id == rule_id)
            .values(parameters=parameters, description=description)
        )
        changed += 1
    if changed:
        log.info("Renumbered periods in %d saved rule(s) to count %s", changed,
                 "every row" if reverse else "lessons only")


def upgrade() -> None:
    op.create_table('zero_periods',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('school_id', sa.Integer(), nullable=False),
    sa.Column('period_id', sa.Integer(), nullable=False),
    sa.Column('grade', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['period_id'], ['periods.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_zero_periods_period_id'), 'zero_periods', ['period_id'], unique=False)
    op.create_index(op.f('ix_zero_periods_school_id'), 'zero_periods', ['school_id'], unique=False)

    # batch_alter_table so the same migration runs on SQLite, which cannot add
    # a foreign key to an existing table in place.
    with op.batch_alter_table('class_groups') as batch:
        batch.add_column(sa.Column('class_teacher_id', sa.Integer(), nullable=True))
        batch.create_index(batch.f('ix_class_groups_class_teacher_id'), ['class_teacher_id'], unique=False)
        batch.create_foreign_key(
            'fk_class_groups_class_teacher_id', 'teachers', ['class_teacher_id'], ['id'], ondelete='SET NULL',
        )

    conn = op.get_bind()
    # Before is_break goes: it is what says which rows were breaks.
    _remap_rules(conn)
    break_ids = [
        pid for pid, flag in conn.execute(sa.select(_periods.c.id, _periods.c.is_break)) if _truthy(flag)
    ]
    op.add_column('periods', sa.Column('kind', sa.String(), server_default='lesson', nullable=False))
    if break_ids:
        conn.execute(_periods.update().where(_periods.c.id.in_(break_ids)).values(kind='break'))
    with op.batch_alter_table('periods') as batch:
        batch.drop_column('is_break')


def downgrade() -> None:
    # The class teacher and zero periods have no older equivalent; they come
    # back as breaks, which is what they were closest to - nothing taught.
    op.add_column('periods', sa.Column('is_break', sa.Boolean(), server_default=sa.text("'false'"), nullable=False))
    conn = op.get_bind()
    # Both ways, not just the breaks: SQLite stores the text default 'false',
    # which reads back as true.
    conn.execute(_periods.update().where(_periods.c.kind != 'lesson').values(is_break=True))
    conn.execute(_periods.update().where(_periods.c.kind == 'lesson').values(is_break=False))
    _remap_rules(conn, reverse=True)
    with op.batch_alter_table('periods') as batch:
        batch.drop_column('kind')
    with op.batch_alter_table('class_groups') as batch:
        batch.drop_constraint('fk_class_groups_class_teacher_id', type_='foreignkey')
        batch.drop_index(batch.f('ix_class_groups_class_teacher_id'))
        batch.drop_column('class_teacher_id')
    op.drop_index(op.f('ix_zero_periods_school_id'), table_name='zero_periods')
    op.drop_index(op.f('ix_zero_periods_period_id'), table_name='zero_periods')
    op.drop_table('zero_periods')

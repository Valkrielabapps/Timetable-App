"""email verified and token version

Revision ID: 0ee16a4c4226
Revises: c7e2a9d4f1b6
Create Date: 2026-10-31 13:22:39.021974

"""
from typing import Sequence, Union

import os

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0ee16a4c4226'
down_revision: Union[str, None] = 'c7e2a9d4f1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))

    # Accounts that have already proved their email: Google verified it for
    # anyone who has signed in with Google. The Timetablz admin account is
    # marked too, so the admin page - which now needs a verified email -
    # keeps working for it.
    users = sa.table("users", sa.column("email", sa.String), sa.column("google_sub", sa.String),
                     sa.column("email_verified", sa.Boolean))
    op.execute(users.update().where(users.c.google_sub.isnot(None)).values(email_verified=True))
    admins = os.environ.get("PLATFORM_ADMIN_EMAILS") or "valkyrielabapps@gmail.com"
    for email in {e.strip().lower() for e in admins.split(",") if e.strip()}:
        op.execute(users.update().where(sa.func.lower(users.c.email) == email).values(email_verified=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
        batch.drop_column("email_verified")

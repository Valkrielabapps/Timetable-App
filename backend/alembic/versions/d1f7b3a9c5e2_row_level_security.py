"""Row-level security on every table, and no table access for Supabase's public roles.

Supabase publishes a Data API that anyone holding the project's anon key can
call as the `anon` or `authenticated` role. This app never uses it: the browser
only talks to the backend, which connects as the role that owns the tables and
checks who may see which school on every request. So those two roles get no
policies at all (row-level security with no policy lets nobody through) and
lose their table grants, now and for tables made by later migrations.

The backend is unaffected because a table's owner bypasses row-level security
unless it is forced, and this doesn't force it. The migration refuses to run if
the connecting role doesn't own a table and can't bypass row-level security,
since enabling it would then lock the app out of that table.

Revision ID: d1f7b3a9c5e2
Revises: c9e5a1f3b7d4
"""
from alembic import op

revision: str = "d1f7b3a9c5e2"
down_revision = "c9e5a1f3b7d4"
branch_labels = None
depends_on = None

PUBLIC_ROLES = ("anon", "authenticated")

_TABLES = """
    SELECT c.oid::regclass AS rel, c.relowner
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
"""


def _public_roles_sql(action: str) -> str:
    # Plain Postgres (local development, CI) has no Supabase roles: skip them.
    return f"""
    DO $$
    DECLARE r text;
    BEGIN
      FOREACH r IN ARRAY ARRAY{list(PUBLIC_ROLES)} LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
          {action}
        END IF;
      END LOOP;
    END $$;
    """


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"""
    DO $$
    DECLARE t record;
    BEGIN
      FOR t IN {_TABLES} LOOP
        IF NOT pg_has_role(current_user, t.relowner, 'USAGE')
           AND NOT (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user) THEN
          RAISE EXCEPTION 'Not turning on row-level security: % is owned by %, so the app (%) would lose access to it',
            t.rel, pg_get_userbyid(t.relowner), current_user;
        END IF;
      END LOOP;
      FOR t IN {_TABLES} LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t.rel);
      END LOOP;
    END $$;
    """)
    op.execute(_public_roles_sql("""
          EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
          EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
          EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
          EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
    """))


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Back to Supabase's defaults.
    op.execute(_public_roles_sql("""
          EXECUTE format('GRANT ALL ON ALL TABLES IN SCHEMA public TO %I', r);
          EXECUTE format('GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO %I', r);
          EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %I', r);
          EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO %I', r);
    """))
    op.execute(f"""
    DO $$
    DECLARE t record;
    BEGIN
      FOR t IN {_TABLES} LOOP
        EXECUTE format('ALTER TABLE %s DISABLE ROW LEVEL SECURITY', t.rel);
      END LOOP;
    END $$;
    """)

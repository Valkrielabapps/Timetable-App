"""
Database engine + session setup (SQLAlchemy 2.0 style).

`get_db` is a FastAPI dependency: each request gets its own session, which is
closed automatically when the request finishes.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

# pool_pre_ping: check a connection is still alive before handing it out.
# Matters specifically for free-tier hosted Postgres (e.g. Supabase), which
# can drop idle connections after inactivity - without this, the first
# request after a quiet period would fail with a stale-connection error
# instead of transparently reconnecting. No-op/cheap for SQLite.
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class every SQLAlchemy model inherits from."""
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

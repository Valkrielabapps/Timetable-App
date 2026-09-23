"""
Shared pytest fixtures for the backend test suite.

Forces a fresh, isolated temp-file SQLite database for the whole test
session, regardless of whatever DATABASE_URL a developer's real .env
points at — tests should never depend on (or risk touching) a real
dev.db. A temp *file* rather than `sqlite:///:memory:` is deliberate:
each new connection SQLAlchemy's default pool opens against an in-memory
SQLite URL gets its own blank database unless a shared/static connection
pool is configured, which app/core/database.py's production engine setup
doesn't do (no reason to, in production) — so TestClient requests (each
of which may grab a different pooled connection) would intermittently
hit a database with no tables in it. A temp file sidesteps this with zero
changes to production code.

This has to happen before anything imports app.core.config or
app.core.database, since both read DATABASE_URL exactly once, at import
time — done here, at the very top of conftest.py, since pytest always
imports conftest.py before collecting/importing any test module.
"""
import os
import tempfile

_tmp_db_fd, _tmp_db_path = tempfile.mkstemp(suffix=".db")
os.close(_tmp_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db_path}"

# This suite signs up dozens of users from a single client, which the real
# limits (5 signups/hour per IP) would throttle almost immediately. The limiter
# itself is covered directly in tests/test_rate_limit.py, which re-enables it.
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    os.remove(_tmp_db_path)


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncates every table after each test so tests don't see each
    other's data, without paying for a full schema drop/recreate every
    time (this suite is still small enough that this is cheap; revisit if
    it ever isn't)."""
    yield
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def orm_db():
    """A plain SQLAlchemy session for tests that call service-layer
    functions (e.g. app.services.bulk_import) directly rather than going
    through the HTTP layer — same throwaway-in-memory-DB pattern as
    test_solver.py's local db_session fixture, kept here too so other
    service-level test files don't each need their own copy."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(test_engine)
    session = sessionmaker(bind=test_engine)()
    try:
        yield session
    finally:
        session.close()


def signup(client, email="a@a.com", password="password123", name="A"):
    """Returns (user_json, auth_headers) for a freshly signed-up user."""
    r = client.post("/api/auth/signup", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    body = r.json()
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


def create_school(client, headers, name="Test School", institution_type=None):
    r = client.post("/api/schools", json={"name": name, "institution_type": institution_type}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()

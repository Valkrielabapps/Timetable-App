"""
Tests for Sentry setup, mostly around what must NOT leave the process.

The scrubbing in app/core/observability.py is the only thing standing between
a crash report and a still-valid JWT being posted to a third party, so it is
worth asserting on directly rather than trusting by inspection.
"""
from app.core.observability import _scrub, init_sentry


def test_init_is_a_noop_without_a_dsn(monkeypatch):
    """No DSN is a supported state (local dev, tests, CI), not an error."""
    from app.core import observability

    monkeypatch.setattr(observability.settings, "sentry_dsn", None)
    assert init_sentry() is False


def test_authorization_header_is_scrubbed():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.super-secret",
                "Accept": "application/json",
            }
        }
    }
    scrubbed = _scrub(event, None)
    assert scrubbed["request"]["headers"]["Authorization"] == "[scrubbed]"
    # Non-sensitive headers are useful context and should survive.
    assert scrubbed["request"]["headers"]["Accept"] == "application/json"


def test_cookie_headers_are_scrubbed_case_insensitively():
    event = {"request": {"headers": {"cookie": "session=abc", "SET-COOKIE": "x=1"}}}
    scrubbed = _scrub(event, None)
    assert scrubbed["request"]["headers"]["cookie"] == "[scrubbed]"
    assert scrubbed["request"]["headers"]["SET-COOKIE"] == "[scrubbed]"


def test_request_body_is_dropped():
    """Request bodies here carry emails, names and school data."""
    event = {
        "request": {
            "headers": {},
            "data": {"email": "teacher@school.example", "password": "hunter2"},
        }
    }
    scrubbed = _scrub(event, None)
    assert "data" not in scrubbed["request"]


def test_scrub_tolerates_events_without_a_request():
    """Errors from the background solver thread have no HTTP request attached."""
    event = {"exception": {"values": []}}
    assert _scrub(event, None) == event


def test_blank_env_vars_are_normalised_to_none():
    """`KEY=` in .env means unset, not an empty string.

    .env.example ships every optional key that way, so this is the common
    case rather than an edge one - without normalising, `is None` and
    `if not ...` disagree about whether a feature is configured.
    """
    from app.core.config import Settings

    s = Settings(
        anthropic_api_key="",
        sentry_dsn="   ",
        google_client_id="",
        resend_api_key="",
    )
    assert s.anthropic_api_key is None
    assert s.sentry_dsn is None
    assert s.google_client_id is None
    assert s.resend_api_key is None


def test_real_values_are_left_alone():
    from app.core.config import Settings

    s = Settings(anthropic_api_key="sk-ant-real-key")
    assert s.anthropic_api_key == "sk-ant-real-key"

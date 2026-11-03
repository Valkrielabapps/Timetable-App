"""
Tests for app/services/email_service.py in isolation - mocks the Resend
HTTP call entirely (never makes a real network request) and asserts the
fail-open contract described in that module's docstring: this function
must return a bool and never raise, regardless of what happens.
"""
from unittest.mock import patch

from app.core.config import settings
from app.services.email_service import send_invite_email


def test_returns_false_without_raising_when_no_api_key_configured():
    assert settings.resend_api_key is None  # sanity check on the test env
    result = send_invite_email(
        to_email="new@a.com", school_name="Valkyrie Labs",
        inviter_name="Owner", role="viewer", invite_token="tok123",
    )
    assert result is False


def test_returns_true_when_resend_accepts_the_email():
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            result = send_invite_email(
                to_email="new@a.com", school_name="Valkyrie Labs",
                inviter_name="Owner", role="admin", invite_token="tok123",
            )
    assert result is True
    # Confirm the request was actually shaped like a Resend send-email call.
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer fake-key"
    assert kwargs["json"]["to"] == ["new@a.com"]
    assert "Valkyrie Labs" in kwargs["json"]["subject"]
    assert "tok123" in kwargs["json"]["html"]


def test_returns_false_when_resend_rejects_the_request():
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 422
            mock_post.return_value.text = "Invalid `from` address"
            result = send_invite_email(
                to_email="new@a.com", school_name="Valkyrie Labs",
                inviter_name="Owner", role="viewer", invite_token="tok123",
            )
    assert result is False


def test_returns_false_on_network_error_rather_than_raising():
    with patch.object(settings, "resend_api_key", "fake-key"):
        with patch("app.services.email_service.requests.post", side_effect=ConnectionError("boom")):
            result = send_invite_email(
                to_email="new@a.com", school_name="Valkyrie Labs",
                inviter_name="Owner", role="viewer", invite_token="tok123",
            )
    assert result is False

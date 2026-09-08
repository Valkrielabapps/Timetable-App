"""
Tests for app/services/infeasibility_explainer.py in isolation — mocks
the Anthropic call entirely (never a real API request) and asserts the
fail-open contract described in that module's docstring: this function
must return a str or None, and never raise, regardless of what happens.
"""
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.infeasibility_explainer import explain_infeasibility


def test_returns_none_for_empty_errors():
    assert explain_infeasibility([]) is None


def test_returns_none_without_raising_when_no_api_key_configured():
    assert settings.anthropic_api_key is None  # sanity check on the test env
    result = explain_infeasibility(["Grade 8A needs 40 periods/week but only 35 exist."])
    assert result is None


def test_returns_explanation_text_on_success():
    fake_block = MagicMock(type="text", text="Grade 8A is overbooked — reduce periods or add more to the week.")
    fake_response = MagicMock(content=[fake_block])
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_anthropic_cls.return_value.messages.create.return_value = fake_response
            result = explain_infeasibility(["Grade 8A needs 40 periods/week but only 35 exist."])
    assert result == "Grade 8A is overbooked — reduce periods or add more to the week."


def test_returns_none_on_api_failure_rather_than_raising():
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic", side_effect=ConnectionError("boom")):
            result = explain_infeasibility(["some error"])
    assert result is None


def test_returns_none_when_response_has_no_text_blocks():
    fake_response = MagicMock(content=[])
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_anthropic_cls.return_value.messages.create.return_value = fake_response
            result = explain_infeasibility(["some error"])
    assert result is None

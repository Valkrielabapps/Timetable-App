"""
Tests for app/services/setup_extractor.py in isolation — mocks the
Anthropic call entirely, and exercises read_spreadsheet_rows() against
real in-memory CSV/xlsx bytes (no LLM involved for that part). Follows
the same fail-open contract test shape as test_infeasibility_explainer.py.
"""
import io

import openpyxl
import pytest
from unittest.mock import MagicMock, patch

from app.core.config import settings
from app.services.setup_extractor import extract_setup_llm, read_spreadsheet_rows


def test_read_spreadsheet_rows_csv():
    content = b"Name,Subject\nMrs. Sharma,Math\nMr. Rao,Science\n"
    rows = read_spreadsheet_rows("staff.csv", content)
    assert rows == [["Name", "Subject"], ["Mrs. Sharma", "Math"], ["Mr. Rao", "Science"]]


def test_read_spreadsheet_rows_xlsx():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Name", "Subject"])
    ws.append(["Mrs. Sharma", "Math"])
    buf = io.BytesIO()
    wb.save(buf)
    rows = read_spreadsheet_rows("staff.xlsx", buf.getvalue())
    assert rows == [["Name", "Subject"], ["Mrs. Sharma", "Math"]]


def test_read_spreadsheet_rows_rejects_unsupported_type():
    with pytest.raises(ValueError):
        read_spreadsheet_rows("staff.pdf", b"whatever")


def test_read_spreadsheet_rows_rejects_empty_file():
    with pytest.raises(ValueError):
        read_spreadsheet_rows("staff.csv", b"\n\n")


def test_extract_setup_llm_returns_none_for_empty_rows():
    assert extract_setup_llm([]) is None


def test_extract_setup_llm_returns_none_without_api_key():
    assert settings.anthropic_api_key is None
    assert extract_setup_llm([["Name"], ["Mrs. Sharma"]]) is None


def test_extract_setup_llm_returns_tool_input_on_success():
    # NOTE: MagicMock(name=...) is reserved for the mock's own repr name, not
    # an attribute — set .name afterwards instead, or block.name would be a
    # Mock object, not the string the real code checks against.
    fake_block = MagicMock(
        type="tool_use",
        input={"teachers": [{"name": "Mrs. Sharma", "subject_names": ["Math"]}], "subjects": [{"name": "Math"}],
               "class_groups": [], "notes": ""},
    )
    fake_block.name = "record_extracted_setup"
    fake_response = MagicMock(content=[fake_block])
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_anthropic_cls.return_value.messages.create.return_value = fake_response
            result = extract_setup_llm([["Name", "Subject"], ["Mrs. Sharma", "Math"]])
    assert result["teachers"][0]["name"] == "Mrs. Sharma"


def test_extract_setup_llm_returns_none_on_api_failure():
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic", side_effect=ConnectionError("boom")):
            result = extract_setup_llm([["Name"], ["Mrs. Sharma"]])
    assert result is None


def test_extract_setup_llm_returns_none_when_tool_not_used():
    fake_response = MagicMock(content=[MagicMock(type="text", text="I couldn't find a tool to use.")])
    with patch.object(settings, "anthropic_api_key", "fake-key"):
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_anthropic_cls.return_value.messages.create.return_value = fake_response
            result = extract_setup_llm([["Name"], ["Mrs. Sharma"]])
    assert result is None

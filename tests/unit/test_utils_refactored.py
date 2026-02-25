"""Tests for refactored utility functions."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

from slcli.utils import sanitize_filename, extract_error_type, parse_inner_errors


def test_sanitize_filename() -> None:
    """Test filename sanitization."""
    # Basic case
    assert sanitize_filename("Test Name") == "test-name"

    # Special characters
    assert sanitize_filename("Test & Name!") == "test-name"

    # Multiple spaces
    assert sanitize_filename("Test   Multiple   Spaces") == "test-multiple-spaces"

    # Already clean name
    assert sanitize_filename("test-name") == "test-name"

    # Empty string
    assert sanitize_filename("", "fallback") == "fallback"

    # Only special characters
    assert sanitize_filename("!!!@@@", "fallback") == "fallback"

    # Apostrophes and quotes
    assert sanitize_filename("Darren's Test Template") == "darrens-test-template"


def test_extract_error_type() -> None:
    """Test error type extraction."""
    # Full class name
    assert (
        extract_error_type("Skyline.WorkOrder.WorkflowNotFoundOrNoAccess")
        == "WorkflowNotFoundOrNoAccess"
    )

    # Simple name
    assert extract_error_type("ValidationError") == "ValidationError"

    # Empty string
    assert extract_error_type("") == ""


def test_parse_inner_errors() -> None:
    """Test inner error parsing."""
    inner_errors = [
        {
            "name": "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess",
            "message": "Workflow not found",
            "resourceId": "123",
            "resourceType": "workflow",
        },
        {"name": "ValidationError", "message": "Invalid input", "resourceId": "456"},
    ]

    result = parse_inner_errors(inner_errors)

    assert len(result) == 2
    assert result[0]["type"] == "WorkflowNotFoundOrNoAccess"
    assert result[0]["message"] == "Workflow not found"
    assert result[0]["resource_id"] == "123"
    assert result[0]["resource_type"] == "workflow"

    assert result[1]["type"] == "ValidationError"
    assert result[1]["message"] == "Invalid input"
    assert result[1]["resource_id"] == "456"
    assert result[1]["resource_type"] == ""


def test_parse_inner_errors_empty() -> None:
    """Test parsing empty inner errors list."""
    result = parse_inner_errors([])
    assert result == []


class TestMakeApiRequestHttpMethods:
    """Tests for make_api_request HTTP method dispatch."""

    def _patch_keyring(self, monkeypatch: Any) -> None:
        """Patch keyring to return a minimal config."""
        import keyring

        config = {"api_url": "http://localhost:8000", "api_key": "dummy-key", "platform": "SLE"}

        monkeypatch.setattr(
            keyring,
            "get_password",
            lambda *a, **kw: json.dumps(config),
        )

    def test_patch_method_dispatches_to_requests_patch(self, monkeypatch: Any) -> None:
        """make_api_request with PATCH calls requests.patch."""
        self._patch_keyring(monkeypatch)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with patch("requests.patch", return_value=mock_response) as mock_patch:
            from slcli.utils import make_api_request

            result = make_api_request("PATCH", "http://localhost:8000/api/v1/resource/1")

        mock_patch.assert_called_once()
        call_kwargs = mock_patch.call_args
        assert call_kwargs[0][0] == "http://localhost:8000/api/v1/resource/1"
        assert result is mock_response

    def test_patch_method_sends_payload(self, monkeypatch: Any) -> None:
        """make_api_request with PATCH forwards the JSON payload."""
        self._patch_keyring(monkeypatch)

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        payload = {"message": "updated text"}

        with patch("requests.patch", return_value=mock_response) as mock_patch:
            from slcli.utils import make_api_request

            make_api_request("PATCH", "http://localhost:8000/api/v1/resource/1", payload=payload)

        _, call_kwargs = mock_patch.call_args
        assert call_kwargs.get("json") == payload

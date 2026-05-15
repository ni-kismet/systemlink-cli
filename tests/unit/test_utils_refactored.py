"""Tests for refactored utility functions."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from slcli.utils import (
    ExitCodes,
    _extract_response_error_message,
    extract_error_type,
    handle_api_error,
    parse_inner_errors,
    sanitize_filename,
)


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


def test_handle_api_error_forbidden(capsys: Any) -> None:
    """Forbidden errors should map to permission denied."""
    with pytest.raises(SystemExit) as exc_info:
        handle_api_error(Exception("403 Forbidden"))

    captured = capsys.readouterr()
    assert exc_info.value.code == ExitCodes.PERMISSION_DENIED
    assert "Permission denied" in captured.err


def _make_http_error(status_code: int, body: Any) -> requests.HTTPError:
    """Create a requests.HTTPError with a mock response containing the given JSON body."""
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code
    response.json.return_value = body
    exc = requests.HTTPError(
        f"{status_code} Client Error: Bad Request for url: https://example.com/api"
    )
    exc.response = response
    return exc


def test_handle_api_error_extracts_error_message(capsys: Any) -> None:
    """Server error body message should be shown instead of generic HTTP status."""
    exc = _make_http_error(
        400,
        {"error": {"message": "Workspace 'Fred' was not found.", "code": -251046}},
    )
    with pytest.raises(SystemExit) as exc_info:
        handle_api_error(exc)

    captured = capsys.readouterr()
    assert exc_info.value.code == ExitCodes.NOT_FOUND
    assert "Workspace 'Fred' was not found." in captured.err


def test_handle_api_error_extracts_toplevel_message(capsys: Any) -> None:
    """Top-level message field from the response body should be displayed."""
    exc = _make_http_error(400, {"message": "Something went wrong"})
    with pytest.raises(SystemExit) as exc_info:
        handle_api_error(exc)

    captured = capsys.readouterr()
    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    assert "Something went wrong" in captured.err


def test_handle_api_error_falls_back_without_json(capsys: Any) -> None:
    """Error without parseable JSON should fall back to the exception string."""
    response = MagicMock(spec=requests.Response)
    response.json.side_effect = ValueError("No JSON")
    exc = requests.HTTPError("400 Bad Request for url: https://example.com/api")
    exc.response = response

    with pytest.raises(SystemExit) as exc_info:
        handle_api_error(exc)

    captured = capsys.readouterr()
    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    assert "400 Bad Request" in captured.err


def test_handle_api_error_permission_from_response_body(capsys: Any) -> None:
    """403 response with a body message should still map to permission denied."""
    exc = _make_http_error(
        403,
        {"error": {"message": "Unauthorized access to workspace"}},
    )
    with pytest.raises(SystemExit) as exc_info:
        handle_api_error(exc)

    captured = capsys.readouterr()
    assert exc_info.value.code == ExitCodes.PERMISSION_DENIED
    assert "Unauthorized access to workspace" in captured.err


def test_extract_response_error_message_no_response() -> None:
    """Plain Exception without a response attribute returns None."""
    assert _extract_response_error_message(Exception("boom")) is None


def test_extract_response_error_message_nested_error() -> None:
    """SystemLink-style nested error body is extracted."""
    exc = _make_http_error(
        400,
        {"error": {"message": "Invalid input", "name": "Skyline.Validation"}},
    )
    assert _extract_response_error_message(exc) == "Invalid input"


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

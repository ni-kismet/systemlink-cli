"""Tests for refactored utility functions."""

from slcli.utils import sanitize_filename, extract_error_type, parse_inner_errors


def test_sanitize_filename():
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


def test_extract_error_type():
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


def test_parse_inner_errors():
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


def test_parse_inner_errors_empty():
    """Test parsing empty inner errors list."""
    result = parse_inner_errors([])
    assert result == []

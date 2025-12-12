"""Unit tests for feed_click.py."""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from slcli.feed_click import register_feed_commands


def make_cli() -> click.Group:
    """Create a test CLI with feed commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_feed_commands(test_cli)
    return test_cli


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        json_data: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        text: str = "",
    ) -> None:
        """Initialize mock response.

        Args:
            json_data: The JSON data to return from json().
            status_code: The HTTP status code.
            text: The response text.
        """
        self._json_data = json_data or {}
        self._status_code = status_code
        self._text = text

    def json(self) -> Dict[str, Any]:
        return self._json_data

    @property
    def status_code(self) -> int:
        return self._status_code

    @property
    def text(self) -> str:
        return self._text

    def raise_for_status(self) -> None:
        if self._status_code >= 400:
            from requests.exceptions import HTTPError

            raise HTTPError(f"HTTP {self._status_code}")


@pytest.fixture(autouse=True)
def mock_workspace_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent workspace lookups from hitting keyring or network in unit tests."""
    monkeypatch.setattr("slcli.feed_click.get_workspace_map", lambda: {})
    monkeypatch.setattr(
        "slcli.feed_click.get_workspace_id_with_fallback", lambda workspace: workspace
    )


# =============================================================================
# Feed List Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_list_table_format_sle(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed list command with table format for SLE."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "feeds": [
                {
                    "id": "feed-1",
                    "name": "TestFeed",
                    "platform": "WINDOWS",
                    "workspace": "ws-1",
                },
                {
                    "id": "feed-2",
                    "name": "LinuxFeed",
                    "platform": "NI_LINUX_RT",
                    "workspace": "ws-2",
                },
            ],
            "totalCount": 2,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "list", "--format", "table"])

    assert result.exit_code == 0
    assert "TestFeed" in result.output
    assert "LinuxFeed" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_list_json_format_sle(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed list command with JSON format for SLE."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "feeds": [
                {
                    "id": "feed-1",
                    "name": "TestFeed",
                    "platform": "WINDOWS",
                    "workspace": "ws-1",
                }
            ],
            "totalCount": 1,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "list", "--format", "json"])

    assert result.exit_code == 0
    assert "feed-1" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_list_table_format_sls(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed list command with table format for SLS."""
    mock_detect.return_value = "SLS"
    mock_request.return_value = MockResponse(
        json_data={
            "feeds": [
                {
                    "id": "feed-1",
                    "name": "ServerFeed",
                    "platform": "windows",
                    "workspace": "",
                }
            ],
            "totalCount": 1,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "list", "--format", "table"])

    assert result.exit_code == 0
    assert "ServerFeed" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_list_empty(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed list command with no feeds."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(json_data={"feeds": [], "totalCount": 0})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "list", "--format", "table"])

    assert result.exit_code == 0
    assert "No feeds found" in result.output


# =============================================================================
# Feed Get Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_get_by_id(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed get command by ID."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "id": "feed-123",
            "name": "MyFeed",
            "platform": "WINDOWS",
            "workspace": "ws-1",
            "description": "A test feed",
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "get", "--id", "feed-123"])

    assert result.exit_code == 0
    assert "feed-123" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_get_json_format(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed get command with JSON format."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "id": "feed-123",
            "name": "MyFeed",
            "platform": "WINDOWS",
            "workspace": "ws-1",
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "get", "--id", "feed-123", "--format", "json"])

    assert result.exit_code == 0
    assert '"id"' in result.output


# =============================================================================
# Feed Create Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_create_sle(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed create command for SLE."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "id": "new-feed-id",
            "name": "NewFeed",
            "platform": "WINDOWS",
            "workspace": "ws-1",
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "feed",
            "create",
            "--name",
            "NewFeed",
            "--platform",
            "windows",
            "--workspace",
            "ws-1",
        ],
    )

    assert result.exit_code == 0, f"Failed with: {result.output}"
    assert (
        "created" in result.output.lower() or "new-feed-id" in result.output or "✓" in result.output
    )


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_create_case_insensitive_platform(
    mock_request: MagicMock, mock_detect: MagicMock
) -> None:
    """Test feed create command with case-insensitive platform."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "id": "new-feed-id",
            "name": "NewFeed",
            "platform": "WINDOWS",
            "workspace": "ws-1",
        }
    )

    cli = make_cli()
    runner = CliRunner()

    # Test with lowercase
    result = runner.invoke(
        cli,
        [
            "feed",
            "create",
            "--name",
            "NewFeed",
            "--platform",
            "windows",
            "--workspace",
            "ws-1",
        ],
    )
    assert result.exit_code == 0

    # Test with uppercase
    result = runner.invoke(
        cli,
        [
            "feed",
            "create",
            "--name",
            "NewFeed",
            "--platform",
            "WINDOWS",
            "--workspace",
            "ws-1",
        ],
    )
    assert result.exit_code == 0

    # Test with mixed case
    result = runner.invoke(
        cli,
        [
            "feed",
            "create",
            "--name",
            "NewFeed",
            "--platform",
            "Windows",
            "--workspace",
            "ws-1",
        ],
    )
    assert result.exit_code == 0


# =============================================================================
# Feed Delete Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_delete(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed delete command."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(status_code=200)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "delete", "--id", "feed-123", "--yes"])

    assert result.exit_code == 0


# =============================================================================
# Feed Package List Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_package_list(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed package list command."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "packages": [
                {
                    "id": "pkg-1",
                    "metadata": {
                        "packageName": "test-package",
                        "version": "1.0.0",
                        "architecture": "x64",
                    },
                }
            ],
            "totalCount": 1,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["feed", "package", "list", "--feed-id", "feed-123", "--format", "table"]
    )

    assert result.exit_code == 0
    assert "test-package" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_package_list_json(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed package list command with JSON format."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "packages": [
                {
                    "id": "pkg-1",
                    "metadata": {
                        "packageName": "test-package",
                        "version": "1.0.0",
                    },
                }
            ],
            "totalCount": 1,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["feed", "package", "list", "--feed-id", "feed-123", "--format", "json"]
    )

    assert result.exit_code == 0
    assert "pkg-1" in result.output


# =============================================================================
# Feed Job List Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_job_list(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed job list command."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "jobs": [
                {
                    "id": "job-1",
                    "type": "UPLOAD_PACKAGE",
                    "status": "SUCCEEDED",
                    "createdAt": "2024-01-01T00:00:00Z",
                }
            ],
            "totalCount": 1,
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "job", "list", "--format", "table"])

    assert result.exit_code == 0
    assert "job-1" in result.output or "SUCCEEDED" in result.output


@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_feed_job_get(mock_request: MagicMock, mock_detect: MagicMock) -> None:
    """Test feed job get command."""
    mock_detect.return_value = "SLE"
    mock_request.return_value = MockResponse(
        json_data={
            "id": "job-123",
            "type": "REPLICATE",
            "status": "SUCCEEDED",
            "createdAt": "2024-01-01T00:00:00Z",
            "completedAt": "2024-01-01T00:05:00Z",
        }
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "job", "get", "--id", "job-123"])

    assert result.exit_code == 0
    assert "job-123" in result.output


# =============================================================================
# Platform Detection Tests
# =============================================================================


@patch("slcli.feed_click.make_api_request")
@patch("slcli.feed_click.get_platform")
def test_feed_list_with_api_error(mock_detect: MagicMock, mock_request: MagicMock) -> None:
    """Test feed commands handle API errors gracefully."""
    mock_detect.return_value = "SLE"

    # Simulate API error
    from requests.exceptions import HTTPError

    mock_request.side_effect = HTTPError("404 Not Found")

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["feed", "list"])

    assert result.exit_code != 0


# =============================================================================
# Platform Normalization Tests
# =============================================================================


@patch("slcli.feed_click.get_platform")
def test_normalize_platform_windows_sle(mock_get_platform: MagicMock) -> None:
    """Test platform normalization for windows on SLE."""
    from slcli.feed_click import _normalize_platform

    mock_get_platform.return_value = "SLE"

    # SLE expects uppercase
    assert _normalize_platform("windows") == "WINDOWS"
    assert _normalize_platform("WINDOWS") == "WINDOWS"
    assert _normalize_platform("Windows") == "WINDOWS"


@patch("slcli.feed_click.get_platform")
def test_normalize_platform_windows_sls(mock_get_platform: MagicMock) -> None:
    """Test platform normalization for windows on SLS."""
    from slcli.feed_click import _normalize_platform

    mock_get_platform.return_value = "SLS"

    # SLS expects lowercase
    assert _normalize_platform("windows") == "windows"
    assert _normalize_platform("WINDOWS") == "windows"
    assert _normalize_platform("Windows") == "windows"


@patch("slcli.feed_click.get_platform")
def test_normalize_platform_linux_rt_sle(mock_get_platform: MagicMock) -> None:
    """Test platform normalization for NI Linux RT on SLE."""
    from slcli.feed_click import _normalize_platform

    mock_get_platform.return_value = "SLE"

    # SLE expects NI_LINUX_RT
    assert _normalize_platform("ni-linux-rt") == "NI_LINUX_RT"
    assert _normalize_platform("NI_LINUX_RT") == "NI_LINUX_RT"
    assert _normalize_platform("ni_linux_rt") == "NI_LINUX_RT"


@patch("slcli.feed_click.get_platform")
def test_normalize_platform_linux_rt_sls(mock_get_platform: MagicMock) -> None:
    """Test platform normalization for NI Linux RT on SLS."""
    from slcli.feed_click import _normalize_platform

    mock_get_platform.return_value = "SLS"

    # SLS expects ni-linux-rt
    assert _normalize_platform("ni-linux-rt") == "ni-linux-rt"
    assert _normalize_platform("NI_LINUX_RT") == "ni-linux-rt"
    assert _normalize_platform("ni_linux_rt") == "ni-linux-rt"


# =============================================================================
# Wait Flag Tests
# =============================================================================


@patch("slcli.feed_click.time.sleep")
@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_replicate_with_wait(
    mock_request: MagicMock, mock_detect: MagicMock, mock_sleep: MagicMock
) -> None:
    """Test replicate command with --wait flag."""
    mock_detect.return_value = "SLE"

    # First call creates the job, second call checks status
    mock_request.side_effect = [
        MockResponse(json_data={"jobId": "job-123"}),
        MockResponse(
            json_data={
                "id": "job-123",
                "status": "SUCCEEDED",
                "type": "REPLICATE",
                "resourceId": "new-feed-id",
            }
        ),
    ]

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "feed",
            "replicate",
            "--name",
            "MyReplicatedFeed",
            "--platform",
            "windows",
            "--url",
            "https://source-feed.example.com",
            "--wait",
        ],
    )

    assert result.exit_code == 0, f"Failed with: {result.output}"
    assert "replicated" in result.output.lower() or "✓" in result.output


@patch("slcli.feed_click.time.sleep")
@patch("slcli.feed_click.get_platform")
@patch("slcli.feed_click.make_api_request")
def test_replicate_with_wait_polls_until_complete(
    mock_request: MagicMock, mock_detect: MagicMock, mock_sleep: MagicMock
) -> None:
    """Test replicate command polls until job completes."""
    mock_detect.return_value = "SLE"

    # First call creates the job, subsequent calls check status
    mock_request.side_effect = [
        MockResponse(json_data={"jobId": "job-123"}),
        MockResponse(json_data={"id": "job-123", "status": "QUEUED"}),
        MockResponse(json_data={"id": "job-123", "status": "IN_PROGRESS"}),
        MockResponse(json_data={"id": "job-123", "status": "SUCCEEDED", "resourceId": "feed-id"}),
    ]

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "feed",
            "replicate",
            "--name",
            "MyReplicatedFeed",
            "--platform",
            "windows",
            "--url",
            "https://source-feed.example.com",
            "--wait",
        ],
    )

    assert result.exit_code == 0, f"Failed with: {result.output}"
    # Verify sleep was called for polling
    assert mock_sleep.call_count >= 2

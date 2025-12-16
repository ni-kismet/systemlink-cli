"""Unit tests for file CLI commands."""

import builtins
import json
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.file_click import register_file_commands
from slcli.utils import ExitCodes


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def make_cli() -> click.Group:
    """Create CLI instance with file commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_file_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class MockResponse:
    """Mock response class for requests."""

    def __init__(self, json_data: Any, status_code: int = 200) -> None:
        """Initialize mock response.

        Args:
            json_data: Data to return from json() method
            status_code: HTTP status code to return
        """
        self._json_data = json_data
        self.status_code = status_code
        self.content = b"test file content"

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")

    def iter_content(self, chunk_size: int = 8192) -> Any:
        yield self.content


# --- Test file list command ---


def test_list_files_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing files with a successful response."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file1",
                        "properties": {"Name": "test-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                        "created": "2024-01-15T10:30:00.000Z",
                    },
                    {
                        "id": "file2",
                        "properties": {"Name": "data.csv"},
                        "size": 2048,
                        "size64": 2048,
                        "created": "2024-01-16T14:00:00.000Z",
                    },
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "list"])
    assert result.exit_code == 0
    assert "test-file.txt" in result.output
    assert "data.csv" in result.output


def test_list_files_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing files when no files exist."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"availableFiles": []})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "list"])
    assert result.exit_code == 0
    assert "No files found" in result.output


def test_list_files_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing files with JSON output."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file1",
                        "properties": {"Name": "test-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                        "created": "2024-01-15T10:30:00.000Z",
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "file1"
    assert data[0]["properties"]["Name"] == "test-file.txt"


def test_list_files_with_workspace(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing files filtered by workspace."""
    patch_keyring(monkeypatch)

    captured_payloads: list = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        if "json" in kw:
            captured_payloads.append(kw["json"])
        return MockResponse({"availableFiles": []})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "list", "--workspace", "ws-123"])
    assert result.exit_code == 0
    assert len(captured_payloads) > 0
    # search-files uses workspaceId:("id") syntax
    assert 'workspaceId:("ws-123")' in captured_payloads[0].get("filter", "")


def test_list_files_with_name_filter(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing files with name filter."""
    patch_keyring(monkeypatch)

    captured_payloads: list = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        if "json" in kw:
            captured_payloads.append(kw["json"])
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file1",
                        "properties": {"Name": "test-file.txt"},
                        "size64": 1024,
                        "created": "2024-01-15T10:30:00.000Z",
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "list", "--filter", "test"])
    assert result.exit_code == 0
    assert len(captured_payloads) > 0
    filter_str = captured_payloads[0].get("filter", "")
    # search-files uses name:("*search*") OR extension:("*search*") syntax
    assert 'name:("*test*")' in filter_str
    assert 'extension:("*test*")' in filter_str


# --- Test file get command ---


def test_get_file_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting file metadata."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {
                            "Name": "test-document.pdf",
                            "author": "test",
                            "version": "1.0",
                        },
                        "size": 10240,
                        "size64": 10240,
                        "created": "2024-01-15T10:30:00.000Z",
                        "workspace": "ws-abc",
                        "serviceGroup": "Default",
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "get", "file123"])
    assert result.exit_code == 0
    assert "test-document.pdf" in result.output
    assert "file123" in result.output
    assert "ws-abc" in result.output


def test_get_file_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting file metadata with JSON output."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "test-document.pdf"},
                        "size": 10240,
                        "size64": 10240,
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "get", "file123", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "file123"
    assert data["properties"]["Name"] == "test-document.pdf"


def test_get_file_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting file that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"availableFiles": []})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "get", "nonexistent"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


# --- Test file upload command ---


def test_upload_file_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test uploading a file."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        # API returns a uri field with the file path
        return MockResponse({"uri": "/nifile/v1/service-groups/Default/files/new-file-123"})

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", lambda *a, **kw: MockResponse({}))
    cli = make_cli()

    with runner.isolated_filesystem():
        # Create a test file
        with open("test.txt", "w") as f:
            f.write("test content")

        result = runner.invoke(cli, ["file", "upload", "test.txt"])
        assert result.exit_code == 0
        assert "uploaded successfully" in result.output.lower()
        assert "new-file-123" in result.output


def test_upload_file_with_workspace(monkeypatch: Any, runner: CliRunner) -> None:
    """Test uploading a file to a specific workspace."""
    patch_keyring(monkeypatch)

    captured_urls: list = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        if a:
            captured_urls.append(a[0])
        return MockResponse({"uri": "/nifile/v1/service-groups/Default/files/new-file-123"})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    with runner.isolated_filesystem():
        with open("test.txt", "w") as f:
            f.write("test content")

        result = runner.invoke(cli, ["file", "upload", "test.txt", "--workspace", "ws-target"])
        assert result.exit_code == 0
        # Workspace should be in query string
        assert any("workspace=ws-target" in url for url in captured_urls)


def test_upload_file_with_custom_name(monkeypatch: Any, runner: CliRunner) -> None:
    """Test uploading a file with a custom name."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"uri": "/nifile/v1/service-groups/Default/files/new-file-123"})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    with runner.isolated_filesystem():
        with open("test.txt", "w") as f:
            f.write("test content")

        result = runner.invoke(cli, ["file", "upload", "test.txt", "--name", "custom-name.txt"])
        assert result.exit_code == 0
        assert "uploaded successfully" in result.output.lower()


def test_upload_file_with_properties(monkeypatch: Any, runner: CliRunner) -> None:
    """Test uploading a file with properties."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"uri": "/nifile/v1/service-groups/Default/files/new-file-123"})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    with runner.isolated_filesystem():
        with open("test.txt", "w") as f:
            f.write("test content")

        result = runner.invoke(
            cli,
            [
                "file",
                "upload",
                "test.txt",
                "--properties",
                '{"author": "test", "version": "1.0"}',
            ],
        )
        assert result.exit_code == 0


def test_upload_file_invalid_properties_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test uploading a file with invalid properties JSON."""
    patch_keyring(monkeypatch)
    cli = make_cli()

    with runner.isolated_filesystem():
        with open("test.txt", "w") as f:
            f.write("test content")

        result = runner.invoke(
            cli,
            ["file", "upload", "test.txt", "--properties", "invalid-json"],
        )
        assert result.exit_code != 0
        assert "Invalid JSON" in result.output


def test_upload_file_nonexistent(runner: CliRunner) -> None:
    """Test uploading a file that doesn't exist."""
    cli = make_cli()

    result = runner.invoke(cli, ["file", "upload", "/nonexistent/path/to/file.txt"])
    assert result.exit_code != 0
    assert "does not exist" in result.output.lower() or "no such file" in result.output.lower()


# --- Test file download command ---


def test_download_file_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test downloading a file."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        # For _get_file_by_id query
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "downloaded-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ]
            }
        )

    def mock_get(*a: Any, **kw: Any) -> Any:
        # For file data download
        resp: Any = MockResponse(b"file content")
        resp.content = b"test file content"
        return resp

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["file", "download", "file123"])
        assert result.exit_code == 0
        assert "downloaded successfully" in result.output.lower()


def test_download_file_custom_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test downloading a file to a custom location."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "original.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ]
            }
        )

    def mock_get(*a: Any, **kw: Any) -> Any:
        resp: Any = MockResponse(b"file content")
        resp.content = b"test file content"
        return resp

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["file", "download", "file123", "--output", "custom-name.txt"])
        assert result.exit_code == 0
        assert "custom-name.txt" in result.output


def test_download_file_overwrite_cancelled(monkeypatch: Any, runner: CliRunner) -> None:
    """Test downloading a file with existing file and user cancels overwrite."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "existing-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    with runner.isolated_filesystem():
        # Create existing file
        with open("existing-file.txt", "w") as f:
            f.write("existing content")

        result = runner.invoke(cli, ["file", "download", "file123"], input="n\n")
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()


def test_download_file_force_overwrite(monkeypatch: Any, runner: CliRunner) -> None:
    """Test downloading a file with force overwrite."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "existing-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ]
            }
        )

    def mock_get(*a: Any, **kw: Any) -> Any:
        resp: Any = MockResponse(b"file content")
        resp.content = b"new file content"
        return resp

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    with runner.isolated_filesystem():
        # Create existing file
        with open("existing-file.txt", "w") as f:
            f.write("existing content")

        result = runner.invoke(cli, ["file", "download", "file123", "--force"])
        assert result.exit_code == 0
        assert "downloaded successfully" in result.output.lower()


# --- Test file delete command ---


def test_delete_file_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a file with confirmation."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        """Mock POST for query-files-linq metadata lookup."""
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "file-to-delete.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ],
                "totalCount": 1,
            }
        )

    def mock_delete(*a: Any, **kw: Any) -> Any:
        return MockResponse({})

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.delete", mock_delete)
    cli = make_cli()

    result = runner.invoke(cli, ["file", "delete", "--id", "file123"], input="y\n")
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_delete_file_force(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a file with force flag."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        """Mock POST for query-files-linq metadata lookup."""
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "file-to-delete.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ],
                "totalCount": 1,
            }
        )

    def mock_delete(*a: Any, **kw: Any) -> Any:
        return MockResponse({})

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.delete", mock_delete)
    cli = make_cli()

    result = runner.invoke(cli, ["file", "delete", "--id", "file123", "--force"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_delete_file_cancelled(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a file when user cancels."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        """Mock POST for query-files-linq metadata lookup."""
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file123",
                        "properties": {"Name": "file-to-keep.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ],
                "totalCount": 1,
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    result = runner.invoke(cli, ["file", "delete", "--id", "file123"], input="n\n")
    assert result.exit_code == 0
    assert "cancelled" in result.output.lower()


# --- Test file query command ---


def test_query_files_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test querying files with search filter."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file1",
                        "properties": {"Name": "test-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                        "created": "2024-01-15T10:30:00.000Z",
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    # search-files uses name:("*test*") syntax
    result = runner.invoke(cli, ["file", "query", "--filter", 'name:("*test*")'])
    assert result.exit_code == 0
    assert "test-file.txt" in result.output


def test_query_files_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test querying files with JSON output."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {
                "availableFiles": [
                    {
                        "id": "file1",
                        "properties": {"Name": "test-file.txt"},
                        "size": 1024,
                        "size64": 1024,
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["file", "query", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1


def test_query_files_empty_result(monkeypatch: Any, runner: CliRunner) -> None:
    """Test querying files with no matching results."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"availableFiles": []})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    # search-files uses name:("value") syntax
    result = runner.invoke(cli, ["file", "query", "--filter", 'name:("nonexistent")'])
    assert result.exit_code == 0
    assert "No files match" in result.output


# --- Test file update-metadata command ---


def test_update_metadata_name(monkeypatch: Any, runner: CliRunner) -> None:
    """Test updating file name."""
    patch_keyring(monkeypatch)

    post_count = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        post_count[0] += 1
        # First POST is query-files-linq, second is update-metadata
        if post_count[0] == 1:
            return MockResponse(
                {
                    "availableFiles": [
                        {
                            "id": "file123",
                            "properties": {"Name": "old-name.txt", "key": "value"},
                        }
                    ]
                }
            )
        return MockResponse({})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    result = runner.invoke(cli, ["file", "update-metadata", "file123", "--name", "new-name.txt"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_update_metadata_add_property(monkeypatch: Any, runner: CliRunner) -> None:
    """Test adding a property to file metadata."""
    patch_keyring(monkeypatch)

    post_count = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        post_count[0] += 1
        if post_count[0] == 1:
            return MockResponse(
                {
                    "availableFiles": [
                        {
                            "id": "file123",
                            "properties": {"Name": "test.txt", "existing": "1"},
                        }
                    ]
                }
            )
        return MockResponse({})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    result = runner.invoke(
        cli, ["file", "update-metadata", "file123", "--add-property", "newkey=newvalue"]
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_update_metadata_name_and_properties(monkeypatch: Any, runner: CliRunner) -> None:
    """Test update-metadata with both --name and --properties to verify name takes precedence."""
    patch_keyring(monkeypatch)

    captured_payloads: list = []
    post_count = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        post_count[0] += 1
        if "json" in kw:
            captured_payloads.append(kw["json"])
        # First POST is query-files-linq, second is update-metadata
        if post_count[0] == 1:
            return MockResponse(
                {"availableFiles": [{"id": "file123", "properties": {"Name": "old.txt"}}]}
            )
        return MockResponse({})

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    # Pass --properties with a Name that should be overwritten by --name
    result = runner.invoke(
        cli,
        [
            "file",
            "update-metadata",
            "file123",
            "--name",
            "cli-name.txt",
            "--properties",
            '{"Name": "json-name.txt", "author": "test"}',
        ],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()
    # Verify the --name flag takes precedence over Name in --properties
    assert len(captured_payloads) >= 2
    update_payload = captured_payloads[-1]
    assert update_payload["properties"]["Name"] == "cli-name.txt"
    assert update_payload["properties"]["author"] == "test"


def test_update_metadata_no_updates(monkeypatch: Any, runner: CliRunner) -> None:
    """Test update-metadata with no updates specified."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {"availableFiles": [{"id": "file123", "properties": {"Name": "test.txt"}}]}
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    result = runner.invoke(cli, ["file", "update-metadata", "file123"])
    assert result.exit_code != 0
    assert "No updates specified" in result.output


def test_update_metadata_invalid_property_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test update-metadata with invalid property format."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {"availableFiles": [{"id": "file123", "properties": {"Name": "test.txt"}}]}
        )

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    result = runner.invoke(
        cli, ["file", "update-metadata", "file123", "--add-property", "invalid-format"]
    )
    assert result.exit_code != 0
    assert "key=value" in result.output


# --- Test file watch command ---


def test_watch_mutually_exclusive_options(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that --move-to and --delete-after-upload are mutually exclusive."""
    patch_keyring(monkeypatch)
    cli = make_cli()

    with runner.isolated_filesystem():
        import os

        os.makedirs("watch-dir")
        os.makedirs("move-dir")

        result = runner.invoke(
            cli,
            [
                "file",
                "watch",
                "watch-dir",
                "--move-to",
                "move-dir",
                "--delete-after-upload",
            ],
        )
        assert result.exit_code != 0
        assert "Cannot use both" in result.output


def test_watch_requires_watchdog(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that watch command requires watchdog package."""
    patch_keyring(monkeypatch)

    # Mock the import to fail by patching sys.modules
    import sys as sys_module

    # Remove watchdog from modules if present and make import fail
    for key in list(sys_module.modules.keys()):
        if "watchdog" in key:
            del sys_module.modules[key]

    # Patch the import mechanism
    original_import = builtins.__import__

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if "watchdog" in name:
            raise ImportError("No module named 'watchdog'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    cli = make_cli()

    with runner.isolated_filesystem():
        import os

        os.makedirs("watch-dir")

        result = runner.invoke(cli, ["file", "watch", "watch-dir"])
        assert result.exit_code != 0
        assert "watchdog" in result.output.lower()


def test_watch_folder_mutually_exclusive(monkeypatch: Any, runner: CliRunner) -> None:
    """Ensure watch rejects mutually exclusive move/delete options."""
    patch_keyring(monkeypatch)
    cli = make_cli()

    with runner.isolated_filesystem():
        import os

        os.makedirs("watch-dir")
        result = runner.invoke(
            cli,
            [
                "file",
                "watch",
                "watch-dir",
                "--move-to",
                "archived",
                "--delete-after-upload",
            ],
        )

        assert result.exit_code == ExitCodes.INVALID_INPUT
        assert "Cannot use both --move-to and --delete-after-upload" in result.output


# --- Test helper functions ---


def test_format_file_size() -> None:
    """Test file size formatting."""
    from slcli.file_click import _format_file_size

    assert _format_file_size(None) == "N/A"
    assert "B" in _format_file_size(500)
    assert "KB" in _format_file_size(1024)
    assert "MB" in _format_file_size(1024 * 1024)
    assert "GB" in _format_file_size(1024 * 1024 * 1024)


def test_format_timestamp() -> None:
    """Test timestamp formatting."""
    from slcli.file_click import _format_timestamp

    assert _format_timestamp(None) == "N/A"
    assert _format_timestamp("") == "N/A"
    assert _format_timestamp("2024-01-15T10:30:00.000Z") == "2024-01-15 10:30:00"

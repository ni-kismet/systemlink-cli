"""Unit tests for state CLI commands."""

import json
from pathlib import Path
from typing import Any, Dict, Optional, cast

import click
import pytest
import requests
from click.testing import CliRunner

from slcli.state_click import register_state_commands
from slcli.utils import ExitCodes
from .test_utils import patch_keyring


def make_cli() -> click.Group:
    """Create a CLI instance with state commands registered."""

    @click.group()
    def cli() -> None:
        pass

    register_state_commands(cli)
    return cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(autouse=True)
def disable_readonly(monkeypatch: Any) -> None:
    """Keep tests focused on state command behavior."""
    monkeypatch.setattr("slcli.state_click.check_readonly_mode", lambda _operation: None)


class MockResponse:
    """Mock response object for requests-based tests."""

    def __init__(
        self,
        json_data: Optional[Any] = None,
        status_code: int = 200,
        content: bytes = b"",
        headers: Optional[Dict[str, str]] = None,
        chunks: Optional[list[bytes]] = None,
    ) -> None:
        """Initialize a mock response payload for requests-based tests."""
        self._json_data = json_data
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._chunks = chunks or ([content] if content else [])

    @property
    def text(self) -> str:
        if self.content:
            return self.content.decode("utf-8")
        if self._json_data is None:
            return ""
        return json.dumps(self._json_data)

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("No JSON payload")
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=cast(requests.Response, self))

    def iter_content(self, chunk_size: int = 8192) -> Any:
        """Yield content chunks like requests.Response.iter_content."""
        del chunk_size
        yield from self._chunks


def _workspace_response() -> MockResponse:
    return MockResponse(
        {
            "workspaces": [{"id": "ws-1", "name": "Default"}],
            "totalCount": 1,
        }
    )


def test_list_states_table_format(monkeypatch: Any, runner: CliRunner) -> None:
    """List should render state rows with workspace names."""
    patch_keyring(monkeypatch)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return _workspace_response()
        return MockResponse(
            {
                "totalCount": 1,
                "states": [
                    {
                        "id": "state-1",
                        "name": "DAQmx 19.5",
                        "distribution": "WINDOWS",
                        "architecture": "X64",
                        "workspace": "ws-1",
                        "containsExtraOperations": True,
                        "lastUpdatedTimestamp": "2026-04-27T12:00:00Z",
                    }
                ],
            }
        )

    monkeypatch.setattr("requests.get", mock_get)

    result = runner.invoke(make_cli(), ["state", "list"])
    assert result.exit_code == 0
    assert "DAQmx 19.5" in result.output
    assert "Default" in result.output


def test_list_states_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """JSON list output should emit the raw state array."""
    patch_keyring(monkeypatch)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return _workspace_response()
        return MockResponse(
            {
                "totalCount": 1,
                "states": [{"id": "state-1", "name": "DAQmx 19.5"}],
            }
        )

    monkeypatch.setattr("requests.get", mock_get)

    result = runner.invoke(make_cli(), ["state", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == [{"id": "state-1", "name": "DAQmx 19.5"}]


def test_get_state_table_format(monkeypatch: Any, runner: CliRunner) -> None:
    """State get should print the expected summary view."""
    patch_keyring(monkeypatch)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return _workspace_response()
        return MockResponse(
            {
                "id": "state-1",
                "name": "DAQmx 19.5",
                "description": "Windows state",
                "distribution": "WINDOWS",
                "architecture": "X64",
                "workspace": "ws-1",
                "containsExtraOperations": True,
                "feeds": [{"name": "feed-1", "url": "https://example.test/feed"}],
                "packages": [{"name": "pkg-1", "version": "1.0.0"}],
            }
        )

    monkeypatch.setattr("requests.get", mock_get)

    result = runner.invoke(make_cli(), ["state", "get", "state-1"])
    assert result.exit_code == 0
    assert "State Details" in result.output
    assert "Contains Extra Operations: Yes" in result.output
    assert "feed-1" in result.output
    assert "pkg-1" in result.output


def test_create_state_from_flags(monkeypatch: Any, runner: CliRunner) -> None:
    """Create should resolve workspace names and pass typed JSON options through."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return _workspace_response()
        raise AssertionError(f"Unexpected GET {url}")

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return MockResponse({"id": "state-1", "name": "DAQmx 19.5"})

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)

    result = runner.invoke(
        make_cli(),
        [
            "state",
            "create",
            "--name",
            "DAQmx 19.5",
            "--distribution",
            "WINDOWS",
            "--architecture",
            "X64",
            "--workspace",
            "Default",
            "--property",
            "channel=prod",
            "--feed",
            '{"name": "feed-1", "url": "https://example.test/feed"}',
            "--package",
            '{"name": "pkg-1", "version": "1.0.0"}',
            "--system-image",
            '{"name": "base-image", "version": "1.0"}',
        ],
    )

    assert result.exit_code == 0
    assert captured["json"] == {
        "name": "DAQmx 19.5",
        "distribution": "WINDOWS",
        "architecture": "X64",
        "workspace": "ws-1",
        "properties": {"channel": "prod"},
        "feeds": [{"name": "feed-1", "url": "https://example.test/feed"}],
        "packages": [{"name": "pkg-1", "version": "1.0.0"}],
        "systemImage": {"name": "base-image", "version": "1.0"},
    }


def test_update_state_with_request_and_properties(monkeypatch: Any, runner: CliRunner) -> None:
    """Update should merge request-file payloads with explicit CLI overrides."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_patch(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return MockResponse({"id": "state-1", "name": "Updated State"})

    monkeypatch.setattr("requests.patch", mock_patch)

    with runner.isolated_filesystem():
        request_path = Path("update.json")
        request_path.write_text(json.dumps({"description": "old description"}), encoding="utf-8")

        result = runner.invoke(
            make_cli(),
            [
                "state",
                "update",
                "state-1",
                "--request",
                str(request_path),
                "--name",
                "Updated State",
                "--property",
                "stage=validated",
            ],
        )

    assert result.exit_code == 0
    assert captured["json"] == {
        "description": "old description",
        "name": "Updated State",
        "properties": {"stage": "validated"},
    }


def test_create_state_preserves_request_workspace(monkeypatch: Any, runner: CliRunner) -> None:
    """Request-file workspaces should be preserved when no CLI workspace override is provided."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return MockResponse(
                {
                    "workspaces": [
                        {"id": "ws-1", "name": "Default"},
                        {"id": "ws-2", "name": "Other"},
                    ],
                    "totalCount": 2,
                }
            )
        raise AssertionError(f"Unexpected GET {url}")

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["json"] = kwargs.get("json")
        return MockResponse({"id": "state-1", "name": "DAQmx 19.5"})

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        request_path = Path("create.json")
        request_path.write_text(
            json.dumps(
                {
                    "name": "DAQmx 19.5",
                    "distribution": "WINDOWS",
                    "architecture": "X64",
                    "workspace": "Other",
                }
            ),
            encoding="utf-8",
        )

        result = runner.invoke(make_cli(), ["state", "create", "--request", str(request_path)])

    assert result.exit_code == 0
    assert captured["json"]["workspace"] == "ws-2"


def test_export_state_streams_to_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Export should request a streamed POST response and write iterated chunks."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["stream"] = kwargs.get("stream")
        return MockResponse(
            content=b"",
            chunks=[b"state:", b" exported\n"],
            headers={"Content-Disposition": 'attachment; filename="saved-state.sls"'},
        )

    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        result = runner.invoke(make_cli(), ["state", "export", "state-1"])
        assert result.exit_code == 0
        assert captured["stream"] is True
        assert Path("saved-state.sls").read_text(encoding="utf-8") == "state: exported\n"


def test_capture_state_streams_to_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Capture should request a streamed POST response and write iterated chunks."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["stream"] = kwargs.get("stream")
        return MockResponse(content=b"", chunks=[b"captured:", b" state\n"])

    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        result = runner.invoke(make_cli(), ["state", "capture", "system-1", "--output", "out.sls"])
        assert result.exit_code == 0
        assert captured["stream"] is True
        assert Path("out.sls").read_text(encoding="utf-8") == "captured: state\n"


def test_delete_state_yes(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete should accept the yes flag and call the delete endpoint."""
    patch_keyring(monkeypatch)

    def mock_delete(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(status_code=204)

    monkeypatch.setattr("requests.delete", mock_delete)

    result = runner.invoke(make_cli(), ["state", "delete", "state-1", "--yes"])
    assert result.exit_code == 0
    assert "State deleted" in result.output


def test_import_state_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Import should submit multipart form data using the API's field names."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        if "/niuser/v1/workspaces" in url:
            return _workspace_response()
        raise AssertionError(f"Unexpected GET {url}")

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        return MockResponse({"id": "state-1", "name": "Imported State"})

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        input_path = Path("input.sls")
        input_path.write_text("state: content\n", encoding="utf-8")

        result = runner.invoke(
            make_cli(),
            [
                "state",
                "import",
                "--name",
                "Imported State",
                "--distribution",
                "WINDOWS",
                "--architecture",
                "X64",
                "--workspace",
                "Default",
                "--property",
                "channel=prod",
                "--file",
                str(input_path),
            ],
        )

    assert result.exit_code == 0
    assert captured["data"]["Name"] == "Imported State"
    assert captured["data"]["Workspace"] == "ws-1"
    assert json.loads(captured["data"]["Properties"]) == {"channel": "prod"}
    assert captured["files"]["File"][0] == "input.sls"


def test_replace_state_content_success(monkeypatch: Any, runner: CliRunner) -> None:
    """replace-content should send the expected multipart fields."""
    patch_keyring(monkeypatch)
    captured: Dict[str, Any] = {}

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        return MockResponse({"id": "state-1", "name": "Updated State"})

    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        input_path = Path("replacement.sls")
        input_path.write_text("replacement: content\n", encoding="utf-8")

        result = runner.invoke(
            make_cli(),
            [
                "state",
                "replace-content",
                "state-1",
                "--file",
                str(input_path),
                "--change-description",
                "Refresh package list",
            ],
        )

    assert result.exit_code == 0
    assert captured["data"] == {"Id": "state-1", "ChangeDescription": "Refresh package list"}
    assert captured["files"]["File"][0] == "replacement.sls"


def test_export_state_to_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Export should write the returned payload to disk."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(
            content=b"state: exported\n",
            headers={"Content-Disposition": 'attachment; filename="saved-state.sls"'},
        )

    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        result = runner.invoke(make_cli(), ["state", "export", "state-1"])
        assert result.exit_code == 0
        assert Path("saved-state.sls").read_text(encoding="utf-8") == "state: exported\n"


def test_export_state_inline(monkeypatch: Any, runner: CliRunner) -> None:
    """Export inline should write the state content to stdout."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        assert kwargs["json"] == {"state": {"stateID": "state-1"}, "inline": True}
        return MockResponse(content=b"state: inline\n")

    monkeypatch.setattr("requests.post", mock_post)

    result = runner.invoke(make_cli(), ["state", "export", "state-1", "--inline"])
    assert result.exit_code == 0
    assert result.output == "state: inline\n"


def test_capture_state_to_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Capture should write the generated system state file to disk."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        assert kwargs["json"] == {"systemID": "system-1"}
        return MockResponse(content=b"captured: state\n")

    monkeypatch.setattr("requests.post", mock_post)

    with runner.isolated_filesystem():
        result = runner.invoke(make_cli(), ["state", "capture", "system-1", "--output", "out.sls"])
        assert result.exit_code == 0
        assert Path("out.sls").read_text(encoding="utf-8") == "captured: state\n"


def test_state_history_table(monkeypatch: Any, runner: CliRunner) -> None:
    """History should paginate and render version rows."""
    patch_keyring(monkeypatch)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(
            {
                "totalCount": 1,
                "versions": [
                    {
                        "version": "v1",
                        "description": "Initial version",
                        "createdTimestamp": "2026-04-27T12:00:00Z",
                        "userId": "user-1",
                    }
                ],
            }
        )

    monkeypatch.setattr("requests.get", mock_get)

    result = runner.invoke(make_cli(), ["state", "history", "state-1"])
    assert result.exit_code == 0
    assert "Initial version" in result.output
    assert "user-1" in result.output


def test_state_version_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Version should return raw JSON when requested."""
    patch_keyring(monkeypatch)

    def mock_get(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse({"id": "state-1", "name": "Historical State", "version": "v1"})

    monkeypatch.setattr("requests.get", mock_get)

    result = runner.invoke(make_cli(), ["state", "version", "state-1", "v1", "--format", "json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["name"] == "Historical State"


def test_revert_state_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Revert should treat 204 as success."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        assert kwargs["json"] == {"id": "state-1", "version": "v1"}
        return MockResponse(status_code=204)

    monkeypatch.setattr("requests.post", mock_post)

    result = runner.invoke(make_cli(), ["state", "revert", "state-1", "v1", "--yes"])
    assert result.exit_code == 0
    assert "State reverted" in result.output


def test_revert_state_error_body(monkeypatch: Any, runner: CliRunner) -> None:
    """Revert should surface the API error body when the service responds with HTTP 200."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(
            {
                "error": {
                    "message": "Cannot revert to the requested version.",
                    "innerErrors": [{"message": "Version not found."}],
                }
            },
            status_code=200,
        )

    monkeypatch.setattr("requests.post", mock_post)

    result = runner.invoke(make_cli(), ["state", "revert", "state-1", "missing", "--yes"])
    assert result.exit_code == ExitCodes.GENERAL_ERROR
    assert "Cannot revert to the requested version." in result.output
    assert "Version not found." in result.output


def test_create_state_conflict_returns_invalid_input(monkeypatch: Any, runner: CliRunner) -> None:
    """Conflict responses should map to INVALID_INPUT for state create."""
    patch_keyring(monkeypatch)

    def mock_post(url: str, *args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(
            {"error": {"message": "A state with this name already exists."}},
            status_code=409,
        )

    monkeypatch.setattr("requests.post", mock_post)

    result = runner.invoke(
        make_cli(),
        [
            "state",
            "create",
            "--name",
            "DAQmx 19.5",
            "--distribution",
            "WINDOWS",
            "--architecture",
            "X64",
        ],
    )
    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "already exists" in result.output

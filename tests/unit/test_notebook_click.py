"""Unit tests for slcli notebook commands."""

import os
import tempfile
from typing import Any

# Shared test utilities
from click.testing import CliRunner
from pytest import MonkeyPatch

from slcli.main import cli
from slcli.platform import PLATFORM_SLE, PLATFORM_SLS
from slcli.utils import ExitCodes
from .test_utils import patch_keyring


def test_notebook_list(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)
    notebooks = [
        {"id": "abc123", "name": "TestNotebook1"},
        {"id": "def456", "name": "TestNotebook2"},
    ]

    # Patch _query_notebooks_http to return mock notebooks
    import slcli.notebook_click
    from typing import Any

    class MockResponse:
        def __init__(self, data: dict[str, Any]):
            self._data = data

        def json(self) -> dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

    def mock_query_notebooks_http(
        filter_str: str | None = None, take: int = 1000
    ) -> list[dict[str, Any]]:
        return notebooks

    monkeypatch.setattr(
        slcli.notebook_click,
        "_query_notebooks_http",
        mock_query_notebooks_http,
    )
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})
    result = runner.invoke(cli, ["notebook", "manage", "list"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "TestNotebook1" in result.output
    assert "TestNotebook2" in result.output


def test_notebook_list_with_filter(monkeypatch: MonkeyPatch) -> None:
    """Ensure custom filter combines with workspace filter."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import slcli.notebook_click
    import slcli.utils

    captured: dict[str, Any] = {}

    def mock_validate_workspace_access(workspace: str, warn_on_error: bool = True) -> str:
        return "ws-123"

    def mock_query(filter_str: str | None = None, take: int = 1000) -> list[dict[str, Any]]:
        captured["filter"] = filter_str
        return [
            {
                "id": "abc123",
                "name": "TestNotebook",
                "workspace": "ws-123",
                "properties": {"interface": "File Analysis"},
            }
        ]

    monkeypatch.setattr(
        slcli.notebook_click, "validate_workspace_access", mock_validate_workspace_access
    )
    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {"ws-123": "WS"})
    monkeypatch.setattr(slcli.notebook_click, "_query_notebooks_http", mock_query)

    result = runner.invoke(
        cli,
        [
            "notebook",
            "manage",
            "list",
            "--workspace",
            "Default",
            "--filter",
            "Test",
        ],
    )

    assert result.exit_code == 0
    assert (
        captured.get("filter")
        == 'workspace = "ws-123" and (name.ToLower().Contains("test") or properties.interface.ToLower().Contains("test"))'
    )
    assert "TestNotebook" in result.output


def test_notebook_download_by_id(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)
    content = b"notebook-bytes"

    # Patch _get_notebook_content_http to return mock content
    import slcli.notebook_click

    def mock_get_notebook_content_http(notebook_id: str) -> bytes:
        return content

    monkeypatch.setattr(
        slcli.notebook_click,
        "_get_notebook_content_http",
        mock_get_notebook_content_http,
    )
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.close()
        result = runner.invoke(
            cli,
            [
                "notebook",
                "manage",
                "download",
                "--id",
                "abc123",
                "--output",
                tmp.name,
                "--type",
                "content",
            ],
        )
        assert result.exit_code == 0
        with open(tmp.name, "rb") as f:
            assert f.read() == content
        os.unlink(tmp.name)


def test_notebook_upload(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    # Patch _create_notebook_http to return a mock result
    import slcli.notebook_click
    from typing import Any

    class MockResponse:
        def __init__(self, data: dict[str, Any]):
            self._data = data

        def json(self) -> dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 201

    def mock_create_notebook_http(name: str, workspace: str, content: bytes) -> dict[str, Any]:
        return {"id": "uploaded123"}

    def mock_query_notebooks_http(
        filter_str: str | None = None, take: int = 1000
    ) -> list[dict[str, Any]]:
        return []

    monkeypatch.setattr(
        slcli.notebook_click,
        "_create_notebook_http",
        mock_create_notebook_http,
    )
    monkeypatch.setattr(
        slcli.notebook_click,
        "_query_notebooks_http",
        mock_query_notebooks_http,
    )
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test-nb")
        tmp.close()
        result = runner.invoke(
            cli, ["notebook", "manage", "create", "--file", tmp.name, "--name", "TestNotebook"]
        )
        assert result.exit_code == 0
        assert "uploaded123" in result.output
        os.unlink(tmp.name)


def test_notebook_update_requires_payload(monkeypatch: MonkeyPatch) -> None:
    """Update should fail when no metadata or content provided."""
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    monkeypatch.setattr(slcli.notebook_click, "get_platform", lambda: PLATFORM_SLE)

    result = runner.invoke(cli, ["notebook", "manage", "update", "--id", "nb1"])

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "Must provide at least one" in result.output


def test_notebook_update_rejected_on_sls(monkeypatch: MonkeyPatch) -> None:
    """Update should reject on SLS platforms."""
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    monkeypatch.setattr(slcli.notebook_click, "get_platform", lambda: PLATFORM_SLS)

    result = runner.invoke(
        cli,
        ["notebook", "manage", "update", "--id", "nb1", "--metadata", __file__],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "not supported" in result.output


def test_notebook_execute_sync_success(monkeypatch: MonkeyPatch) -> None:
    """Execute sync should emit completion output when execution finishes immediately."""
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    monkeypatch.setattr(slcli.notebook_click, "get_platform", lambda: PLATFORM_SLE)
    monkeypatch.setattr(
        slcli.notebook_click, "_build_create_execution_payload", lambda **_: {"id": "payload"}
    )

    def fake_parse(resp_data: Any, is_sls: bool) -> list[dict[str, Any]]:
        return [
            {
                "id": "exec-1",
                "status": "SUCCEEDED",
                "result": {"ok": True},
                "cachedResult": False,
            }
        ]

    class PostResp:
        def json(self) -> Any:
            return {}

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(slcli.notebook_click, "_parse_execution_response", fake_parse)
    monkeypatch.setattr(slcli.notebook_click.requests, "post", lambda *a, **k: PostResp())

    result = runner.invoke(
        cli,
        [
            "notebook",
            "execute",
            "sync",
            "--notebook-id",
            "nb1",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert '"exec-1"' in result.output


def test_set_notebook_interface_valid(monkeypatch: MonkeyPatch) -> None:
    """Test setting a valid interface on a notebook."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import slcli.notebook_click

    def mock_set_interface(notebook_id: str, interface: str) -> dict[str, Any]:
        return {
            "id": "abc123",
            "name": "test-notebook",
            "properties": {"interface": interface},
        }

    monkeypatch.setattr(
        slcli.notebook_click,
        "_set_notebook_interface_http",
        mock_set_interface,
    )

    def mock_get_notebook(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "id": "abc123",
            "name": "test-notebook",
            "workspace": "default-workspace",
        }

    monkeypatch.setattr(slcli.notebook_click, "_get_notebook_http", mock_get_notebook)

    result = runner.invoke(
        cli,
        [
            "notebook",
            "manage",
            "set-interface",
            "--id",
            "abc123",
            "--interface",
            "File Analysis",
        ],
    )
    assert result.exit_code == 0
    assert "Interface assigned" in result.output
    assert "File Analysis" in result.output


def test_set_notebook_interface_invalid(monkeypatch: MonkeyPatch) -> None:
    """Test that invalid interface is rejected."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    result = runner.invoke(
        cli,
        [
            "notebook",
            "manage",
            "set-interface",
            "--id",
            "abc123",
            "--interface",
            "Invalid Interface",
        ],
    )
    assert result.exit_code != 0


def test_set_notebook_interface_sls_not_supported(monkeypatch: MonkeyPatch) -> None:
    """Test that interface assignment fails on SLS."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import slcli.notebook_click

    # Mock platform to be SLS
    monkeypatch.setattr(slcli.notebook_click, "get_platform", lambda: PLATFORM_SLS)

    result = runner.invoke(
        cli,
        [
            "notebook",
            "manage",
            "set-interface",
            "--id",
            "abc123",
            "--interface",
            "File Analysis",
        ],
    )
    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "not supported" in result.output


def test_list_notebooks_with_interface(monkeypatch: MonkeyPatch) -> None:
    """Test that list command displays interface column."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    notebooks = [
        {
            "id": "abc123",
            "name": "TestNotebook1",
            "properties": {"interface": "File Analysis"},
        },
        {
            "id": "def456",
            "name": "TestNotebook2",
            "properties": {"interface": "Data Table Analysis"},
        },
    ]

    import slcli.notebook_click
    import slcli.utils

    def mock_query(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return notebooks

    monkeypatch.setattr(slcli.notebook_click, "_query_notebooks_http", mock_query)
    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    result = runner.invoke(cli, ["notebook", "manage", "list"])
    assert result.exit_code == 0
    assert "File Analysis" in result.output
    assert "Data Table Analysis" in result.output

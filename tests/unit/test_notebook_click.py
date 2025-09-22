"""Unit tests for slcli notebook commands."""

import os
import tempfile

# Shared test utilities
from click.testing import CliRunner
from pytest import MonkeyPatch

from slcli.main import cli
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

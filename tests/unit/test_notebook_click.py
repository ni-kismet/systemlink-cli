"""Unit tests for slcli notebook commands."""

import os
import tempfile

# Shared test utilities
from click.testing import CliRunner

from slcli.main import cli
from .test_utils import patch_keyring


def test_notebook_list(monkeypatch):
    runner = CliRunner()
    patch_keyring(monkeypatch)
    notebooks = [
        {"id": "abc123", "name": "TestNotebook1"},
        {"id": "def456", "name": "TestNotebook2"},
    ]

    # Patch NotebookClient.query_notebooks to return mock paged result
    import slcli.notebook_click

    class MockNotebook:
        def __init__(self, nb):
            for k, v in nb.items():
                setattr(self, k, v)
            self.__dict__ = nb

    class MockPagedResult:
        def __init__(self, notebooks):
            self.notebooks = [MockNotebook(nb) for nb in notebooks]
            self.continuation_token = None

    monkeypatch.setattr(
        slcli.notebook_click.NotebookClient,
        "query_notebooks",
        lambda self, query: MockPagedResult(notebooks),
    )
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})
    result = runner.invoke(cli, ["notebook", "list"])
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "TestNotebook1" in result.output
    assert "TestNotebook2" in result.output


def test_notebook_download_by_id(monkeypatch):
    runner = CliRunner()
    patch_keyring(monkeypatch)
    content = b"notebook-bytes"

    # Patch NotebookClient.get_notebook_content to return a BytesIO
    import slcli.notebook_click
    import io

    monkeypatch.setattr(
        slcli.notebook_click.NotebookClient,
        "get_notebook_content",
        lambda self, notebook_id: io.BytesIO(content),
    )
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.close()
        result = runner.invoke(
            cli,
            ["notebook", "download", "--id", "abc123", "--output", tmp.name, "--type", "content"],
        )
        assert result.exit_code == 0
        with open(tmp.name, "rb") as f:
            assert f.read() == content
        os.unlink(tmp.name)


def test_notebook_upload(monkeypatch):
    runner = CliRunner()
    patch_keyring(monkeypatch)

    # Patch NotebookClient.create_notebook to return a mock result
    import slcli.notebook_click

    class MockCreateResult:
        id = "uploaded123"

    class MockPagedResult:
        def __init__(self):
            self.notebooks = []
            self.continuation_token = None

        def __iter__(self):
            return iter(self.notebooks)

    monkeypatch.setattr(
        slcli.notebook_click.NotebookClient,
        "create_notebook",
        lambda self, metadata, content: MockCreateResult(),
    )
    monkeypatch.setattr(
        slcli.notebook_click.NotebookClient,
        "query_notebooks",
        lambda self, query: MockPagedResult(),
    )
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test-nb")
        tmp.close()
        result = runner.invoke(
            cli, ["notebook", "create", "--file", tmp.name, "--name", "TestNotebook"]
        )
        assert result.exit_code == 0
        assert "uploaded123" in result.output
        os.unlink(tmp.name)

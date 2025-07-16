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

    def mock_post(*args, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                # The CLI expects a dict with a 'notebooks' key
                return {"notebooks": notebooks}

        return Resp()

    # Also mock get_workspace_map to avoid KeyError or API call
    import slcli.utils

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})
    result = runner.invoke(cli, ["notebook", "list"])
    # Print output for debugging if test fails
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    assert "TestNotebook1" in result.output
    assert "TestNotebook2" in result.output


def test_notebook_download_by_id(monkeypatch):
    runner = CliRunner()
    patch_keyring(monkeypatch)
    content = b"notebook-bytes"

    def mock_get(*args, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            @property
            def content(self):
                return content

        return Resp()

    monkeypatch.setattr("requests.get", mock_get)
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

    def mock_post(*args, **kwargs):
        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "uploaded123"}

        return Resp()

    monkeypatch.setattr("requests.post", mock_post)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test-nb")
        tmp.close()
        result = runner.invoke(
            cli, ["notebook", "create", "--file", tmp.name, "--name", "TestNotebook"]
        )
        assert result.exit_code == 0
        assert "uploaded123" in result.output
        os.unlink(tmp.name)

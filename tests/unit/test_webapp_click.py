"""Unit tests for slcli webapp commands."""

from typing import Any, Dict
from pathlib import Path

from click.testing import CliRunner
from pytest import MonkeyPatch

from slcli.main import cli
from .test_utils import patch_keyring


def test_webapp_init_creates_index(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "webapp_skel"
    result = runner.invoke(cli, ["webapp", "init", "--directory", str(target)])
    assert result.exit_code == 0
    idx = target / "app" / "index.html"
    assert idx.exists()
    content = idx.read_text(encoding="utf-8")
    assert "Example WebApp" in content


def test_webapp_pack_creates_nipkg(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "index.html").write_text("hello")

    out = tmp_path / "site_out.nipkg"
    result = runner.invoke(cli, ["webapp", "pack", str(folder), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    # verify it's a Debian-style ar archive (.nipkg)
    with open(out, "rb") as f:
        magic = f.read(8)
    assert magic == b"!<arch>\n"

    # Simple check that the archive contains the standard members by searching bytes
    data = out.read_bytes()
    assert b"debian-binary" in data
    assert b"control.tar.gz" in data
    assert b"data.tar.gz" in data


def test_webapp_list_shows_items(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> MockResp:
        return MockResp(
            {"webapps": [{"id": "a1", "name": "AppOne", "workspace": "ws1", "type": "WebVI"}]}
        )

    monkeypatch.setattr(requests, "post", mock_post)
    # patch workspace map
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    result = runner.invoke(cli, ["webapp", "list"])
    assert result.exit_code == 0
    assert "AppOne" in result.output


def test_webapp_list_paging_default(monkeypatch: MonkeyPatch) -> None:
    """Default take should be 25 and the CLI should offer to show the next 25."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def make_items(start: int, count: int) -> list:
        return [
            {"id": f"id{n}", "name": f"App{n}", "workspace": "ws1", "type": "WebVI"}
            for n in range(start, start + count)
        ]

    # Create two pages: 25 items, then 5 items
    pages = [make_items(1, 25), make_items(26, 5)]
    call = {"i": 0}

    def mock_post(url: str, **kwargs: Any) -> Any:
        i = call["i"]
        call["i"] += 1
        data: Dict[str, Any] = {"webapps": pages[i]}
        # Add continuation token on first page
        if i == 0:
            data["continuationToken"] = "tok1"
        return MockResp(data)

    monkeypatch.setattr(requests, "post", mock_post)
    # patch workspace map
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    # Simulate user answering 'n' to the "Show next set of results?" prompt
    result = runner.invoke(cli, ["webapp", "list"], input="n\n")
    assert result.exit_code == 0
    # Should show the prompt to ask for next set
    assert "Show next set of results?" in result.output
    # Should contain first page item but not an item from the second page
    assert "App1" in result.output
    assert "App26" not in result.output


def test_webapp_list_paging_custom_take(monkeypatch: MonkeyPatch) -> None:
    """When the user specifies --take 10 the CLI should page by 10 and offer next 10."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def make_items(start: int, count: int) -> list:
        return [
            {"id": f"id{n}", "name": f"App{n}", "workspace": "ws1", "type": "WebVI"}
            for n in range(start, start + count)
        ]

    # Pages of 10, 10, 5
    pages = [make_items(1, 10), make_items(11, 10), make_items(21, 5)]
    call = {"i": 0}

    def mock_post(url: str, **kwargs: Any) -> Any:
        i = call["i"]
        call["i"] += 1
        data: Dict[str, Any] = {"webapps": pages[i]}
        if i < 2:
            data["continuationToken"] = f"tok{i+1}"
        return MockResp(data)

    monkeypatch.setattr(requests, "post", mock_post)
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    # Simulate user answering 'y' to fetch second page, then 'n' to stop before third
    result = runner.invoke(cli, ["webapp", "list", "--take", "10"], input="y\nn\n")
    assert result.exit_code == 0
    assert "Show next set of results?" in result.output
    # First and second page items should be present, third page should not
    assert "App1" in result.output
    assert "App20" in result.output
    assert "App21" not in result.output


def test_webapp_get_shows_metadata(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def mock_get(url: str, **kwargs: Any) -> Any:
        return MockResp({"id": "abc", "name": "MyApp", "properties": {}, "type": "WebVI"})

    monkeypatch.setattr(requests, "get", mock_get)
    result = runner.invoke(cli, ["webapp", "get", "--id", "abc"])
    assert result.exit_code == 0
    assert "MyApp" in result.output


def test_webapp_publish_creates_and_uploads(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    # create a source folder to publish
    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "index.html").write_text("hi")

    import requests

    class MockPostResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 201

        def raise_for_status(self) -> None:
            return None

    class MockPutResp:
        text = ""

        @property
        def status_code(self) -> int:
            return 204

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> Any:
        return MockPostResp({"id": "new-webapp-id"})

    def mock_put(url: str, **kwargs: Any) -> Any:
        return MockPutResp()

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "put", mock_put)

    result = runner.invoke(
        cli, ["webapp", "publish", str(folder), "--name", "NewApp", "--workspace", "Default"]
    )
    assert result.exit_code == 0
    assert "Published webapp content" in result.output or "Created webapp metadata" in result.output

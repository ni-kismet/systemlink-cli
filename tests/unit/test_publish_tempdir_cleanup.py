"""Tests for publish tempdir cleanup behavior."""

from pathlib import Path
from typing import Any, Dict

from click.testing import CliRunner
from pytest import MonkeyPatch

from slcli.main import cli


def test_publish_cleans_temporary_directory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # Prepare a small folder to publish
    src = tmp_path / "site"
    src.mkdir()
    (src / "index.html").write_text("hi")

    # Spy object to capture cleanup call
    class TempDirSpy:
        def __init__(self) -> None:
            self.name = str(tmp_path / "td")
            self.cleaned = False

        def cleanup(self) -> None:
            self.cleaned = True

        # Make this object usable as a context manager to mirror
        # tempfile.TemporaryDirectory() behavior when used with 'with'.
        def __enter__(self) -> str:
            return self.name

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            self.cleanup()

    spy = TempDirSpy()

    # Monkeypatch TemporaryDirectory to return our spy
    def fake_tempdir() -> TempDirSpy:
        return spy

    monkeypatch.setattr("tempfile.TemporaryDirectory", fake_tempdir)

    # Mock network calls so publishing only exercises local packaging and cleanup
    import requests

    class MockPostResp:
        def __init__(self, data: Dict[str, Any]) -> None:
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

    def mock_post(url: str, **kwargs: Any) -> MockPostResp:
        return MockPostResp({"id": "new-webapp-id"})

    def mock_put(url: str, **kwargs: Any) -> MockPutResp:
        return MockPutResp()

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "put", mock_put)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["webapp", "publish", str(src), "--name", "X", "--workspace", "Default"]
    )
    assert result.exit_code == 0

    # Ensure our TemporaryDirectory spy had cleanup called
    assert getattr(spy, "cleaned", False) is True

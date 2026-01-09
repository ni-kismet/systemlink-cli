from __future__ import annotations

import sys
from pathlib import Path

import pytest

from slcli.web_editor import DFFWebEditor

ESSENTIAL_FILES = ["index.html", "editor.js", "README.md"]


def _make_assets(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for name in ESSENTIAL_FILES:
        (base / name).write_text(f"src-{name}")


def _assert_copied(target: Path) -> None:
    for name in ESSENTIAL_FILES:
        assert (target / name).read_text() == f"src-{name}"


def test_source_from_meipass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    meipass = tmp_path / "meipass"
    _make_assets(meipass / "dff-editor")

    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    target = tmp_path / "out"
    target.mkdir()
    editor = DFFWebEditor(port=0, output_dir=str(target))

    editor._create_editor_files("{}", None)

    _assert_copied(target)


def test_source_from_frozen_onedir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    app_dir = tmp_path / "appdir"
    assets = app_dir / "dff-editor"
    _make_assets(assets)

    fake_executable = app_dir / "slcli"
    fake_executable.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_executable))

    target = tmp_path / "out"
    target.mkdir()
    editor = DFFWebEditor(port=0, output_dir=str(target))

    editor._create_editor_files("{}", None)

    _assert_copied(target)


def test_source_from_site_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import slcli.web_editor as web_editor

    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    site_root = tmp_path / "site-packages"
    slcli_pkg = site_root / "slcli"
    slcli_pkg.mkdir(parents=True)

    fake_module_file = slcli_pkg / "web_editor.py"
    monkeypatch.setattr(web_editor, "__file__", str(fake_module_file))

    _make_assets(site_root / "dff-editor")

    target = tmp_path / "out"
    target.mkdir()
    editor = DFFWebEditor(port=0, output_dir=str(target))

    editor._create_editor_files("{}", None)

    _assert_copied(target)

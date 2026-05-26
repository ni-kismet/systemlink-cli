"""Regression tests for release packaging metadata."""

import json
import os
from pathlib import Path
from typing import Any

from scripts import build_homebrew, build_pyinstaller, build_scoop


def test_render_formula_installs_binary_contents(tmp_path: Path, monkeypatch: Any) -> None:
    """The Homebrew formula should install the staged archive contents into libexec."""
    output_path = tmp_path / "homebrew-slcli.rb"
    monkeypatch.setattr(build_homebrew, "DIST_FORMULA", output_path)

    build_homebrew.render_formula("linux-sha", "macos-sha", "macos-intel-sha", "1.2.3")

    rendered = output_path.read_text(encoding="utf-8")

    assert (
        'url "https://github.com/ni-kismet/systemlink-cli/releases/download/v1.2.3/slcli-linux.tar.gz"'
        in rendered
    )
    assert (
        'url "https://github.com/ni-kismet/systemlink-cli/releases/download/v1.2.3/slcli-macos.tar.gz"'
        in rendered
    )
    assert (
        'url "https://github.com/ni-kismet/systemlink-cli/releases/download/v1.2.3/slcli-macos-15-intel.tar.gz"'
        in rendered
    )
    assert 'libexec.install Dir["*"]' in rendered
    assert 'bin.install_symlink libexec/"slcli"' in rendered


def test_render_manifest_matches_release_zip_layout(tmp_path: Path, monkeypatch: Any) -> None:
    """The Scoop manifest should point at the release ZIP and extracted executable layout."""
    output_path = tmp_path / "scoop-slcli.json"
    monkeypatch.setattr(build_scoop, "DIST_MANIFEST", output_path)

    build_scoop.render_manifest(
        "1.2.3",
        "https://github.com/ni-kismet/systemlink-cli/releases/download/v1.2.3/slcli.zip",
        "ABC123",
    )

    manifest = json.loads(output_path.read_text(encoding="utf-8"))

    assert manifest["version"] == "1.2.3"
    assert manifest["architecture"]["64bit"]["url"] == (
        "https://github.com/ni-kismet/systemlink-cli/releases/download/v1.2.3/slcli.zip"
    )
    assert manifest["architecture"]["64bit"]["hash"] == "ABC123"
    assert manifest["extract_dir"] == "slcli"
    assert manifest["bin"] == "slcli.exe"


def test_optional_data_args_skips_missing_directory(tmp_path: Path, capsys: Any) -> None:
    """Skip optional directories that are intentionally absent from PyInstaller packaging."""
    args = build_pyinstaller._optional_data_args(tmp_path / "missing", "skills")

    assert args == []
    assert "Skipping optional data directory missing" in capsys.readouterr().out


def test_optional_data_args_includes_existing_directory(tmp_path: Path) -> None:
    """Include optional directories in PyInstaller packaging when they exist."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    args = build_pyinstaller._optional_data_args(skills_dir, "skills")

    assert args == ["--add-data", f"{skills_dir}{os.pathsep}skills"]

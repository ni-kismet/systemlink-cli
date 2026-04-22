"""Unit tests for the Towncrier release helper script."""

from pathlib import Path
from typing import Any

from scripts.towncrier_release import (
    apply_release,
    bump_version,
    determine_version_bump,
    get_fragment_type,
    get_next_version,
    replace_poetry_version,
)


def test_get_fragment_type_handles_duplicate_suffix() -> None:
    """Duplicate Towncrier suffixes still preserve the fragment type."""
    assert get_fragment_type(Path("123.patch.1.md")) == "patch"


def test_determine_version_bump_prefers_highest_priority() -> None:
    """Major fragments take precedence over minor and patch fragments."""
    assert determine_version_bump(["patch", "minor", "major"]) == "major"


def test_bump_version_applies_patch_for_documentation_changes() -> None:
    """Documentation fragments still trigger a patch release."""
    assert bump_version("1.9.3", "patch") == "1.9.4"


def test_replace_poetry_version_updates_tool_poetry_section_only() -> None:
    """Only the tool.poetry version field should be rewritten."""
    pyproject_text = (
        "[tool.poetry]\n"
        'name = "systemlink-cli"\n'
        'version = "1.9.3"\n\n'
        "[tool.other]\n"
        'version = "leave-me-alone"\n'
    )

    updated = replace_poetry_version(pyproject_text, "1.10.0")

    assert 'version = "1.10.0"' in updated
    assert 'version = "leave-me-alone"' in updated


def test_get_next_version_uses_fragment_types(tmp_path: Path) -> None:
    """The next release version is inferred from Towncrier fragments."""
    (tmp_path / "newsfragments").mkdir()
    (tmp_path / "newsfragments" / "123.minor.md").write_text("Add a new command.\n")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\n" 'name = "systemlink-cli"\n' 'version = "1.9.3"\n',
        encoding="utf-8",
    )

    assert get_next_version(tmp_path) == "1.10.0"


def test_apply_release_updates_version_files_and_builds_changelog(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Applying a release rewrites versions and invokes Towncrier build."""
    (tmp_path / "newsfragments").mkdir()
    (tmp_path / "newsfragments" / "123.patch.md").write_text("Fix a bug.\n")
    (tmp_path / "slcli").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\n" 'name = "systemlink-cli"\n' 'version = "1.9.3"\n',
        encoding="utf-8",
    )

    calls = []

    def mock_run(command: list[str], cwd: Path, check: bool) -> None:
        calls.append((command, cwd, check))

    monkeypatch.setattr("scripts.towncrier_release.subprocess.run", mock_run)

    applied_version = apply_release(tmp_path)

    assert applied_version == "1.9.4"
    assert 'version = "1.9.4"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert '__version__ = "1.9.4"' in (tmp_path / "slcli" / "_version.py").read_text(
        encoding="utf-8"
    )
    assert len(calls) == 1
    assert calls[0][1] == tmp_path
    assert calls[0][2] is True
    assert calls[0][0][1:] == ["-m", "towncrier", "build", "--yes", "--version", "1.9.4"]


def test_apply_release_returns_none_without_fragments(tmp_path: Path) -> None:
    """No Towncrier fragments means there is no release to prepare."""
    (tmp_path / "newsfragments").mkdir()
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\n" 'name = "systemlink-cli"\n' 'version = "1.9.3"\n',
        encoding="utf-8",
    )

    assert apply_release(tmp_path) is None

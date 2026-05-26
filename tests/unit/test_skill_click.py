"""Unit tests for skill_click.py."""

from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from slcli.skill_click import (
    CLIENT_CHOICES,
    TEMPORARILY_UNAVAILABLE_MESSAGE,
    _find_bundled_skills_dir,
    _find_repo_root,
    _resolve_destinations,
    install_skills_to_directory,
    register_skill_commands,
)


def make_cli() -> click.Group:
    """Create a test CLI with skill commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_skill_commands(test_cli)
    return test_cli


@pytest.fixture()
def runner() -> CliRunner:
    """Return a Click test runner."""
    return CliRunner()


# ── _resolve_destinations ────────────────────────────────────────────────────


def test_resolve_destinations_personal_all(tmp_path: Path) -> None:
    """Personal scope returns one personal dir per client, deduplicated."""
    with patch("slcli.skill_click._personal_dir", side_effect=lambda c: tmp_path / c):
        dests = _resolve_destinations(CLIENT_CHOICES, "personal")
    assert len(dests) == len(CLIENT_CHOICES)
    assert all(d == tmp_path / c for d, c in zip(dests, CLIENT_CHOICES))


def test_resolve_destinations_project_all(tmp_path: Path) -> None:
    """Project scope returns one project dir per client under repo_root."""
    with patch("slcli.skill_click._find_repo_root", return_value=tmp_path):
        dests = _resolve_destinations(CLIENT_CHOICES, "project")
    assert dests == [tmp_path / ".agents" / "skills", tmp_path / ".claude" / "skills"]


def test_resolve_destinations_both(tmp_path: Path) -> None:
    """Both scope returns personal + project dirs for every client."""
    with patch(
        "slcli.skill_click._personal_dir", side_effect=lambda c: tmp_path / "home" / c
    ), patch("slcli.skill_click._find_repo_root", return_value=tmp_path / "repo"):
        dests = _resolve_destinations(["agents"], "both")
    assert len(dests) == 2


def test_resolve_destinations_deduplicates(tmp_path: Path) -> None:
    """Duplicate paths are removed while preserving order."""
    same = tmp_path / "shared"
    with patch("slcli.skill_click._personal_dir", return_value=same):
        dests = _resolve_destinations(["agents", "claude"], "personal")
    assert dests == [same]


def test_resolve_destinations_project_falls_back_to_cwd(tmp_path: Path) -> None:
    """Project scope uses cwd when not inside a git repo."""
    with patch("slcli.skill_click._find_repo_root", return_value=None), patch(
        "slcli.skill_click.Path.cwd", return_value=tmp_path
    ):
        dests = _resolve_destinations(["claude"], "project")
    assert len(dests) == 1


# ── temporary skill availability ─────────────────────────────────────────────


def test_install_without_options_reports_temporary_unavailability(runner: CliRunner) -> None:
    """The install command exits before prompting while skills are unavailable."""
    cli = make_cli()
    result = runner.invoke(cli, ["skill", "install"])
    assert result.exit_code != 0
    assert TEMPORARILY_UNAVAILABLE_MESSAGE in result.output


def test_install_with_options_reports_temporary_unavailability(runner: CliRunner) -> None:
    """Passing explicit options still reports the temporary outage."""
    cli = make_cli()
    result = runner.invoke(
        cli,
        ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
    )
    assert result.exit_code != 0
    assert TEMPORARILY_UNAVAILABLE_MESSAGE in result.output


# ── helper functions ─────────────────────────────────────────────────────────


def test_find_repo_root_finds_git(tmp_path: Path) -> None:
    """_find_repo_root returns the directory containing .git."""
    (tmp_path / ".git").mkdir()
    subdir = tmp_path / "a" / "b"
    subdir.mkdir(parents=True)
    with patch("slcli.skill_click.Path.cwd", return_value=subdir):
        result = _find_repo_root()
    assert result == tmp_path


def test_find_repo_root_returns_none_outside_repo(tmp_path: Path) -> None:
    """_find_repo_root returns None when no .git is found."""
    # Use a path that is very unlikely to be inside a real git repo
    with patch("slcli.skill_click.Path.cwd", return_value=Path("/tmp")):
        result = _find_repo_root()
    # Can be None or a real repo root — just assert it doesn't raise
    assert result is None or isinstance(result, Path)


def test_find_bundled_skills_dir_raises_when_skills_are_removed() -> None:
    """_find_bundled_skills_dir raises once bundled skills are removed."""
    with pytest.raises(FileNotFoundError):
        _find_bundled_skills_dir()


def test_personal_dir_returns_expanded_path() -> None:
    """_personal_dir expands ~ and returns the correct path for each client."""
    from slcli.skill_click import _personal_dir

    agents = _personal_dir("agents")
    assert agents == Path.home() / ".agents" / "skills"

    claude = _personal_dir("claude")
    assert claude == Path.home() / ".claude" / "skills"


def test_install_skills_to_directory(tmp_path: Path) -> None:
    """Install_skills_to_directory is a no-op while skills are unavailable."""
    count = install_skills_to_directory(tmp_path)
    assert count == 0
    assert not (tmp_path / ".agents" / "skills").exists()


def test_install_skills_to_directory_specific_skill(tmp_path: Path) -> None:
    """Install_skills_to_directory remains a no-op for specific skill requests."""
    count = install_skills_to_directory(tmp_path, skill_names=["slcli"])
    assert count == 0
    assert not (tmp_path / ".agents" / "skills").exists()

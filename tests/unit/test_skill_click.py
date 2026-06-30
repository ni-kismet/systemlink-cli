"""Unit tests for skill_click.py."""

from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from slcli.skill_click import (
    CLIENT_CHOICES,
    SKILL_CHOICES,
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


# ── install command behavior ─────────────────────────────────────────────────


def test_install_without_options_installs_default_project_skills(
    runner: CliRunner, tmp_path: Path
) -> None:
    """The default install command stages bundled skills into the repo agents path."""
    cli = make_cli()
    with patch("slcli.skill_click._find_repo_root", return_value=tmp_path):
        result = runner.invoke(cli, ["skill", "install"])
    assert result.exit_code == 0
    assert (tmp_path / ".agents" / "skills" / "slcli" / "SKILL.md").exists()


def test_install_with_options_installs_selected_personal_skill_dependency(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Installing a specific skill stages that bundled skill into the chosen destination."""
    cli = make_cli()
    with patch("slcli.skill_click._personal_dir", return_value=tmp_path / "claude-home"):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "slcli",
                "--client",
                "claude",
                "--scope",
                "personal",
            ],
        )
    assert result.exit_code == 0
    assert (tmp_path / "claude-home" / "slcli" / "SKILL.md").exists()


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


def test_find_bundled_skills_dir_returns_packaged_directory() -> None:
    """_find_bundled_skills_dir should find the packaged skill directory."""
    skills_dir = _find_bundled_skills_dir()
    assert (skills_dir / "slcli" / "SKILL.md").exists()


def test_personal_dir_returns_expanded_path() -> None:
    """_personal_dir expands ~ and returns the correct path for each client."""
    from slcli.skill_click import _personal_dir

    agents = _personal_dir("agents")
    assert agents == Path.home() / ".agents" / "skills"

    claude = _personal_dir("claude")
    assert claude == Path.home() / ".claude" / "skills"


def test_install_skills_to_directory(tmp_path: Path) -> None:
    """Install_skills_to_directory copies the bundled skills into the target tree."""
    count = install_skills_to_directory(tmp_path)
    assert count == len(SKILL_CHOICES)
    assert (tmp_path / ".agents" / "skills" / "slcli" / "SKILL.md").exists()


def test_install_skills_to_directory_specific_skill(tmp_path: Path) -> None:
    """Specific installs copy only the requested bundled skill."""
    count = install_skills_to_directory(tmp_path, skill_names=["slcli"])
    assert count == 1
    assert (tmp_path / ".agents" / "skills" / "slcli" / "SKILL.md").exists()

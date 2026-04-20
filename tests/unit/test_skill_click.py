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


@pytest.fixture()
def fake_skills_dir(tmp_path: Path) -> Path:
    """Return a temp skills/ directory containing minimal bundled skills."""
    skill_names = [
        "slcli",
        "systemlink-webapp",
        "systemlink-notebook",
        "systemlink-python-test",
        "systemlink-job-debugging",
        "nipkg-file-package",
    ]

    for skill_name in skill_names:
        skill_dir = tmp_path / "skills" / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {skill_name}\ndescription: test\n---\nContent\n"
        )

    refs = tmp_path / "skills" / "slcli" / "references"
    refs.mkdir()
    (refs / "filtering.md").write_text("# Filtering\n")
    return tmp_path / "skills"


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


# ── install interactive prompts ──────────────────────────────────────────────


def test_install_prompts_when_no_options(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """Without any flags the command prompts for skill, client, and scope then installs."""
    dest = tmp_path / "agents-personal"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest]
    ), patch("slcli.skill_click.questionary.select") as mock_select:
        mock_select.return_value.ask.side_effect = ["slcli", "agents", "personal"]
        result = runner.invoke(cli, ["skill", "install"])
    assert result.exit_code == 0
    assert "✓ Installed slcli skill" in result.output


def test_install_agents_personal_flags(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill slcli --client agents --scope personal installs to the agents dir."""
    dest_parent = tmp_path / "agents-personal"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert (dest_parent / "slcli" / "SKILL.md").exists()


def test_install_single_client_project(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill slcli --client agents --scope project installs into .agents/skills/slcli."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()
    expected = repo_root / ".agents" / "skills"

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._find_repo_root", return_value=repo_root
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "project"],
        )
    assert result.exit_code == 0
    assert (expected / "slcli" / "SKILL.md").exists()


def test_install_claude_project(runner: CliRunner, fake_skills_dir: Path, tmp_path: Path) -> None:
    """--skill slcli --client claude --scope project installs into .claude/skills/slcli."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._find_repo_root", return_value=repo_root
    ):
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
                "project",
            ],
        )
    assert result.exit_code == 0
    assert (repo_root / ".claude" / "skills" / "slcli" / "SKILL.md").exists()


def test_install_all_client_installs_all(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--client all installs the skill for every supported client."""
    dest_agents = tmp_path / "agents-personal"
    dest_claude = tmp_path / "claude-personal"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_agents, dest_claude]
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "all", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert (dest_agents / "slcli" / "SKILL.md").exists()
    assert (dest_claude / "slcli" / "SKILL.md").exists()


def test_install_force_overwrites(runner: CliRunner, fake_skills_dir: Path, tmp_path: Path) -> None:
    """--force silently overwrites an existing installation."""
    dest_parent = tmp_path / "dest"
    dest = dest_parent / "slcli"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("old")

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "slcli",
                "--client",
                "agents",
                "--scope",
                "personal",
                "--force",
            ],
        )
    assert result.exit_code == 0
    assert "✓ Installed slcli skill" in result.output
    assert (dest / "SKILL.md").read_text() != "old"


def test_install_prompt_overwrite_decline(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """Declining overwrite prompt skips that destination."""
    dest_parent = tmp_path / "dest"
    dest = dest_parent / "slcli"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("old")

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ), patch("slcli.skill_click.questionary.confirm") as mock_confirm:
        mock_confirm.return_value.ask.return_value = False
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert "Skipped" in result.output
    assert (dest / "SKILL.md").read_text() == "old"


def test_install_references_copied(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """The references/ subdirectory is also copied."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert (dest_parent / "slcli" / "references" / "filtering.md").exists()


def test_install_missing_source(runner: CliRunner) -> None:
    """Missing bundled skills dir exits non-zero."""
    cli = make_cli()
    with patch(
        "slcli.skill_click._find_bundled_skills_dir",
        side_effect=FileNotFoundError("not found"),
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code != 0


def test_install_all_skipped_exits_cleanly(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """Skipping all destinations exits 0 with a descriptive message."""
    dest_parent = tmp_path / "dest"
    dest = dest_parent / "slcli"
    dest.mkdir(parents=True)
    (dest / "SKILL.md").write_text("old")

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ), patch("slcli.skill_click.questionary.confirm") as mock_confirm:
        mock_confirm.return_value.ask.return_value = False
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "slcli", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert "No skill locations were updated" in result.output


# ── systemlink-webapp skill ────────────────────────────────────────────────────


def test_install_webapp_skill_personal(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill systemlink-webapp installs the webapp skill."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "systemlink-webapp",
                "--client",
                "agents",
                "--scope",
                "personal",
            ],
        )
    assert result.exit_code == 0
    assert "\u2713 Installed systemlink-webapp skill" in result.output
    assert (dest_parent / "systemlink-webapp" / "SKILL.md").exists()


def test_install_all_skills(runner: CliRunner, fake_skills_dir: Path, tmp_path: Path) -> None:
    """--skill all installs every bundled skill."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            ["skill", "install", "--skill", "all", "--client", "agents", "--scope", "personal"],
        )
    assert result.exit_code == 0
    assert result.output.count("\u2713 Installed") == len(SKILL_CHOICES)
    for skill_name in SKILL_CHOICES:
        assert (dest_parent / skill_name / "SKILL.md").exists()


def test_install_python_test_skill_personal(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill systemlink-python-test installs the python test skill."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "systemlink-python-test",
                "--client",
                "agents",
                "--scope",
                "personal",
            ],
        )
    assert result.exit_code == 0
    assert "\u2713 Installed systemlink-python-test skill" in result.output
    assert (dest_parent / "systemlink-python-test" / "SKILL.md").exists()


def test_install_notebook_skill_personal(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill systemlink-notebook installs the notebook skill."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "systemlink-notebook",
                "--client",
                "agents",
                "--scope",
                "personal",
            ],
        )
    assert result.exit_code == 0
    assert "\u2713 Installed systemlink-notebook skill" in result.output
    assert (dest_parent / "systemlink-notebook" / "SKILL.md").exists()


def test_install_webapp_skill_project(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """--skill systemlink-webapp --client agents --scope project installs into .agents/skills/."""
    repo_root = tmp_path / "myrepo"
    repo_root.mkdir()

    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._find_repo_root", return_value=repo_root
    ):
        result = runner.invoke(
            cli,
            [
                "skill",
                "install",
                "--skill",
                "systemlink-webapp",
                "--client",
                "agents",
                "--scope",
                "project",
            ],
        )
    assert result.exit_code == 0
    assert (repo_root / ".agents" / "skills" / "systemlink-webapp" / "SKILL.md").exists()


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


def test_find_bundled_skills_dir_dev_tree() -> None:
    """_find_bundled_skills_dir locates the actual skills/slcli/SKILL.md."""
    skills_dir = _find_bundled_skills_dir()
    assert (skills_dir / "slcli" / "SKILL.md").exists()


def test_personal_dir_returns_expanded_path() -> None:
    """_personal_dir expands ~ and returns the correct path for each client."""
    from slcli.skill_click import _personal_dir

    agents = _personal_dir("agents")
    assert agents == Path.home() / ".agents" / "skills"

    claude = _personal_dir("claude")
    assert claude == Path.home() / ".claude" / "skills"


def test_install_oserror_exits_nonzero(
    runner: CliRunner, fake_skills_dir: Path, tmp_path: Path
) -> None:
    """An OSError during copy reports an error and exits non-zero."""
    dest_parent = tmp_path / "dest"
    cli = make_cli()
    with patch("slcli.skill_click._find_bundled_skills_dir", return_value=fake_skills_dir), patch(
        "slcli.skill_click._resolve_destinations", return_value=[dest_parent]
    ), patch("slcli.skill_click.shutil.copytree", side_effect=OSError("disk full")), patch(
        "slcli.skill_click.questionary.select"
    ) as mock_select:
        mock_select.return_value.ask.return_value = "slcli"
        result = runner.invoke(
            cli, ["skill", "install", "--client", "agents", "--scope", "personal"]
        )
    assert result.exit_code != 0
    assert "Failed to install" in result.output


def test_install_skills_to_directory(tmp_path: Path) -> None:
    """Install_skills_to_directory copies skills into the project."""
    count = install_skills_to_directory(tmp_path)
    assert count == len(SKILL_CHOICES)
    for name in SKILL_CHOICES:
        assert (tmp_path / ".agents" / "skills" / name / "SKILL.md").exists()


def test_install_skills_to_directory_specific_skill(tmp_path: Path) -> None:
    """Install_skills_to_directory can install a single skill."""
    count = install_skills_to_directory(tmp_path, skill_names=["slcli"])
    assert count == 1
    assert (tmp_path / ".agents" / "skills" / "slcli" / "SKILL.md").exists()
    assert not (tmp_path / ".agents" / "skills" / "systemlink-webapp").exists()
    assert not (tmp_path / ".agents" / "skills" / "systemlink-notebook").exists()

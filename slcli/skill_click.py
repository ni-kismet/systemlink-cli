"""Agent Skills install command for slcli."""

import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from .utils import ExitCodes

SKILL_NAME = "slcli"

# Mapping of client name → (personal skills dir, project subdir relative to repo root)
# personal dir uses Path.home() so it's always resolved at call time via _personal_dir().
_CLIENT_TABLE: Dict[str, Tuple[str, str]] = {
    "copilot": ("~/.copilot/skills", ".github/skills"),
    "claude": ("~/.claude/skills", ".claude/skills"),
    "codex": ("~/.agents/skills", ".agents/skills"),
}

CLIENT_CHOICES = list(_CLIENT_TABLE.keys())


def _personal_dir(client: str) -> Path:
    """Return the resolved personal skills directory for a client."""
    return Path(_CLIENT_TABLE[client][0]).expanduser()


def _project_subdir(client: str) -> str:
    """Return the project-relative skills subdirectory for a client."""
    return _CLIENT_TABLE[client][1]


def _find_repo_root() -> Optional[Path]:
    """Walk up from cwd looking for a .git directory.

    Returns:
        The repository root Path, or None if not inside a git repository.
    """
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        if (directory / ".git").exists():
            return directory
    return None


def _find_bundled_skills_dir() -> Path:
    """Locate the bundled skills/ directory.

    Handles PyInstaller (onefile + onedir) and development/source layouts.

    Returns:
        Path to the bundled skills/ directory.

    Raises:
        FileNotFoundError: If the skills directory cannot be found.
    """
    candidates: List[Path] = []

    # PyInstaller onefile mode
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "skills")

    # PyInstaller onedir / frozen executable
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "skills")

    # Development/Poetry-install: skills/ sits next to the slcli package
    candidates.append(Path(__file__).resolve().parent.parent / "skills")

    for candidate in candidates:
        if candidate.exists() and (candidate / SKILL_NAME / "SKILL.md").exists():
            return candidate

    raise FileNotFoundError(
        "Bundled skills directory not found. "
        "Try reinstalling slcli: pip install --force-reinstall slcli"
    )


def _resolve_destinations(clients: List[str], scope: str) -> List[Path]:
    """Build the list of destination skill parent directories.

    Args:
        clients: List of client names (subset of CLIENT_CHOICES).
        scope: One of 'personal', 'project', or 'both'.

    Returns:
        Deduplicated list of directories into which slcli/ should be copied.
    """
    dirs: List[Path] = []

    repo_root: Optional[Path] = None
    if scope in ("project", "both"):
        repo_root = _find_repo_root() or Path.cwd()

    for client in clients:
        if scope in ("personal", "both"):
            dirs.append(_personal_dir(client))
        if scope in ("project", "both") and repo_root is not None:
            dirs.append(repo_root / _project_subdir(client))

    # Preserve order, deduplicate (e.g. same path selected via two clients)
    seen: List[Path] = []
    for d in dirs:
        if d not in seen:
            seen.append(d)
    return seen


def register_skill_commands(cli: Any) -> None:
    """Register the skill command group with the CLI.

    Args:
        cli: The Click CLI group to register commands with.
    """

    @cli.group()
    def skill() -> None:
        """Manage AI agent skills for Copilot, Claude, and Codex."""

    @skill.command(name="install")
    @click.option(
        "--client",
        "-c",
        type=click.Choice(CLIENT_CHOICES + ["all"], case_sensitive=False),
        default=None,
        help="AI client to install for (copilot, claude, codex, or all).",
    )
    @click.option(
        "--scope",
        "-s",
        type=click.Choice(["personal", "project", "both"], case_sensitive=False),
        default=None,
        help="personal (~/ home dirs), project (current repo), or both.",
    )
    @click.option(
        "--force",
        "-F",
        is_flag=True,
        default=False,
        help="Overwrite existing skill installation without prompting.",
    )
    def install_skill(client: Optional[str], scope: Optional[str], force: bool) -> None:
        """Install the slcli agent skill for AI coding assistants.

        Copies the bundled slcli skill into the skills directory of one or more
        AI clients. Supported clients and their skill locations:

        \b
          copilot  personal: ~/.copilot/skills/       project: .github/skills/
          claude   personal: ~/.claude/skills/         project: .claude/skills/
          codex    personal: ~/.agents/skills/         project: .agents/skills/

        When --client and --scope are omitted you will be prompted interactively.
        """
        # ── interactive prompts when options not supplied ─────────────────────
        if client is None:
            client = click.prompt(
                "Install for which AI client",
                type=click.Choice(CLIENT_CHOICES + ["all"], case_sensitive=False),
                default="all",
            )

        if scope is None:
            scope = click.prompt(
                "Install scope",
                type=click.Choice(["personal", "project", "both"], case_sensitive=False),
                default="personal",
            )

        # ── resolve client list ───────────────────────────────────────────────
        clients: List[str] = CLIENT_CHOICES if client == "all" else [client]

        # ── locate source ─────────────────────────────────────────────────────
        try:
            skills_dir = _find_bundled_skills_dir()
        except FileNotFoundError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

        source = skills_dir / SKILL_NAME
        destinations = _resolve_destinations(clients, scope)

        installed_any = False
        errors = 0

        for dest_parent in destinations:
            dest = dest_parent / SKILL_NAME

            if dest.exists() and not force:
                confirm = click.confirm(
                    f"Skill already installed at {dest}. Overwrite?", default=False
                )
                if not confirm:
                    click.echo(f"  Skipped {dest}")
                    continue

            try:
                dest_parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                click.echo(f"✓ Installed slcli skill → {dest}")
                installed_any = True
            except OSError as exc:
                click.echo(f"✗ Failed to install to {dest}: {exc}", err=True)
                errors += 1

        if not installed_any and errors == 0:
            click.echo("No skill locations were updated.")

        if errors:
            sys.exit(ExitCodes.GENERAL_ERROR)

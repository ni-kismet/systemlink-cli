"""Agent Skills install command for slcli."""

import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click
import questionary

from .utils import ExitCodes

SKILL_NAME = "slcli"
SKILL_CHOICES = ["slcli", "systemlink-webapp"]

# Mapping of client name -> (personal skills dir, project subdir relative to repo root)
# personal dir uses Path.home() so it's always resolved at call time via _personal_dir().
_CLIENT_TABLE: Dict[str, Tuple[str, str]] = {
    "agents": ("~/.agents/skills", ".agents/skills"),
    "claude": ("~/.claude/skills", ".claude/skills"),
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

    # pip install / development: skills/ bundled inside the slcli package
    candidates.append(Path(__file__).resolve().parent / "skills")

    for candidate in candidates:
        if candidate.exists() and any(
            (candidate / name / "SKILL.md").exists() for name in SKILL_CHOICES
        ):
            return candidate

    raise FileNotFoundError(
        "Bundled skills directory not found. "
        "Try reinstalling slcli: pip install --force-reinstall slcli"
    )


# Universal project-scoped skills directory (client-agnostic)
PROJECT_SKILLS_SUBDIR = ".agents/skills"


def install_skills_to_directory(
    directory: Path,
    skill_names: Optional[List[str]] = None,
    subdir: str = PROJECT_SKILLS_SUBDIR,
) -> int:
    """Install bundled skills into a project directory.

    Copies skill folders into a skills subdirectory within *directory*.
    The default location (``.agents/skills/``) is the universal convention
    recognized by multiple AI clients.

    Args:
        directory: Project root to install into.
        skill_names: Skills to install.  Defaults to all available skills.
        subdir: Relative subdirectory for skills.  Defaults to ``.agents/skills``.

    Returns:
        Number of skills successfully installed.
    """
    if skill_names is None:
        skill_names = list(SKILL_CHOICES)

    try:
        skills_dir = _find_bundled_skills_dir()
    except FileNotFoundError:
        return 0

    dest_parent = directory / subdir
    installed = 0

    for name in skill_names:
        source = skills_dir / name
        if not source.exists():
            continue
        dest = dest_parent / name
        dest_parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        installed += 1

    return installed


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
        """Manage AI agent skills for most agents and Claude."""

    @skill.command(name="install")
    @click.option(
        "--skill",
        "-k",
        type=click.Choice(SKILL_CHOICES + ["all"], case_sensitive=False),
        default=None,
        help="Skill to install (slcli, systemlink-webapp, or all).",
    )
    @click.option(
        "--client",
        "-c",
        type=click.Choice(CLIENT_CHOICES, case_sensitive=False),
        default=None,
        help="AI client to install for (agents [most agents] or claude).",
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
    def install_skill(
        skill: Optional[str], client: Optional[str], scope: Optional[str], force: bool
    ) -> None:
        """Install agent skills for AI coding assistants.

        Copies bundled skills into the skills directory of one or more AI clients.
        Available skills: slcli, systemlink-webapp.
        Supported clients and their skill locations:

                    \b
                agents   personal: ~/.agents/skills/         project: .agents/skills/
                     (most agents)
                claude   personal: ~/.claude/skills/         project: .claude/skills/

        When options are omitted you will be prompted interactively.
        """
        # ── interactive prompts when options not supplied ─────────────────────
        if skill is None:
            skill = questionary.select(
                "Which skill to install?",
                choices=SKILL_CHOICES + ["all"],
                default="all",
            ).ask()
            if skill is None:
                raise click.Abort()

        if client is None:
            client = questionary.select(
                "Install for which AI client?",
                choices=[
                    questionary.Choice("most agents", value="agents"),
                    questionary.Choice("claude", value="claude"),
                ],
                default="agents",
            ).ask()
            if client is None:
                raise click.Abort()

        if scope is None:
            scope = questionary.select(
                "Install scope?",
                choices=["personal", "project", "both"],
                default="personal",
            ).ask()
            if scope is None:
                raise click.Abort()

        # ── resolve skill and client lists ────────────────────────────────────
        skill_names: List[str] = SKILL_CHOICES if skill == "all" else [skill]
        clients: List[str] = [client]

        # ── locate source ─────────────────────────────────────────────────────
        try:
            skills_dir = _find_bundled_skills_dir()
        except FileNotFoundError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

        destinations = _resolve_destinations(clients, scope)

        installed_any = False
        errors = 0

        for skill_name in skill_names:
            source = skills_dir / skill_name
            if not source.exists():
                click.echo(
                    f"✗ Skill '{skill_name}' not found in bundled skills directory.", err=True
                )
                errors += 1
                continue

            for dest_parent in destinations:
                dest = dest_parent / skill_name

                if dest.exists() and not force:
                    confirm = questionary.confirm(
                        f"Skill already installed at {dest}. Overwrite?",
                        default=False,
                    ).ask()
                    if not confirm:
                        click.echo(f"  Skipped {dest}")
                        continue

                try:
                    dest_parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(source, dest)
                    click.echo(f"✓ Installed {skill_name} skill → {dest}")
                    installed_any = True
                except OSError as exc:
                    click.echo(f"✗ Failed to install to {dest}: {exc}", err=True)
                    errors += 1

        if not installed_any and errors == 0:
            click.echo("No skill locations were updated.")

        if errors:
            sys.exit(ExitCodes.GENERAL_ERROR)

"""Agent Skills install command for slcli."""

import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

from .utils import ExitCodes, format_success

SKILL_NAME = "slcli"
_FALLBACK_SKILL_CHOICES = [
    "nipkg-file-package",
    "slcli",
    "systemlink-job-debugging",
    "systemlink-notebook",
    "systemlink-python-test",
    "systemlink-webapp",
]

# Mapping of client name -> (personal skills dir, project subdir relative to repo root)
# personal dir uses Path.home() so it's always resolved at call time via _personal_dir().
_CLIENT_TABLE: Dict[str, Tuple[str, str]] = {
    "agents": ("~/.agents/skills", ".agents/skills"),
    "claude": ("~/.claude/skills", ".claude/skills"),
}

CLIENT_CHOICES = list(_CLIENT_TABLE.keys())
_SKILL_DEPENDENCIES: Dict[str, List[str]] = {
    "nipkg-file-package": ["slcli"],
    "systemlink-job-debugging": ["slcli"],
    "systemlink-notebook": ["slcli"],
    "systemlink-python-test": ["slcli"],
    "systemlink-webapp": ["slcli"],
}


def _skills_dir_candidates() -> List[Path]:
    """Return candidate bundled skills directories for source and frozen layouts."""
    candidates: List[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "skills")

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "skills")

    candidates.append(Path(__file__).resolve().parent / "skills")
    return candidates


def _skill_names_in_directory(directory: Path) -> List[str]:
    """Return sorted bundled skill names for a skills directory."""
    if not directory.exists():
        return []

    return sorted(
        child.name
        for child in directory.iterdir()
        if child.is_dir() and (child / "SKILL.md").exists()
    )


def _discover_skill_choices() -> List[str]:
    """Discover bundled skills from the current installation layout."""
    for candidate in _skills_dir_candidates():
        names = _skill_names_in_directory(candidate)
        if names:
            return names
    return list(_FALLBACK_SKILL_CHOICES)


SKILL_CHOICES = _discover_skill_choices()


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
    for candidate in _skills_dir_candidates():
        if _skill_names_in_directory(candidate):
            return candidate

    raise FileNotFoundError(
        "Bundled skills directory not found. "
        "Try reinstalling slcli: pip install --force-reinstall slcli"
    )


# Universal project-scoped skills directory (client-agnostic)
PROJECT_SKILLS_SUBDIR = ".agents/skills"


def _expand_skill_selection(skill_names: Optional[List[str]] = None) -> List[str]:
    """Expand requested skill names with any bundled dependencies."""
    requested = list(dict.fromkeys(skill_names or SKILL_CHOICES))
    invalid = [name for name in requested if name not in SKILL_CHOICES]
    if invalid:
        invalid_display = ", ".join(sorted(invalid))
        raise ValueError(f"Unknown bundled skill(s): {invalid_display}")

    expanded: List[str] = []
    for skill_name in requested:
        for dependency in _SKILL_DEPENDENCIES.get(skill_name, []):
            if dependency not in expanded:
                expanded.append(dependency)
        if skill_name not in expanded:
            expanded.append(skill_name)
    return expanded


def install_skills_to_directory(
    directory: Path,
    skill_names: Optional[List[str]] = None,
    subdir: str = PROJECT_SKILLS_SUBDIR,
    force: bool = False,
) -> int:
    """Install bundled skills into the requested directory and return the count."""
    bundled_skills_dir = _find_bundled_skills_dir()
    selected_skills = _expand_skill_selection(skill_names)
    destination_root = directory / subdir if subdir else directory
    destination_root.mkdir(parents=True, exist_ok=True)

    for skill_name in selected_skills:
        source_dir = bundled_skills_dir / skill_name
        if not source_dir.exists():
            raise FileNotFoundError(
                f"Bundled skill '{skill_name}' not found in {bundled_skills_dir}"
            )

        destination_dir = destination_root / skill_name
        if destination_dir.exists():
            if not force:
                raise FileExistsError(
                    f"{destination_dir} already exists. Use --force to overwrite it."
                )
            if destination_dir.is_dir():
                shutil.rmtree(destination_dir)
            else:
                destination_dir.unlink()

        shutil.copytree(source_dir, destination_dir)

    return len(selected_skills)


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
        """Install bundled AI assistant skills."""

    @skill.command(name="install")
    @click.option(
        "--skill",
        "-k",
        type=click.Choice(SKILL_CHOICES + ["all"], case_sensitive=False),
        default=None,
        help=f"Skill to install ({', '.join(SKILL_CHOICES)}, or all).",
    )
    @click.option(
        "--client",
        "-c",
        type=click.Choice(CLIENT_CHOICES + ["all"], case_sensitive=False),
        default=None,
        help="AI client to install for (agents [most agents], claude, or all).",
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
        """Install bundled skills for supported AI clients."""
        requested_skills: Optional[List[str]]
        if skill in (None, "all"):
            requested_skills = None
        else:
            assert skill is not None
            requested_skills = [skill.lower()]
        selected_skill_names = _expand_skill_selection(requested_skills)
        selected_clients = CLIENT_CHOICES if client == "all" else [client or "agents"]
        selected_scope = scope or "project"
        destinations = _resolve_destinations(selected_clients, selected_scope)

        try:
            installed_count = 0
            for destination in destinations:
                installed_count += install_skills_to_directory(
                    destination,
                    skill_names=selected_skill_names,
                    subdir="",
                    force=force,
                )
        except ValueError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except FileExistsError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except FileNotFoundError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

        format_success(
            "Installed bundled AI skills",
            {
                "Skills": ", ".join(selected_skill_names),
                "Destinations": ", ".join(str(path) for path in destinations),
                "Installed": str(installed_count),
            },
        )

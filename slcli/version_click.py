"""Version checking and update guidance for slcli."""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Optional

import click
import requests
from packaging.version import InvalidVersion, Version

from ._version import __version__
from .rich_output import print_json
from .utils import ExitCodes

PYPI_URL = "https://pypi.org/pypi/systemlink-cli/json"
RELEASES_URL = "https://github.com/ni-kismet/systemlink-cli/releases/latest"


class InstallMethod(str, Enum):
    """Supported slcli installation methods."""

    HOMEBREW = "homebrew"
    SCOOP = "scoop"
    PIPX = "pipx"
    UV = "uv"
    PIP = "pip"
    STANDALONE = "standalone"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class VersionCheckResult:
    """Result returned by a version check.

    Attributes:
        current_version: Installed slcli version.
        latest_version: Latest version published to PyPI.
        status: One of ``outdated``, ``current``, or ``ahead``.
        install_method: Detected installation method.
        update_command: Suggested update command, when available.
    """

    current_version: str
    latest_version: str
    status: str
    install_method: str
    update_command: Optional[str]


def fetch_latest_version() -> str:
    """Return the latest published systemlink-cli version from PyPI."""
    response = requests.get(PYPI_URL, timeout=5)
    response.raise_for_status()
    payload: Any = response.json()
    try:
        version = payload["info"]["version"]
    except (KeyError, TypeError) as exc:
        raise ValueError("PyPI returned an unexpected response") from exc
    if not isinstance(version, str) or not version:
        raise ValueError("PyPI returned an invalid version")
    try:
        Version(version)
    except InvalidVersion as exc:
        raise ValueError(f"PyPI returned an invalid version: {version}") from exc
    return version


def _path_contains(path: Path, *parts: str) -> bool:
    """Return whether a path contains the given consecutive components."""
    lowered_parts = tuple(part.lower() for part in path.parts)
    expected = tuple(part.lower() for part in parts)
    width = len(expected)
    return any(lowered_parts[index : index + width] == expected for index in range(len(path.parts)))


def detect_install_method() -> InstallMethod:
    """Detect how the running slcli installation is managed."""
    executable = Path(sys.executable).resolve()

    if getattr(sys, "frozen", False):
        if _path_contains(executable, "cellar", "slcli"):
            return InstallMethod.HOMEBREW
        if _path_contains(executable, "scoop", "apps", "slcli"):
            return InstallMethod.SCOOP
        return InstallMethod.STANDALONE

    if _path_contains(executable, "pipx", "venvs", "systemlink-cli"):
        return InstallMethod.PIPX
    if _path_contains(executable, "uv", "tools", "systemlink-cli"):
        return InstallMethod.UV

    project_root = Path(__file__).resolve().parent.parent
    if (project_root / "pyproject.toml").is_file() and (project_root / ".git").exists():
        return InstallMethod.DEVELOPMENT

    try:
        distribution("systemlink-cli")
    except PackageNotFoundError:
        return InstallMethod.UNKNOWN
    return InstallMethod.PIP


def get_update_command(install_method: InstallMethod) -> Optional[str]:
    """Return the update command for an installation method, when available."""
    commands = {
        InstallMethod.HOMEBREW: "brew upgrade slcli",
        InstallMethod.SCOOP: "scoop update slcli",
        InstallMethod.PIPX: "pipx upgrade systemlink-cli",
        InstallMethod.UV: "uv tool upgrade systemlink-cli",
        InstallMethod.PIP: f'"{sys.executable}" -m pip install --upgrade systemlink-cli',
        InstallMethod.DEVELOPMENT: "git pull && poetry install",
    }
    return commands.get(install_method)


def check_version(current_version: str = __version__) -> VersionCheckResult:
    """Compare the current slcli version with the latest published version."""
    latest_version = fetch_latest_version()
    current = Version(current_version)
    latest = Version(latest_version)
    status = "outdated" if current < latest else "current" if current == latest else "ahead"
    install_method = detect_install_method()
    return VersionCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        status=status,
        install_method=install_method.value,
        update_command=get_update_command(install_method),
    )


def _render_version_check(result: VersionCheckResult) -> None:
    """Render a human-readable version check result."""
    click.echo(f"Current version: {result.current_version}")
    click.echo(f"Latest version:  {result.latest_version}")
    click.echo(f"Installed with:  {result.install_method}")
    click.echo()

    if result.status == "current":
        click.echo("✓ slcli is up to date")
    elif result.status == "ahead":
        click.echo("Current version is newer than the latest published version")
    elif result.update_command:
        click.echo("A newer version is available:")
        click.echo(f"  {result.update_command}")
    else:
        click.echo("A newer version is available.")
        click.echo(f"Download it from {RELEASES_URL}")


def register_version_commands(cli: Any) -> None:
    """Register version commands with the CLI."""

    @cli.group(invoke_without_command=True)
    @click.pass_context
    def version(ctx: click.Context) -> None:
        """Show the installed version and check for updates."""
        if ctx.invoked_subcommand is None:
            click.echo(f"slcli version {__version__}")

    @version.command(name="check")
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["text", "json"]),
        default="text",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--fail-if-outdated",
        is_flag=True,
        help="Exit with code 1 when a newer version is available",
    )
    def check(format_output: str, fail_if_outdated: bool) -> None:
        """Check whether this is the latest slcli version."""
        try:
            result = check_version()
        except InvalidVersion as exc:
            click.echo(f"✗ Invalid version: {exc}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except (requests.RequestException, ValueError) as exc:
            click.echo(f"✗ Unable to retrieve the latest slcli version: {exc}", err=True)
            sys.exit(ExitCodes.NETWORK_ERROR)

        if format_output == "json":
            print_json(asdict(result))
        else:
            _render_version_check(result)

        if fail_if_outdated and result.status == "outdated":
            sys.exit(ExitCodes.GENERAL_ERROR)

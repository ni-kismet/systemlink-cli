"""Host package-manager backends for managed-client software jobs in real mode."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Protocol, Sequence

from .models import ManagedClientError

COMMAND_TIMEOUT_SECONDS = 1800
OS_RELEASE_PATH = Path("/etc/os-release")
APT_SOURCES_LIST = Path("/etc/apt/sources.list")
APT_SOURCES_DIRECTORY = Path("/etc/apt/sources.list.d")
REBOOT_MARKERS: tuple[Path, ...] = (Path("/run/reboot-required"), Path("/var/run/reboot-required"))
DEBIAN_FAMILY = "debian"
PACKAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+.\-]*(:[A-Za-z0-9\-]+)?$")
VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+~:\-]*$")
DPKG_FORMAT = (
    r"${Package}\t${Version}\t${Architecture}\t${db:Status-Abbrev}"
    r"\t${binary:Summary}\t${Section}\t${Maintainer}\n"
)
DPKG_FIELD_COUNT = 7
INFO_ATTRIBUTES: tuple[str, ...] = ("version", "arch", "description", "group", "packager")
INSTALLED_STATUS_PREFIX = "ii"
SIMULATED_INSTALL_PATTERN = re.compile(r"^Inst (\S+) (?:\[([^\]]+)\] )?\(([^\s)]+)")
SIMULATED_REMOVE_PATTERN = re.compile(r"^Remv (\S+) \[([^\]]+)\]")
ONE_LINE_SOURCE_PATTERN = re.compile(r"^(deb|deb-src)\s+(?:\[([^\]]*)\]\s*)?(\S+)\s+\S+")

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


class PackageBackendError(ManagedClientError):
    """Raised when a host package operation cannot be completed."""

    def __init__(self, code: str, message: str) -> None:
        """Store a stable error code alongside a human-readable message."""
        super().__init__(message)
        self.code = code
        self.message = message


class PackageBackend(Protocol):
    """Operations a host package manager must provide for managed-client jobs."""

    def list_installed(self) -> Dict[str, Dict[str, str]]:
        """Return installed packages keyed by name with info attributes."""

    def install(
        self, packages: Mapping[str, str], dry_run: bool, install_recommends: bool
    ) -> Dict[str, Dict[str, str]]:
        """Install packages, or simulate it, and return Salt-style old/new changes."""

    def remove(self, names: Sequence[str], dry_run: bool) -> Dict[str, Dict[str, str]]:
        """Remove packages, or simulate it, and return Salt-style old/new changes."""

    def list_repositories(self) -> Dict[str, Dict[str, Any]]:
        """Return configured software sources keyed by name."""

    def reboot_required(self) -> bool:
        """Return whether the host reports that a reboot is pending."""


def validate_package_name(name: str) -> str:
    """Return a package name after rejecting anything that could alter apt arguments."""
    if not PACKAGE_NAME_PATTERN.fullmatch(name):
        raise PackageBackendError("invalid-package-name", f"Invalid package name: {name!r}.")
    return name


def validate_version(version: str) -> str:
    """Return a package version after rejecting anything that could alter apt arguments."""
    if not VERSION_PATTERN.fullmatch(version):
        raise PackageBackendError(
            "invalid-package-version", f"Invalid package version: {version!r}."
        )
    return version


def _default_privilege_prefix() -> list[str]:
    """Return the prefix needed to run package changes as root."""
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() == 0:
        return []
    return ["sudo", "-n"]


def _run_command(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command without a shell and map launch failures to backend errors."""
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as error:
        raise PackageBackendError(
            "package-manager-missing", f"{argv[0]} is not installed."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise PackageBackendError(
            "package-command-timeout",
            f"{argv[0]} did not finish within {COMMAND_TIMEOUT_SECONDS} seconds.",
        ) from error
    except OSError as error:
        raise PackageBackendError(
            "package-command-failed", f"{argv[0]} could not be started."
        ) from error


def _raise_for_failure(result: subprocess.CompletedProcess[str], tool: str) -> None:
    """Raise a backend error when a package command exits unsuccessfully."""
    if result.returncode == 0:
        return
    output = (result.stderr or result.stdout or "").strip().splitlines()
    detail = output[-1] if output else "no output"
    raise PackageBackendError(
        "package-command-failed", f"{tool} exited with status {result.returncode}: {detail}"
    )


def _parse_dpkg_inventory(output: str) -> Dict[str, Dict[str, str]]:
    """Parse dpkg-query output into installed packages only.

    Each record carries the Salt ``pkg.info_installed`` attributes: the version,
    arch, one-line summary (``description``), section (``group``), and maintainer
    (``packager``).
    """
    installed: Dict[str, Dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != DPKG_FIELD_COUNT:
            continue
        name, version, arch, status, summary, section, maintainer = parts
        if status.strip().startswith(INSTALLED_STATUS_PREFIX):
            installed[name] = {
                "version": version,
                "arch": arch,
                "description": summary,
                "group": section,
                "packager": maintainer,
            }
    return installed


def _inventory_changes(
    before: Mapping[str, Mapping[str, str]], after: Mapping[str, Mapping[str, str]]
) -> Dict[str, Dict[str, str]]:
    """Return Salt-style old/new versions for every package whose version differs."""
    changes: Dict[str, Dict[str, str]] = {}
    for name in sorted(before.keys() | after.keys()):
        old = before.get(name, {}).get("version", "")
        new = after.get(name, {}).get("version", "")
        if old != new:
            changes[name] = {"old": old, "new": new}
    return changes


def _simulated_changes(output: str) -> Dict[str, Dict[str, str]]:
    """Parse apt-get simulation output into Salt-style old/new versions."""
    changes: Dict[str, Dict[str, str]] = {}
    for line in output.splitlines():
        install = SIMULATED_INSTALL_PATTERN.match(line)
        if install:
            name = install.group(1).split(":")[0]
            changes[name] = {"old": install.group(2) or "", "new": install.group(3)}
            continue
        removal = SIMULATED_REMOVE_PATTERN.match(line)
        if removal:
            name = removal.group(1).split(":")[0]
            changes[name] = {"old": removal.group(2), "new": ""}
    return dict(sorted(changes.items()))


def _parse_one_line_sources(text: str) -> list[Dict[str, Any]]:
    """Parse classic one-line apt sources, including commented-out (disabled) entries."""
    entries: list[Dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        enabled = True
        if line.startswith("#"):
            line = line.lstrip("#").strip()
            enabled = False
        match = ONE_LINE_SOURCE_PATTERN.match(line)
        if not match:
            continue
        options = (match.group(2) or "").split()
        entries.append(
            {"uri": match.group(3), "enabled": enabled, "trusted": "trusted=yes" in options}
        )
    return entries


def _parse_deb822_sources(text: str) -> list[Dict[str, Any]]:
    """Parse deb822 (.sources) stanzas, using the first URI in each stanza."""
    entries: list[Dict[str, Any]] = []
    for stanza in re.split(r"\n\s*\n", text):
        fields: Dict[str, str] = {}
        for line in stanza.splitlines():
            if ":" in line and not line.startswith((" ", "#")):
                key, _, value = line.partition(":")
                fields[key.strip().lower()] = value.strip()
        uris = fields.get("uris", "").split()
        if not uris:
            continue
        entries.append(
            {
                "uri": uris[0],
                "enabled": fields.get("enabled", "yes").lower() != "no",
                "trusted": fields.get("trusted", "no").lower() == "yes",
            }
        )
    return entries


def _os_family_ids(os_release: Path) -> set[str]:
    """Return the ID and ID_LIKE values from os-release, lowercased."""
    try:
        text = os_release.read_text(encoding="utf-8")
    except OSError:
        return set()
    values: Dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip("\"'")
    ids = {values.get("ID", "").lower(), *values.get("ID_LIKE", "").lower().split()}
    return {identifier for identifier in ids if identifier}


class DpkgPackageBackend:
    """Package operations for the dpkg and apt family, such as Debian and Ubuntu."""

    def __init__(
        self,
        runner: CommandRunner = _run_command,
        privilege_prefix: Sequence[str] | None = None,
        sources_list: Path = APT_SOURCES_LIST,
        sources_directory: Path = APT_SOURCES_DIRECTORY,
        reboot_markers: Sequence[Path] = REBOOT_MARKERS,
    ) -> None:
        """Create a backend; tests can inject the command runner and host paths."""
        self._runner = runner
        self._privilege_prefix = list(
            _default_privilege_prefix() if privilege_prefix is None else privilege_prefix
        )
        self._sources_list = sources_list
        self._sources_directory = sources_directory
        self._reboot_markers = tuple(reboot_markers)

    def list_installed(self) -> Dict[str, Dict[str, str]]:
        """Return installed packages reported by dpkg-query."""
        result = self._runner(["dpkg-query", "-W", f"-f={DPKG_FORMAT}"])
        # dpkg-query exits with 1 when no packages match, which means an empty inventory.
        if result.returncode not in (0, 1):
            _raise_for_failure(result, "dpkg-query")
        return _parse_dpkg_inventory(result.stdout)

    def install(
        self, packages: Mapping[str, str], dry_run: bool, install_recommends: bool
    ) -> Dict[str, Dict[str, str]]:
        """Install pinned or latest packages with apt-get, or simulate with apt-get -s."""
        targets = []
        for name, version in packages.items():
            validate_package_name(name)
            if version == "latest":
                targets.append(name)
            else:
                targets.append(f"{name}={validate_version(version)}")
        recommends = "--install-recommends" if install_recommends else "--no-install-recommends"
        if dry_run:
            result = self._apt(["-s", "-y", recommends, "install", *targets], privileged=False)
            _raise_for_failure(result, "apt-get")
            return _simulated_changes(result.stdout)
        before = self.list_installed()
        result = self._apt(["-y", "-q", recommends, "install", *targets], privileged=True)
        _raise_for_failure(result, "apt-get")
        return _inventory_changes(before, self.list_installed())

    def remove(self, names: Sequence[str], dry_run: bool) -> Dict[str, Dict[str, str]]:
        """Remove packages with apt-get, or simulate with apt-get -s."""
        for name in names:
            validate_package_name(name)
        if dry_run:
            result = self._apt(["-s", "-y", "remove", *names], privileged=False)
            _raise_for_failure(result, "apt-get")
            return _simulated_changes(result.stdout)
        before = self.list_installed()
        result = self._apt(["-y", "-q", "remove", *names], privileged=True)
        _raise_for_failure(result, "apt-get")
        return _inventory_changes(before, self.list_installed())

    def list_repositories(self) -> Dict[str, Dict[str, Any]]:
        """Return apt sources from sources.list and sources.list.d."""
        files: list[Path] = []
        if self._sources_list.is_file():
            files.append(self._sources_list)
        if self._sources_directory.is_dir():
            files.extend(
                sorted(
                    path
                    for path in self._sources_directory.iterdir()
                    if path.suffix in (".list", ".sources") and path.is_file()
                )
            )
        repositories: Dict[str, Dict[str, Any]] = {}
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError as error:
                raise PackageBackendError(
                    "unable-to-read-repositories", f"Unable to read {path.name}."
                ) from error
            entries = (
                _parse_deb822_sources(text)
                if path.suffix == ".sources"
                else _parse_one_line_sources(text)
            )
            for index, entry in enumerate(entries, start=1):
                name = path.name if len(entries) == 1 else f"{path.name}-{index}"
                repositories[name] = entry
        return repositories

    def reboot_required(self) -> bool:
        """Return whether Debian-style tooling has left a reboot marker."""
        return any(marker.exists() for marker in self._reboot_markers)

    def _apt(self, args: Sequence[str], privileged: bool) -> subprocess.CompletedProcess[str]:
        """Run apt-get with a fixed locale and no prompts, as root when required."""
        prefix = self._privilege_prefix if privileged else []
        argv = [
            *prefix,
            "env",
            "LC_ALL=C",
            "DEBIAN_FRONTEND=noninteractive",
            "apt-get",
            *args,
        ]
        return self._runner(argv)


class UnsupportedPackageBackend:
    """Backend used when the host has no package manager this minion can drive."""

    def __init__(self, reason: str) -> None:
        """Store the message returned to the server for every package operation."""
        self._reason = reason

    def _error(self) -> PackageBackendError:
        return PackageBackendError("unsupported-host-package-manager", self._reason)

    def list_installed(self) -> Dict[str, Dict[str, str]]:
        """Reject inventory requests on unsupported hosts."""
        raise self._error()

    def install(
        self, packages: Mapping[str, str], dry_run: bool, install_recommends: bool
    ) -> Dict[str, Dict[str, str]]:
        """Reject installs on unsupported hosts."""
        raise self._error()

    def remove(self, names: Sequence[str], dry_run: bool) -> Dict[str, Dict[str, str]]:
        """Reject removals on unsupported hosts."""
        raise self._error()

    def list_repositories(self) -> Dict[str, Dict[str, Any]]:
        """Reject repository requests on unsupported hosts."""
        raise self._error()

    def reboot_required(self) -> bool:
        """Reject reboot checks on unsupported hosts."""
        raise self._error()


def select_package_backend(
    os_release: Path = OS_RELEASE_PATH,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> PackageBackend:
    """Choose the package backend for this host, or an unsupported placeholder."""
    if DEBIAN_FAMILY in _os_family_ids(os_release) and which("dpkg-query") and which("apt-get"):
        return DpkgPackageBackend()
    return UnsupportedPackageBackend(
        "This host has no supported package manager. Real software jobs require the "
        "dpkg and apt family of Linux distributions."
    )

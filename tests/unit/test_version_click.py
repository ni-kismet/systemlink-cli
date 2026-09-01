"""Tests for slcli version checking and update guidance."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import requests
from click.testing import CliRunner
from packaging.version import InvalidVersion

from slcli.main import cli
from slcli.version_click import (
    InstallMethod,
    VersionCheckResult,
    check_version,
    detect_install_method,
    fetch_latest_version,
    get_update_command,
)


class MockResponse:
    """Minimal response used by the PyPI version tests."""

    def __init__(self, payload: Any) -> None:
        """Initialize the response with its JSON payload."""
        self.payload = payload

    def raise_for_status(self) -> None:
        """Accept the mocked response."""

    def json(self) -> Any:
        """Return the configured response payload."""
        return self.payload


def test_fetch_latest_version(monkeypatch: Any) -> None:
    """The latest version comes from the PyPI package metadata."""
    monkeypatch.setattr(
        "slcli.version_click.requests.get",
        lambda url, timeout: MockResponse({"info": {"version": "1.30.0"}}),
    )

    assert fetch_latest_version() == "1.30.0"


def test_fetch_latest_version_rejects_invalid_remote_version(monkeypatch: Any) -> None:
    """Malformed PyPI versions are reported as invalid remote responses."""
    monkeypatch.setattr(
        "slcli.version_click.requests.get",
        lambda url, timeout: MockResponse({"info": {"version": "not-a-version"}}),
    )

    with pytest.raises(ValueError, match="PyPI returned an invalid version"):
        fetch_latest_version()


@pytest.mark.parametrize(
    ("current", "latest", "expected_status"),
    [
        ("1.2.3", "1.2.4", "outdated"),
        ("1.2.3", "1.2.3", "current"),
        ("1.2.4", "1.2.3", "ahead"),
    ],
)
def test_check_version_status(
    monkeypatch: Any, current: str, latest: str, expected_status: str
) -> None:
    """Version comparison distinguishes outdated, current, and ahead builds."""
    monkeypatch.setattr("slcli.version_click.fetch_latest_version", lambda: latest)
    monkeypatch.setattr("slcli.version_click.detect_install_method", lambda: InstallMethod.PIPX)

    result = check_version(current)

    assert result.status == expected_status
    assert result.install_method == "pipx"
    assert result.update_command == "pipx upgrade systemlink-cli"


@pytest.mark.parametrize(
    ("executable", "frozen", "expected"),
    [
        ("/opt/homebrew/Cellar/slcli/1.2.3/libexec/slcli", True, InstallMethod.HOMEBREW),
        ("/Users/test/scoop/apps/slcli/current/slcli.exe", True, InstallMethod.SCOOP),
        ("/tmp/slcli/slcli", True, InstallMethod.STANDALONE),
        ("/tmp/cellar/other-tool/slcli", True, InstallMethod.STANDALONE),
        ("/Users/test/pipx/venvs/systemlink-cli/bin/python", False, InstallMethod.PIPX),
        ("/Users/test/.local/share/uv/tools/systemlink-cli/bin/python", False, InstallMethod.UV),
    ],
)
def test_detect_install_method_from_executable(
    monkeypatch: Any, executable: str, frozen: bool, expected: InstallMethod
) -> None:
    """Manager-specific executable layouts take precedence over generic installs."""
    monkeypatch.setattr("slcli.version_click.sys.executable", executable)
    monkeypatch.setattr("slcli.version_click.sys.frozen", frozen, raising=False)

    assert detect_install_method() == expected


def test_detect_plain_pip_install(monkeypatch: Any, tmp_path: Path) -> None:
    """Installed distribution metadata falls back to plain pip."""
    module_path = tmp_path / "site-packages" / "slcli" / "version_click.py"
    monkeypatch.setattr("slcli.version_click.__file__", str(module_path))
    monkeypatch.setattr("slcli.version_click.sys.executable", "/venv/bin/python")
    monkeypatch.delattr("slcli.version_click.sys.frozen", raising=False)
    monkeypatch.setattr("slcli.version_click.distribution", lambda name: object())

    assert detect_install_method() == InstallMethod.PIP


def test_detect_development_install(monkeypatch: Any, tmp_path: Path) -> None:
    """A source checkout is identified as a development installation."""
    module_path = tmp_path / "slcli" / "version_click.py"
    (tmp_path / "pyproject.toml").touch()
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr("slcli.version_click.__file__", str(module_path))
    monkeypatch.setattr("slcli.version_click.sys.executable", "/venv/bin/python")
    monkeypatch.delattr("slcli.version_click.sys.frozen", raising=False)

    assert detect_install_method() == InstallMethod.DEVELOPMENT


def test_detect_unknown_install(monkeypatch: Any, tmp_path: Path) -> None:
    """Missing package metadata produces an explicit unknown result."""
    module_path = tmp_path / "slcli" / "version_click.py"
    monkeypatch.setattr("slcli.version_click.__file__", str(module_path))
    monkeypatch.setattr("slcli.version_click.sys.executable", "/tmp/python")
    monkeypatch.delattr("slcli.version_click.sys.frozen", raising=False)

    def missing_distribution(name: str) -> None:
        raise pytest.importorskip("importlib.metadata").PackageNotFoundError(name)

    monkeypatch.setattr("slcli.version_click.distribution", missing_distribution)

    assert detect_install_method() == InstallMethod.UNKNOWN


def test_update_commands_cover_managed_installations() -> None:
    """Each supported manager has actionable update guidance."""
    assert get_update_command(InstallMethod.HOMEBREW) == "brew upgrade slcli"
    assert get_update_command(InstallMethod.SCOOP) == "scoop update slcli"
    assert get_update_command(InstallMethod.PIPX) == "pipx upgrade systemlink-cli"
    assert get_update_command(InstallMethod.UV) == "uv tool upgrade systemlink-cli"
    assert get_update_command(InstallMethod.PIP) == (
        f'"{sys.executable}" -m pip install --upgrade systemlink-cli'
    )
    assert get_update_command(InstallMethod.DEVELOPMENT) == "git pull && poetry install"
    assert get_update_command(InstallMethod.STANDALONE) is None


def test_pip_update_command_quotes_windows_executable(monkeypatch: Any) -> None:
    """The pip update command quotes a Windows executable path."""
    monkeypatch.setattr("slcli.version_click.sys.executable", r"C:\Program Files\Python\python.exe")

    assert get_update_command(InstallMethod.PIP) == (
        r'"C:\Program Files\Python\python.exe" -m pip install --upgrade systemlink-cli'
    )


def test_version_command_shows_current_version_without_network() -> None:
    """The version group itself remains a local operation."""
    runner = CliRunner()

    result = runner.invoke(cli, ["version"])

    assert result.exit_code == 0
    assert result.output.startswith("slcli version ")


def test_version_check_shows_update_command(monkeypatch: Any) -> None:
    """Text output tells an outdated managed installation how to update."""
    monkeypatch.setattr(
        "slcli.version_click.check_version",
        lambda: VersionCheckResult("1.2.3", "1.3.0", "outdated", "homebrew", "brew upgrade slcli"),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version", "check"])

    assert result.exit_code == 0
    assert "A newer version is available" in result.output
    assert "brew upgrade slcli" in result.output


def test_version_check_json_and_fail_if_outdated(monkeypatch: Any) -> None:
    """JSON output supports automation and optional failure for stale installs."""
    monkeypatch.setattr(
        "slcli.version_click.check_version",
        lambda: VersionCheckResult(
            "1.2.3", "1.3.0", "outdated", "pipx", "pipx upgrade systemlink-cli"
        ),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version", "check", "-f", "json", "--fail-if-outdated"])

    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "outdated"


def test_version_check_network_failure(monkeypatch: Any) -> None:
    """A failed latest-version lookup uses the standard network exit code."""
    monkeypatch.setattr(
        "slcli.version_click.check_version",
        lambda: (_ for _ in ()).throw(requests.ConnectionError("offline")),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version", "check"])

    assert result.exit_code == 5
    assert "Unable to retrieve" in result.output


def test_version_check_invalid_remote_version(monkeypatch: Any) -> None:
    """A malformed remote version uses the network error exit code."""
    monkeypatch.setattr(
        "slcli.version_click.check_version",
        lambda: (_ for _ in ()).throw(ValueError("invalid remote version")),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version", "check"])

    assert result.exit_code == 5
    assert "Unable to retrieve" in result.output


def test_version_check_invalid_installed_version(monkeypatch: Any) -> None:
    """A malformed installed version uses the invalid-input exit code."""
    monkeypatch.setattr(
        "slcli.version_click.check_version",
        lambda: (_ for _ in ()).throw(InvalidVersion("invalid installed version")),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version", "check"])

    assert result.exit_code == 2
    assert "Invalid version" in result.output


def test_version_command_skips_credential_migration(monkeypatch: Any) -> None:
    """Version commands do not inspect SystemLink credentials."""
    monkeypatch.setattr(
        "slcli.profiles.has_keyring_credentials",
        lambda: (_ for _ in ()).throw(AssertionError("credentials should not be inspected")),
    )
    runner = CliRunner()

    result = runner.invoke(cli, ["version"])

    assert result.exit_code == 0

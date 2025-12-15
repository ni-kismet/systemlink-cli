"""Test main CLI functionality."""

from typing import Any

from click.testing import CliRunner

from slcli.main import cli, get_version
from slcli.platform import PLATFORM_SLE


def test_version_flag() -> None:
    """Test that --version flag works correctly."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "slcli version" in result.output
    assert len(result.output.strip().split()) == 3  # "slcli version X.Y.Z"


def test_get_version() -> None:
    """Test that get_version returns a valid version string."""
    version = get_version()

    # Should return a string that looks like a version
    assert isinstance(version, str)
    assert len(version) > 0

    # Should either be a proper version (x.y.z) or "unknown"
    if version != "unknown":
        parts = version.split(".")
        assert len(parts) >= 2  # At least major.minor
        for part in parts:
            assert part.isdigit()  # Each part should be numeric


def test_help_includes_version() -> None:
    """Test that help includes the version option."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "--version" in result.output
    assert "Show version and exit" in result.output


def test_no_command_shows_help() -> None:
    """Test that running with no command shows help."""
    runner = CliRunner()
    result = runner.invoke(cli, [])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "Commands:" in result.output


def test_login_with_flags(monkeypatch: Any) -> None:
    """Ensure login stores credentials and detects platform with flags provided."""
    stored: dict[str, dict[str, str]] = {}

    def fake_set_password(service: str, key: str, value: str) -> None:
        stored.setdefault(service, {})[key] = value

    monkeypatch.setattr("slcli.main.keyring.set_password", fake_set_password)
    monkeypatch.setattr("slcli.main.detect_platform", lambda *a, **kw: PLATFORM_SLE)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "login",
            "--url",
            "https://example.test",
            "--api-key",
            "abc123",
            "--web-url",
            "https://web.example.test",
        ],
    )

    assert result.exit_code == 0
    assert stored["systemlink-cli"]["SYSTEMLINK_CONFIG"]
    assert "Platform: SystemLink Enterprise" in result.output


def test_logout_removes_credentials(monkeypatch: Any) -> None:
    """Ensure logout deletes all stored keyring entries."""
    deleted: list[tuple[str, str]] = []

    def fake_delete_password(service: str, key: str) -> None:
        deleted.append((service, key))

    monkeypatch.setattr("slcli.main.keyring.delete_password", fake_delete_password)
    runner = CliRunner()
    result = runner.invoke(cli, ["logout"])

    assert result.exit_code == 0
    assert ("systemlink-cli", "SYSTEMLINK_API_KEY") in deleted
    assert ("systemlink-cli", "SYSTEMLINK_API_URL") in deleted
    assert ("systemlink-cli", "SYSTEMLINK_CONFIG") in deleted


def test_info_json(monkeypatch: Any) -> None:
    """Ensure info emits JSON when requested."""
    sample = {
        "logged_in": True,
        "platform": PLATFORM_SLE,
        "platform_display": "SystemLink Enterprise",
        "api_url": "https://example.test",
        "web_url": "https://web.example.test",
        "features": {"templates": True},
    }

    monkeypatch.setattr("slcli.main.get_platform_info", lambda: sample)
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "--format", "json"])

    assert result.exit_code == 0
    assert '"platform_display": "SystemLink Enterprise"' in result.output

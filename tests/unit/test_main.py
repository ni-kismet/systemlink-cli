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


def test_login_with_flags(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login stores credentials in profile config with flags provided."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr("slcli.main.detect_platform", lambda *a, **kw: PLATFORM_SLE)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "login",
            "--profile",
            "test",
            "--url",
            "https://example.test",
            "--api-key",
            "abc123",
            "--web-url",
            "https://web.example.test",
        ],
        input="\n",  # Skip optional workspace prompt
    )

    assert result.exit_code == 0, result.output
    assert "Profile 'test' saved successfully" in result.output
    assert "Platform: SystemLink Enterprise" in result.output
    # Verify config was written
    assert config_file.exists()


def test_logout_removes_credentials(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure logout deletes profile from config."""
    import json

    config_file = tmp_path / "config.json"
    # Create a config file with a profile (uses hyphens for keys)
    config_data = {
        "version": 1,
        "current-profile": "test",
        "profiles": {
            "test": {
                "server": "https://example.test",
                "api-key": "abc123",
                "web-url": "https://web.example.test",
                "platform": "SLE",
            }
        },
    }
    config_file.write_text(json.dumps(config_data))
    config_file.chmod(0o600)

    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    # Mock keyring deletes to avoid errors
    monkeypatch.setattr("slcli.main.keyring.delete_password", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(cli, ["logout", "--force"])

    assert result.exit_code == 0
    assert "Profile 'test' removed" in result.output


def test_info_json(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure info emits JSON when requested."""
    import json as json_mod

    config_file = tmp_path / "config.json"
    # Create an empty config
    config_data: dict[str, Any] = {"version": 1, "current_profile": None, "profiles": {}}
    config_file.write_text(json_mod.dumps(config_data))
    config_file.chmod(0o600)
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

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

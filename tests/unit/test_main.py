"""Test main CLI functionality."""

import importlib
import json
from typing import Any, Optional

import click
from click.testing import CliRunner

import slcli
from slcli.main import cli, get_version
from slcli.platform import PLATFORM_SLE

VALID_API_KEY = "4LpbauiNA-UI9IhjqZoS4UeikZtExLK9Q_Q77d1bJd"


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
    assert "login" in result.output
    assert "workspace" in result.output


def test_importing_package_does_not_patch_click_output(monkeypatch: Any) -> None:
    """Importing slcli should not mutate Click output globally."""
    original_echo = click.echo
    original_secho = click.secho
    original_utils_echo = click.utils.echo

    monkeypatch.setattr(click, "echo", original_echo)
    monkeypatch.setattr(click, "secho", original_secho)
    monkeypatch.setattr(click.utils, "echo", original_utils_echo)

    importlib.reload(slcli)

    assert click.echo is original_echo
    assert click.secho is original_secho
    assert click.utils.echo is original_utils_echo


def test_cli_installs_rich_output(monkeypatch: Any) -> None:
    """The root CLI installs Rich output before executing commands."""
    installed: list[bool] = []

    monkeypatch.setattr("slcli.main.install_rich_output", lambda: installed.append(True))

    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert installed == [True]


def test_login_with_flags(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login stores credentials in profile config with flags provided."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok"},
            "platform": PLATFORM_SLE,
        },
    )
    # Mock keyring to return None (no existing credentials)
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",  # Skip optional workspace prompt and readonly confirmation
    )

    assert result.exit_code == 0, result.output
    assert "Profile 'test' saved successfully" in result.output
    assert "Connection: ✓ Verified" in result.output
    assert "Platform: SystemLink Enterprise" in result.output
    # Verify config was written
    assert config_file.exists()


def test_login_rejects_unauthorized_api_key(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login fails when the server rejects the API key."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": False,
            "services": {"Auth": "unauthorized"},
            "platform": PLATFORM_SLE,
        },
    )
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",
    )

    assert result.exit_code != 0
    assert "API key validation failed" in result.output
    assert "Profile was not saved" in result.output
    assert not config_file.exists()


def test_login_rejects_inconclusive_profile_verification(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login reports inconclusive verification for non-auth probe failures."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": False,
            "services": {"Auth": "unauthorized", "Comments": "not_found"},
            "platform": PLATFORM_SLE,
        },
    )
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",
    )

    assert result.exit_code == 1
    assert "profile verification was inconclusive" in result.output
    assert "Profile was not saved" in result.output
    assert not config_file.exists()


def test_login_rejects_unknown_auth_verification_state(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login covers the fallback branch when auth verification returns None."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": None,
            "services": {"Auth": "error"},
            "platform": PLATFORM_SLE,
        },
    )
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",
    )

    assert result.exit_code == 1
    assert "profile verification was inconclusive" in result.output
    assert "Profile was not saved" in result.output
    assert not config_file.exists()


def test_login_reports_file_query_fallback(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login explains file query fallback when Elasticsearch is unavailable."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "File": "fallback"},
            "file_query_endpoint": "query-files-linq",
            "elasticsearch_available": False,
            "platform": PLATFORM_SLE,
        },
    )
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",
    )

    assert result.exit_code == 0, result.output
    assert "query-files-linq (Elasticsearch unavailable)" in result.output
    assert "file list' will fall back automatically" in result.output


def test_login_reports_sls_query_files(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure login reports query-files when SLS uses the structured query route."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "File": "ok"},
            "file_query_endpoint": "query-files",
            "elasticsearch_available": False,
            "platform": "SLS",
        },
    )
    monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

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
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ],
        input="\n\n",
    )

    assert result.exit_code == 0, result.output
    assert "File query: query-files" in result.output


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

    monkeypatch.setattr("slcli.main.get_platform_info", lambda **kw: sample)
    runner = CliRunner()
    result = runner.invoke(cli, ["info", "--format", "json"])

    assert result.exit_code == 0


def test_login_prompts_migration_with_existing_keyring(monkeypatch: Any, tmp_path: Any) -> None:
    """Test that CLI automatically migrates credentials when keyring exists."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *a, **kw: {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok"},
            "platform": PLATFORM_SLE,
        },
    )

    # Mock keyring to return existing credentials
    def mock_get_password(service: str, key: str) -> Optional[str]:
        if key == "SYSTEMLINK_CONFIG":
            return json.dumps(
                {
                    "api_url": "https://existing.test",
                    "api_key": "existing-key",
                    "web_url": "https://web.existing.test",
                    "platform": "SLE",
                }
            )
        return None

    # Mock keyring at module level
    import keyring as keyring_module

    monkeypatch.setattr(keyring_module, "get_password", mock_get_password)
    monkeypatch.setattr(keyring_module, "delete_password", lambda *a, **kw: None)

    runner = CliRunner()
    # Run any command - migration should happen automatically
    result = runner.invoke(
        cli,
        ["info"],
    )

    # Migration should have happened automatically
    assert "Migration Required" in result.output
    assert "Migrated credentials to profile 'default'" in result.output
    assert "Migration complete" in result.output


def test_login_migration_accepted(monkeypatch: Any, tmp_path: Any) -> None:
    """Test that automatic migration creates the profile correctly."""
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

    # Mock keyring to return existing credentials
    def mock_get_password(service: str, key: str) -> Optional[str]:
        if key == "SYSTEMLINK_CONFIG":
            return json.dumps(
                {
                    "api_url": "https://migrated.test",
                    "api_key": "migrated-key",
                    "web_url": "https://web.migrated.test",
                    "platform": "SLE",
                }
            )
        return None

    # Mock keyring at module level
    import keyring as keyring_module

    monkeypatch.setattr(keyring_module, "get_password", mock_get_password)
    monkeypatch.setattr(keyring_module, "delete_password", lambda *a, **kw: None)

    runner = CliRunner()
    # Run any command - migration should happen automatically
    result = runner.invoke(
        cli,
        ["info"],
    )

    assert result.exit_code == 0
    assert "Migrated credentials to profile 'default'" in result.output
    assert "Migration complete" in result.output

    # Verify profile was created
    assert config_file.exists()
    import json as json_mod

    saved = json_mod.loads(config_file.read_text())
    assert saved["current-profile"] == "default"
    assert "default" in saved["profiles"]
    assert saved["profiles"]["default"]["server"] == "https://migrated.test"

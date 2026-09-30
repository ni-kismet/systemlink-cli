"""Test main CLI functionality."""

import importlib
from typing import Any
from unittest.mock import patch

import click
from click.testing import CliRunner

import slcli
from slcli.main import cli, get_version
from slcli.platform import PLATFORM_SLE, PLATFORM_SLS
from slcli.utils import ExitCodes

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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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


def test_login_prompts_to_trust_certificate_and_retries(monkeypatch: Any, tmp_path: Any) -> None:
    """Login should persist an approved certificate and retry the service probe."""
    from slcli.ssl_trust import ServerCertificate

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    certificate = ServerCertificate(
        origin="https://example.test:443",
        pem=b"pem",
        fingerprint="D" * 64,
        subject="commonName=example.test",
        issuer="commonName=example.test",
        sans=["example.test"],
        not_before="before",
        not_after="after",
        self_signed=True,
    )
    failed_status = {
        "server_reachable": False,
        "auth_valid": None,
        "services": {"Auth": "certificate_error"},
        "certificate_error": True,
        "certificate": certificate.to_dict(),
        "platform": "unreachable",
    }
    verified_status = {
        "server_reachable": True,
        "auth_valid": True,
        "services": {"Auth": "ok"},
        "platform": PLATFORM_SLE,
    }
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

    with patch(
        "slcli.config_click.check_service_status", side_effect=[failed_status, verified_status]
    ) as check_status, patch(
        "slcli.config_click.inspect_server_certificate", return_value=certificate
    ):
        result = CliRunner().invoke(
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
            input="y\n\n",
        )

    assert result.exit_code == 0, result.output
    assert "Certificate: ✓ Trusted for this server" in result.output
    assert check_status.call_count == 2
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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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

    assert result.exit_code == ExitCodes.PERMISSION_DENIED
    assert "API key validation failed" in result.output
    assert "Profile was not saved" in result.output
    assert not config_file.exists()


def test_login_rejects_unauthorized_api_key_for_sls(monkeypatch: Any, tmp_path: Any) -> None:
    """Ensure an unauthorized SLS probe returns a permission error."""
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
            "platform": PLATFORM_SLS,
        },
    )
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

    result = CliRunner().invoke(
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

    assert result.exit_code == ExitCodes.PERMISSION_DENIED
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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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
    monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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


def test_logout_removes_os_credentials(monkeypatch: Any, tmp_path: Any) -> None:
    """Logout removes profile metadata and its OS-stored credentials."""
    import json
    from unittest.mock import MagicMock

    config_file = tmp_path / "config.json"
    # Create a config file with a profile (uses hyphens for keys)
    config_data = {
        "version": 1,
        "current-profile": "test",
        "profiles": {
            "test": {
                "id": "profile-id",
                "server": "https://example.test",
                "credential-store": "os",
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
    delete_credentials = MagicMock()
    monkeypatch.setattr("slcli.credentials.delete_profile_credentials", delete_credentials)

    runner = CliRunner()
    result = runner.invoke(cli, ["logout", "--force"])

    assert result.exit_code == 0
    assert "Profile 'test' removed" in result.output
    delete_credentials.assert_called_once_with("profile-id", "os", "test", "api-key")


def test_logout_file_api_key_profile_cleans_legacy_tokens(monkeypatch: Any, tmp_path: Any) -> None:
    """Logout supplies the old PKCE account name even for a current API-key profile."""
    import json
    from unittest.mock import MagicMock

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "test",
                "profiles": {
                    "test": {
                        "id": "profile-id",
                        "server": "https://example.test",
                        "api-key": "file-key",
                        "credential-store": "file",
                        "auth-mode": "api-key",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    cleanup = MagicMock()
    monkeypatch.setattr("slcli.credentials.delete_profile_credentials", cleanup)

    result = CliRunner().invoke(cli, ["logout", "--force"])

    assert result.exit_code == 0
    cleanup.assert_called_once_with("profile-id", "file", "test", "api-key")


def test_logout_keeps_pending_record_when_credential_cleanup_fails(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """A cleanup failure leaves a persisted credential ID for retry."""
    import json
    from unittest.mock import MagicMock

    from slcli.credentials import CredentialStoreError

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "test",
                "profiles": {
                    "test": {
                        "id": "profile-id",
                        "server": "https://example.test",
                        "credential-store": "os",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.credentials.delete_profile_credentials",
        MagicMock(side_effect=CredentialStoreError("store locked")),
    )

    result = CliRunner().invoke(cli, ["logout", "--force"])

    assert result.exit_code != 0
    saved = json.loads(config_file.read_text())
    assert "test" not in saved.get("profiles", {})
    assert saved["pending-credential-deletions"][0]["id"] == "profile-id"


def test_logout_does_not_delete_credentials_when_config_save_fails(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """A config write failure prevents destructive credential cleanup."""
    import json
    from unittest.mock import MagicMock

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "test",
                "profiles": {
                    "test": {
                        "id": "profile-id",
                        "server": "https://example.test",
                        "credential-store": "os",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

    def fail_save(_self: Any) -> None:
        raise RuntimeError("config is read-only")

    monkeypatch.setattr("slcli.profiles.ProfileConfig.save", fail_save)
    delete_credentials = MagicMock()
    monkeypatch.setattr("slcli.credentials.delete_profile_credentials", delete_credentials)

    result = CliRunner().invoke(cli, ["logout", "--force"])

    assert result.exit_code != 0
    assert "test" in json.loads(config_file.read_text())["profiles"]
    delete_credentials.assert_not_called()


def test_logout_all_persists_successful_cleanup_before_later_failure(
    monkeypatch: Any, tmp_path: Any
) -> None:
    """A later cleanup failure preserves only profiles whose credentials remain."""
    import json
    from unittest.mock import MagicMock

    import click

    from slcli.credentials import CredentialStoreError

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "first",
                "profiles": {
                    "first": {
                        "id": "first-id",
                        "server": "https://first.example.test",
                        "credential-store": "os",
                    },
                    "second": {
                        "id": "second-id",
                        "server": "https://second.example.test",
                        "credential-store": "os",
                    },
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    delete_credentials = MagicMock(side_effect=[None, CredentialStoreError("store locked")])
    monkeypatch.setattr("slcli.credentials.delete_profile_credentials", delete_credentials)
    error_messages: list[str] = []

    class RecordingClickException(click.ClickException):
        def __init__(self, message: str) -> None:
            error_messages.append(message)
            super().__init__(message)

    monkeypatch.setattr("slcli.main.click.ClickException", RecordingClickException)

    result = CliRunner().invoke(cli, ["logout", "--all", "--force"], terminal_width=200)

    saved = json.loads(config_file.read_text())
    assert result.exit_code != 0
    assert "One earlier profile was removed" in error_messages[0]
    assert "profiles" not in saved
    assert saved["pending-credential-deletions"][0]["id"] == "second-id"
    assert delete_credentials.call_count == 2

    delete_credentials.side_effect = None
    retry = CliRunner().invoke(cli, ["logout", "--all", "--force"])

    assert retry.exit_code == 0
    assert "pending-credential-deletions" not in json.loads(config_file.read_text())
    assert delete_credentials.call_count == 3


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

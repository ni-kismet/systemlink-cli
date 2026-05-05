"""Unit tests for the config_click CLI commands."""

import json
from pathlib import Path
from typing import Any, Dict

import click
import pytest
from click.testing import CliRunner

from slcli.config_click import _normalize_base_url, register_config_commands
from slcli.utils import ExitCodes

VALID_API_KEY = "4LpbauiNA-UI9IhjqZoS4UeikZtExLK9Q_Q77d1bJd"


def make_cli() -> click.Group:
    """Create a test CLI with config commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_config_commands(test_cli)
    return test_cli


class TestListProfiles:
    """Tests for the list command."""

    def test_list_profiles_empty(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test listing profiles when none exist."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list"])

        assert result.exit_code == 0
        assert "No profiles configured" in result.output

    def test_list_profiles_table(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test listing profiles in table format."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "dev",
            "profiles": {
                "dev": {
                    "server": "https://dev.example.com",
                    "api-key": "dev-key",
                },
                "prod": {
                    "server": "https://prod.example.com",
                    "api-key": "prod-key",
                    "workspace": "Production",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list"])

        assert result.exit_code == 0
        assert "dev" in result.output
        assert "prod" in result.output
        assert "dev.example.com" in result.output
        assert "Production" in result.output

    def test_list_profiles_json(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test listing profiles in JSON format."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.example.com",
                    "api-key": "test-key",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 1
        assert output[0]["name"] == "test"
        assert output[0]["server"] == "https://test.example.com"


class TestCurrentProfile:
    """Tests for the current command."""

    def test_current_profile_none(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test showing current profile when none is set."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "current"])

        # Exit code 1 indicates no profile is configured
        assert result.exit_code != 0 or "No current profile" in result.output

    def test_current_profile_set(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test showing current profile when one is set."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "myprofile",
            "profiles": {
                "myprofile": {
                    "server": "https://api.example.com",
                    "api-key": "key123",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "current"])

        assert result.exit_code == 0
        assert "myprofile" in result.output


class TestUseProfile:
    """Tests for the use command."""

    def test_use_profile_success(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test switching to an existing profile."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "old",
            "profiles": {
                "old": {"server": "https://old.com", "api-key": "old-key"},
                "new": {"server": "https://new.com", "api-key": "new-key"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "use", "new"])

        assert result.exit_code == 0
        assert "Switched to profile" in result.output
        assert "new" in result.output

        # Verify the file was updated
        saved = json.loads(config_file.read_text())
        assert saved["current-profile"] == "new"

    def test_use_profile_not_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test switching to a non-existent profile."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "existing",
            "profiles": {
                "existing": {"server": "https://example.com", "api-key": "key"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "use", "nonexistent"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestViewConfig:
    """Tests for the view command."""

    def test_view_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test viewing the full config in table format."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                    "workspace": "Engineering",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "view"])

        assert result.exit_code == 0
        assert "slcli Configuration" in result.output
        assert "SETTING" in result.output
        assert "VALUE" in result.output
        assert "Current Profile" in result.output
        assert "test" in result.output
        assert "https://test.com" in result.output
        assert "Engineering" in result.output
        assert "****1234" in result.output
        assert "secret1234" not in result.output

    def test_view_config_show_secrets(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test viewing the full config with secrets shown."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "view", "--show-secrets"])

        assert result.exit_code == 0
        assert "API Key" in result.output
        assert "secret1234" in result.output

    def test_view_config_without_current_profile(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test viewing the config when no current profile is set."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "view"])

        assert result.exit_code == 0
        assert "Current Profile" in result.output
        assert "(none)" in result.output


class TestDeleteProfile:
    """Tests for the delete command."""

    def test_delete_profile_success(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test deleting a profile with force flag."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "todelete",
            "profiles": {
                "todelete": {"server": "https://delete.com", "api-key": "key"},
                "keep": {"server": "https://keep.com", "api-key": "key2"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "delete", "todelete", "--force"])

        assert result.exit_code == 0
        assert "deleted" in result.output.lower() or "removed" in result.output.lower()

        # Verify the file was updated
        saved = json.loads(config_file.read_text())
        assert "todelete" not in saved["profiles"]
        assert "keep" in saved["profiles"]

    def test_delete_profile_not_found(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test deleting a non-existent profile."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "existing",
            "profiles": {
                "existing": {"server": "https://example.com", "api-key": "key"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "delete", "nonexistent", "--force"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestAddProfileTrailingSlash:
    """Tests that trailing slashes are stripped from URLs during profile creation."""

    def test_trailing_slash_stripped_from_url(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that trailing slashes are stripped from the API URL."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        # Mock check_service_status to avoid network calls
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda url, key: {
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {"Auth": "ok"},
            },
        )
        monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

        from slcli.main import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "login",
                "--profile",
                "test-slash",
                "--url",
                "https://api.example.com/",
                "--api-key",
                VALID_API_KEY,
                "--web-url",
                "https://web.example.com/",
            ],
            input="\n\n",
        )

        assert result.exit_code == 0
        saved = json.loads(config_file.read_text())
        profile = saved["profiles"]["test-slash"]
        assert profile["server"] == "https://api.example.com"
        assert profile.get("web-url", "") == "https://web.example.com"

    def test_multiple_trailing_slashes_stripped(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that multiple trailing slashes are stripped."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda url, key: {
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {"Auth": "ok"},
            },
        )
        monkeypatch.setattr("slcli.main.keyring.get_password", lambda *a, **kw: None)

        from slcli.main import cli

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "login",
                "--profile",
                "test-multi-slash",
                "--url",
                "https://api.example.com///",
                "--api-key",
                VALID_API_KEY,
                "--web-url",
                "https://web.example.com///",
            ],
            input="\n\n",
        )

        assert result.exit_code == 0
        saved = json.loads(config_file.read_text())
        profile = saved["profiles"]["test-multi-slash"]
        assert profile["server"] == "https://api.example.com"
        assert profile.get("web-url", "") == "https://web.example.com"

    def test_config_add_rejects_unreachable_server(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that config add fails instead of saving an unreachable server."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda url, key: {
                "server_reachable": False,
                "platform": "unreachable",
                "auth_valid": None,
                "services": {},
            },
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "config",
                "add",
                "--profile",
                "offline",
                "--url",
                "https://offline.example.com",
                "--api-key",
                VALID_API_KEY,
                "--web-url",
                "https://web.example.com",
            ],
            input="\n",
        )

        assert result.exit_code == ExitCodes.NETWORK_ERROR
        assert "Profile was not saved" in result.output
        assert not config_file.exists()

    def test_config_add_rejects_malformed_api_key(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that config add rejects API keys that do not match the expected format."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        def fail_if_called(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("check_service_status should not run for malformed API keys")

        monkeypatch.setattr("slcli.config_click.check_service_status", fail_if_called)

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "config",
                "add",
                "--profile",
                "bad-key",
                "--url",
                "https://example.test",
                "--api-key",
                "abc123",
                "--web-url",
                "https://web.example.test",
            ],
            input="\n",
        )

        assert result.exit_code == ExitCodes.INVALID_INPUT
        assert "API key must be a 42-character URL-safe token" in result.output
        assert not config_file.exists()


class TestAddProfileUrlValidation:
    """Tests that config add rejects malformed URLs before probing the server."""

    @pytest.mark.parametrize(
        ("raw_url", "label", "expected_message"),
        [
            ("", "SystemLink API URL", "SystemLink API URL cannot be empty."),
            (
                "ftp://example.test",
                "SystemLink API URL",
                "SystemLink API URL must use HTTP or HTTPS.",
            ),
            (
                "https://",
                "SystemLink API URL",
                "SystemLink API URL must include a valid host name.",
            ),
            (
                "https://example.test/api",
                "SystemLink API URL",
                "SystemLink API URL must be a base URL without a path, query string, or fragment.",
            ),
            (
                "https://web.example.test?foo=bar",
                "SystemLink Web UI URL",
                "SystemLink Web UI URL must be a base URL without a path, query string, or fragment.",
            ),
        ],
    )
    def test_normalize_base_url_rejects_invalid_values(
        self,
        raw_url: str,
        label: str,
        expected_message: str,
        capsys: Any,
    ) -> None:
        """Test that malformed URLs are rejected with a clear validation error."""
        with pytest.raises(SystemExit) as exc_info:
            _normalize_base_url(raw_url, label)

        captured = capsys.readouterr()
        assert exc_info.value.code == ExitCodes.INVALID_INPUT
        assert expected_message in captured.err

    @pytest.mark.parametrize(
        ("raw_url", "label", "expected_url", "expected_output"),
        [
            (
                "http://example.test",
                "SystemLink API URL",
                "http://example.test",
                "",
            ),
            (
                "example.test",
                "SystemLink API URL",
                "https://example.test",
                "Warning: Adding HTTPS protocol to systemlink api url.",
            ),
        ],
    )
    def test_normalize_base_url_normalizes_valid_shortcuts(
        self, raw_url: str, label: str, expected_url: str, expected_output: str, capsys: Any
    ) -> None:
        """Test that HTTP and scheme-less URLs are normalized for convenience."""
        normalized = _normalize_base_url(raw_url, label)

        captured = capsys.readouterr()
        assert normalized == expected_url
        if expected_output:
            assert expected_output in captured.out
        else:
            assert captured.out == ""

    @pytest.mark.parametrize(
        ("option_name", "url_value", "expected_message"),
        [
            ("--url", "ftp://example.test", "SystemLink API URL must use HTTP or HTTPS."),
            ("--url", "https://", "SystemLink API URL must include a valid host name."),
            (
                "--url",
                "https://example.test/api",
                "SystemLink API URL must be a base URL without a path, query string, or fragment.",
            ),
            (
                "--web-url",
                "https://web.example.test?foo=bar",
                "SystemLink Web UI URL must be a base URL without a path, query string, or fragment.",
            ),
        ],
    )
    def test_config_add_rejects_invalid_urls_before_connectivity_check(
        self,
        tmp_path: Path,
        monkeypatch: Any,
        option_name: str,
        url_value: str,
        expected_message: str,
    ) -> None:
        """Test that malformed URLs fail validation before any server probe occurs."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        def fail_if_called(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("check_service_status should not run for malformed URLs")

        monkeypatch.setattr("slcli.config_click.check_service_status", fail_if_called)

        cli = make_cli()
        runner = CliRunner()
        args = [
            "config",
            "add",
            "--profile",
            "bad-url",
            "--url",
            "https://example.test",
            "--api-key",
            VALID_API_KEY,
            "--web-url",
            "https://web.example.test",
        ]
        option_index = args.index(option_name)
        args[option_index + 1] = url_value

        result = runner.invoke(cli, args, input="\n")

        assert result.exit_code == ExitCodes.INVALID_INPUT
        assert expected_message in result.output
        assert not config_file.exists()

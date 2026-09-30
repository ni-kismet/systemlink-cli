"""Unit tests for the config_click CLI commands."""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from slcli.config_click import _normalize_base_url, register_config_commands
from slcli.credentials import CredentialStoreError, describe_credential_store
from slcli.platform import PLATFORM_SLS
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

    def test_view_config_reports_effective_env_overrides(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Config view should show a warning when env overrides are active."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                    "web-url": "https://web.test.com",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setenv("SLCLI_API_KEY", "env-secret")

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "view"])

        assert result.exit_code == 0
        # Should NOT show effective source rows in table
        assert "API Key Source" not in result.output
        assert "Effective API URL" not in result.output
        assert "API Key" in result.output

    def test_view_config_emits_override_warning_to_stderr(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Config view should emit the override warning via stderr."""
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
        monkeypatch.setenv("SLCLI_API_KEY", "env-secret")

        echo_calls: list[tuple[str, bool]] = []

        def fake_echo(message: Any = "", err: bool = False, **_: Any) -> None:
            echo_calls.append((str(message), err))

        def fake_render_table(**_: Any) -> None:
            return None

        monkeypatch.setattr("slcli.config_click.click.echo", fake_echo)
        monkeypatch.setattr("slcli.config_click.render_table", fake_render_table)

        cli = make_cli()
        config_group: Any = cli.commands["config"]
        view_command: Any = config_group.commands["view"]
        callback: Any = view_command.callback
        callback(format="table", show_secrets=False)

        warning_messages = [
            message
            for message, is_stderr in echo_calls
            if is_stderr and "Environment overrides active" in message
        ]

        assert warning_messages == [
            "\n⚠️  Environment overrides active (API Key). Run 'slcli info' for effective values."
        ]

    def test_view_config_does_not_show_effective_sources(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Config view should not show effective/source rows (those belong to slcli info)."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                    "web-url": "https://web.test.com",
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
        # Should show stored config values
        assert "https://test.com" in result.output
        assert "https://web.test.com" in result.output
        # Should NOT show effective/source rows
        assert "Effective API URL" not in result.output
        assert "API URL Source" not in result.output
        assert "Effective Web URL" not in result.output
        assert "Web URL Source" not in result.output
        assert "Active Overrides" not in result.output
        # No env override warning when no overrides active
        assert "Environment overrides active" not in result.output

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

    def test_view_config_json_without_env_overrides(self, tmp_path: Path, monkeypatch: Any) -> None:
        """JSON output should show stored profile values without effective/source keys."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "secret1234",
                    "web-url": "https://web.test.com",
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
        result = runner.invoke(cli, ["config", "view", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["current-profile"] == "test"
        assert "test" in data["profiles"]
        assert data["profiles"]["test"]["server"] == "https://test.com"
        assert data["profiles"]["test"]["web-url"] == "https://web.test.com"
        # API key should be masked
        assert data["profiles"]["test"]["api-key"] == "****1234"
        # Should not contain effective/source keys
        assert "effective" not in data
        assert "env-overrides" not in data

    def test_view_config_json_with_env_overrides(self, tmp_path: Path, monkeypatch: Any) -> None:
        """JSON output should include env-overrides list when env vars are set."""
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
        monkeypatch.setenv("SLCLI_API_KEY", "env-secret")
        monkeypatch.setenv("SYSTEMLINK_WEB_URL", "https://override.com")

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "view", "--format", "json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "env-overrides" in data
        assert "API Key" in data["env-overrides"]
        assert "Web URL" in data["env-overrides"]
        assert "effective" not in data


def test_view_config_json_show_secrets_decodes_pkce_bundle(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """JSON output should expose PKCE credentials as an object when requested."""
    config_file = tmp_path / "config.json"
    credentials = {"access-token": "access-token", "refresh-token": "refresh-token"}
    config_data: Dict[str, Any] = {
        "current-profile": "test",
        "profiles": {
            "test": {
                "server": "https://test.com",
                "auth-mode": "pkce",
                "credential-store": "file",
                "pkce-credentials": credentials,
            },
        },
    }
    config_file.write_text(json.dumps(config_data))
    config_file.chmod(0o600)
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

    result = CliRunner().invoke(
        make_cli(), ["config", "view", "--format", "json", "--show-secrets"]
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["profiles"]["test"]["pkce-credentials"] == credentials


@pytest.mark.parametrize("secret_value", ["not-json", "[]"])
def test_view_config_json_rejects_malformed_pkce_bundle(
    secret_value: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Malformed PKCE data should produce a CLI error, not a traceback."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "test",
                "profiles": {
                    "test": {
                        "server": "https://test.com",
                        "auth-mode": "pkce",
                        "credential-store": "os",
                    }
                },
            }
        )
    )
    config_file.chmod(0o600)
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr("slcli.config_click._get_profile_secret", lambda *_args: secret_value)

    result = CliRunner().invoke(
        make_cli(), ["config", "view", "--format", "json", "--show-secrets"]
    )

    assert result.exit_code == ExitCodes.GENERAL_ERROR
    assert "Stored PKCE credentials for profile 'test' are invalid" in result.output
    assert "Traceback" not in result.output


class TestSecureProfiles:
    """Tests for moving plaintext credentials into the OS store."""

    def test_secure_moves_plaintext_api_key_to_os_store(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """The plaintext key is removed only after its OS-store write succeeds."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "server": "https://dev.example.com",
                            "api-key": VALID_API_KEY,
                        }
                    },
                }
            )
        )
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        store_secret = MagicMock()
        monkeypatch.setattr("slcli.config_click.set_credential", store_secret)

        result = CliRunner().invoke(make_cli(), ["config", "secure"])

        assert result.exit_code == 0, result.output
        store_secret.assert_called_once()
        saved_profile = json.loads(config_file.read_text())["profiles"]["dev"]
        assert "api-key" not in saved_profile
        assert saved_profile["credential-store"] == "os"
        assert saved_profile["id"]

    def test_secure_leaves_plaintext_when_os_store_write_fails(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A failed secure migration does not discard the original credential."""
        config_file = tmp_path / "config.json"
        original = {
            "current-profile": "dev",
            "profiles": {"dev": {"server": "https://dev.example.com", "api-key": VALID_API_KEY}},
        }
        config_file.write_text(json.dumps(original))
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.set_credential",
            MagicMock(side_effect=CredentialStoreError("store unavailable")),
        )

        result = CliRunner().invoke(make_cli(), ["config", "secure"])

        assert result.exit_code == ExitCodes.INVALID_INPUT
        saved_profile = json.loads(config_file.read_text())["profiles"]["dev"]
        assert saved_profile["api-key"] == VALID_API_KEY

    def test_secure_cleans_staged_credentials_when_save_fails(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A failed config save preserves plaintext and removes staged OS credentials."""
        from slcli.profiles import ProfileConfig

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {"server": "https://dev.example.com", "api-key": VALID_API_KEY}
                    },
                }
            )
        )
        monkeypatch.setattr(ProfileConfig, "get_config_path", classmethod(lambda cls: config_file))
        monkeypatch.setattr(ProfileConfig, "save", MagicMock(side_effect=RuntimeError("disk full")))
        staged = MagicMock()
        cleanup = MagicMock()
        monkeypatch.setattr("slcli.config_click.set_credential", staged)
        monkeypatch.setattr("slcli.credentials.delete_credential", cleanup)

        result = CliRunner().invoke(make_cli(), ["config", "secure"])

        assert result.exit_code != 0
        assert "Could not save secured profiles" in result.output
        assert json.loads(config_file.read_text())["profiles"]["dev"]["api-key"] == VALID_API_KEY
        cleanup.assert_called_once_with(staged.call_args.args[0], "api-key")

    def test_secure_cleans_earlier_staged_credentials_on_later_failure(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A failed second write does not leave the first profile's OS entry behind."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "profiles": {
                        "dev": {"server": "https://dev.example.com", "api-key": VALID_API_KEY},
                        "prod": {"server": "https://prod.example.com", "api-key": VALID_API_KEY},
                    }
                }
            )
        )
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        staged = MagicMock(side_effect=[None, CredentialStoreError("locked")])
        cleanup = MagicMock()
        monkeypatch.setattr("slcli.config_click.set_credential", staged)
        monkeypatch.setattr("slcli.credentials.delete_credential", cleanup)

        result = CliRunner().invoke(make_cli(), ["config", "secure", "--all"])

        assert result.exit_code != 0
        assert cleanup.call_count == 2
        assert json.loads(config_file.read_text())["profiles"]["dev"]["api-key"] == VALID_API_KEY

    def test_view_of_os_profile_does_not_read_secret(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Normal config view reports the backend without reading its secret."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "profile-id",
                            "server": "https://dev.example.com",
                            "credential-store": "os",
                        }
                    },
                }
            )
        )
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        read_secret = MagicMock(side_effect=AssertionError("must stay lazy"))
        monkeypatch.setattr("slcli.config_click.get_credential", read_secret)

        result = CliRunner().invoke(make_cli(), ["config", "view"])

        assert result.exit_code == 0, result.output
        assert describe_credential_store("os") in result.output
        read_secret.assert_not_called()


def test_file_to_os_profile_transition_stages_credential_before_metadata_save(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The old file credential remains usable until its OS replacement is written."""
    from slcli.config_click import _add_profile_impl

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "profile-id",
                        "server": "https://old.example.com",
                        "api-key": "old-file-key",
                        "credential-store": "file",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    stored_credentials: list[tuple[str, str, str, str]] = []

    def store_credential(profile_id: str, credential: str, value: str, store: str) -> None:
        stored_credentials.append((profile_id, credential, value, store))
        if store == "os":
            on_disk = json.loads(config_file.read_text())["profiles"]["dev"]
            assert on_disk["credential-store"] == "file"
            assert on_disk["api-key"] == "old-file-key"

    monkeypatch.setattr("slcli.config_click.set_credential", store_credential)

    _add_profile_impl(
        profile="dev",
        url="https://new.example.com",
        api_key=VALID_API_KEY,
        web_url="https://web.example.com",
        workspace="",
        set_current=True,
        readonly=False,
    )

    saved_profile = json.loads(config_file.read_text())["profiles"]["dev"]
    assert stored_credentials == [("profile-id", "api-key", VALID_API_KEY, "os")]
    assert saved_profile["credential-store"] == "os"
    assert "api-key" not in saved_profile


def test_file_to_os_profile_transition_cleans_staged_credential_when_save_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A failed OS-metadata save removes the staged secret and restores the file profile."""
    from slcli.config_click import _add_profile_impl
    from slcli.profiles import ProfileConfig

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "profile-id",
                        "server": "https://old.example.com",
                        "api-key": "old-file-key",
                        "credential-store": "file",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    original_save = ProfileConfig.save
    save_calls = 0

    def fail_first_save(config: ProfileConfig) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 1:
            raise RuntimeError("config is read-only")
        original_save(config)

    monkeypatch.setattr(ProfileConfig, "save", fail_first_save)
    store_credential = MagicMock()
    delete_credential = MagicMock()
    monkeypatch.setattr("slcli.config_click.set_credential", store_credential)
    monkeypatch.setattr("slcli.credentials.delete_credential", delete_credential)

    with pytest.raises(SystemExit) as exc_info:
        _add_profile_impl(
            profile="dev",
            url="https://new.example.com",
            api_key=VALID_API_KEY,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
        )

    saved_profile = json.loads(config_file.read_text())["profiles"]["dev"]
    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    store_credential.assert_called_once_with("profile-id", "api-key", VALID_API_KEY, "os")
    delete_credential.assert_called_once_with("profile-id", "api-key")
    assert saved_profile["server"] == "https://old.example.com"
    assert saved_profile["credential-store"] == "file"
    assert saved_profile["api-key"] == "old-file-key"


def test_os_profile_update_stages_new_id_before_metadata_swap(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The original OS credential stays referenced until its replacement is stored."""
    from slcli.config_click import _add_profile_impl

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "old-id",
                        "server": "https://old.example.com",
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
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    staged_ids: list[str] = []

    def stage(profile_id: str, credential: str, value: str, store: str) -> None:
        assert json.loads(config_file.read_text())["profiles"]["dev"]["id"] == "old-id"
        assert store == "os"
        staged_ids.append(profile_id)

    monkeypatch.setattr("slcli.config_click.set_credential", stage)
    monkeypatch.setattr("slcli.credentials.delete_profile_credentials", MagicMock())

    _add_profile_impl(
        profile="dev",
        url="https://new.example.com",
        api_key=VALID_API_KEY,
        web_url="https://web.example.com",
        workspace="",
        set_current=True,
        readonly=False,
    )

    saved = json.loads(config_file.read_text())
    assert staged_ids == [saved["profiles"]["dev"]["id"]]
    assert staged_ids[0] != "old-id"
    assert "pending-credential-deletions" not in saved


@pytest.mark.parametrize("auth_mode", ["api-key", "pkce"])
def test_add_profile_falls_back_to_file_when_os_write_fails(
    auth_mode: str, tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """API-key and PKCE credentials persist to file after an OS-store failure."""
    from slcli.config_click import _add_profile_impl
    from slcli.credentials import set_credential as real_set_credential

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    writes: list[str] = []
    web_url = "https://web.example.com"
    client_id = None

    def set_credential(profile_id: str, credential: str, value: str, store: str) -> None:
        writes.append(store)
        if store == "os":
            raise CredentialStoreError("OS store unavailable")
        real_set_credential(profile_id, credential, value, store)

    if auth_mode == "api-key":
        monkeypatch.setattr("slcli.config_click.set_credential", set_credential)
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda *_args, **_kwargs: {
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {},
            },
        )
        api_key = VALID_API_KEY
    else:
        from slcli.pkce import PkceLoginResult

        monkeypatch.setattr("slcli.pkce.set_credential", set_credential)
        monkeypatch.setattr(
            "slcli.config_click.check_web_server_auth",
            lambda *_args, **_kwargs: {
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {"Web Server": "ok"},
            },
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status", lambda *_args, **_kwargs: {"platform": "SLE"}
        )
        monkeypatch.setattr(
            "slcli.pkce.perform_pkce_login",
            lambda *_args, **_kwargs: PkceLoginResult("access-token", "refresh-token"),
        )
        api_key = None
        client_id = "client-id"

    _add_profile_impl(
        profile="dev",
        url="https://api.example.com",
        api_key=api_key,
        web_url=web_url,
        workspace="",
        set_current=True,
        readonly=False,
        auth_mode=auth_mode,
        client_id=client_id,
    )

    output = capsys.readouterr()
    saved_profile = json.loads(config_file.read_text())["profiles"]["dev"]
    assert writes == ["os"]
    assert saved_profile["credential-store"] == "file"
    assert "OS credential store unavailable" in output.err
    if auth_mode == "api-key":
        assert saved_profile["api-key"] == VALID_API_KEY
    else:
        assert saved_profile["pkce-credentials"]["access-token"] == "access-token"
        assert saved_profile["pkce-credentials"]["refresh-token"] == "refresh-token"


@pytest.mark.parametrize("previous_store", ["os", "file"])
def test_unexpected_os_write_failure_does_not_fall_back_to_plaintext(
    previous_store: str, tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """A non-store failure leaves the previous profile intact and reports an error."""
    from slcli.config_click import _add_profile_impl

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "dev-id",
                        "server": "https://old.example.com",
                        "credential-store": previous_store,
                        **({"api-key": "old-key"} if previous_store == "file" else {}),
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    monkeypatch.setattr(
        "slcli.config_click.set_credential", MagicMock(side_effect=RuntimeError("unexpected bug"))
    )

    with pytest.raises(SystemExit) as exc_info:
        _add_profile_impl(
            profile="dev",
            url="https://new.example.com",
            api_key=VALID_API_KEY,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
        )

    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    assert "storing this profile in the config file" not in capsys.readouterr().err
    saved = json.loads(config_file.read_text())["profiles"]["dev"]
    assert saved["server"] == "https://old.example.com"
    assert saved["credential-store"] == previous_store


@pytest.mark.parametrize("previous_store", ["os", "file"])
@pytest.mark.parametrize("new_store", ["os", "file"])
def test_pkce_to_api_key_migration_removes_legacy_tokens(
    previous_store: str, new_store: str, tmp_path: Path, monkeypatch: Any
) -> None:
    """Switching auth mode cleans old per-token items for either storage transition."""
    from slcli.config_click import _add_profile_impl
    from slcli.credentials import set_credential as real_set_credential

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "dev-id",
                        "server": "https://old.example.com",
                        "auth-mode": "pkce",
                        "credential-store": previous_store,
                        **(
                            {"pkce-credentials": {"access-token": "old-token"}}
                            if previous_store == "file"
                            else {}
                        ),
                    }
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )

    def store_credential(profile_id: str, credential: str, value: str, store: str) -> None:
        if store == "file":
            real_set_credential(profile_id, credential, value, store)

    monkeypatch.setattr("slcli.config_click.set_credential", store_credential)
    monkeypatch.setattr("slcli.credentials.delete_credential", MagicMock())
    delete_legacy = MagicMock()
    monkeypatch.setattr("slcli.credentials.delete_legacy_pkce_credentials", delete_legacy)

    _add_profile_impl(
        profile="dev",
        url="https://new.example.com",
        api_key=VALID_API_KEY,
        web_url="https://web.example.com",
        workspace="",
        set_current=True,
        readonly=False,
        credential_store=new_store,
    )

    assert json.loads(config_file.read_text())["profiles"]["dev"]["server"] == (
        "https://new.example.com"
    )
    delete_legacy.assert_called_once_with(
        "dev", "file" if previous_store == new_store == "file" else "os"
    )


def test_fallback_save_failure_restores_previous_profile(tmp_path: Path, monkeypatch: Any) -> None:
    """A failed fallback save restores the old profile instead of keeping an unusable OS one."""
    from slcli.config_click import _add_profile_impl
    from slcli.profiles import ProfileConfig

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "old-id",
                        "server": "https://old.example.com",
                        "credential-store": "os",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(ProfileConfig, "get_config_path", classmethod(lambda cls: config_file))
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    monkeypatch.setattr(
        "slcli.config_click.set_credential",
        MagicMock(side_effect=CredentialStoreError("OS store unavailable")),
    )
    original_save = ProfileConfig.save
    save_calls = 0

    def fail_fallback_save(config: ProfileConfig) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 1:
            raise RuntimeError("disk full")
        original_save(config)

    monkeypatch.setattr(ProfileConfig, "save", fail_fallback_save)

    with pytest.raises(SystemExit) as exc_info:
        _add_profile_impl(
            profile="dev",
            url="https://new.example.com",
            api_key=VALID_API_KEY,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
        )

    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    saved = json.loads(config_file.read_text())
    assert saved["profiles"]["dev"]["server"] == "https://old.example.com"
    assert saved["profiles"]["dev"]["credential-store"] == "os"


def test_profile_rollback_save_failure_reports_credential_id(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """A second save failure is reported with recovery details, not a traceback."""
    from slcli.config_click import _add_profile_impl
    from slcli.profiles import ProfileConfig

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "dev",
                "profiles": {
                    "dev": {
                        "id": "existing-id",
                        "server": "https://old.example.com",
                        "credential-store": "os",
                    }
                },
            }
        )
    )
    monkeypatch.setattr(ProfileConfig, "get_config_path", classmethod(lambda cls: config_file))
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    original_save = ProfileConfig.save
    save_calls = 0

    def fail_rollback_save(config: ProfileConfig) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls <= 2:
            raise RuntimeError("disk full")
        original_save(config)

    monkeypatch.setattr(ProfileConfig, "save", fail_rollback_save)

    with pytest.raises(SystemExit) as exc_info:
        _add_profile_impl(
            profile="dev",
            url="https://new.example.com",
            api_key=VALID_API_KEY,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
            credential_store="file",
        )

    assert exc_info.value.code == ExitCodes.GENERAL_ERROR
    output = capsys.readouterr()
    assert "Could not restore previous profile" in output.err
    assert "Credential ID: existing-id" in output.err


def test_file_store_transition_retains_pending_cleanup_when_store_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The file profile stays usable while obsolete OS credentials await cleanup."""
    from slcli.config_click import _add_profile_impl

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "current-profile": "other",
                "profiles": {
                    "dev": {
                        "id": "profile-id",
                        "server": "https://old.example.com",
                        "credential-store": "os",
                    },
                    "other": {
                        "server": "https://other.example.com",
                        "api-key": "other-key",
                    },
                },
            }
        )
    )
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        "slcli.config_click.check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "platform": "unknown",
            "auth_valid": True,
            "services": {},
        },
    )
    deleted: list[str] = []

    def delete_credential(_profile_id: str, credential: str) -> None:
        deleted.append(credential)
        if credential == "api-key":
            raise CredentialStoreError("Keychain locked")

    monkeypatch.setattr("slcli.credentials.delete_credential", delete_credential)
    monkeypatch.setattr("slcli.credentials.delete_legacy_pkce_credentials", MagicMock())

    _add_profile_impl(
        profile="dev",
        url="https://new.example.com",
        api_key=VALID_API_KEY,
        web_url="https://web.example.com",
        workspace="",
        set_current=True,
        readonly=False,
        credential_store="file",
    )

    saved = json.loads(config_file.read_text())
    assert deleted == ["pkce", "api-key"]
    assert saved["current-profile"] == "dev"
    assert saved["profiles"]["dev"]["server"] == "https://new.example.com"
    assert saved["profiles"]["dev"]["credential-store"] == "file"
    assert saved["profiles"]["dev"]["api-key"] == VALID_API_KEY
    assert saved["pending-credential-deletions"][0]["id"] == "profile-id"


class TestTrustedCertificates:
    """Tests for managed certificate trust commands."""

    def test_trust_retry_preserves_bearer_authentication(self, monkeypatch: Any) -> None:
        """PKCE certificate approval retries the Web Server probe with a bearer token."""
        from slcli.config_click import _trust_certificate_if_requested
        from slcli.ssl_trust import ServerCertificate

        certificate = ServerCertificate(
            origin="https://web.example.com:443",
            pem=b"pem",
            fingerprint="A" * 64,
            subject="subject",
            issuer="issuer",
            sans=[],
            not_before="before",
            not_after="after",
            self_signed=True,
        )
        retry_status = {
            "server_reachable": True,
            "auth_valid": True,
            "certificate_error": False,
        }
        mock_check = MagicMock(return_value=retry_status)
        monkeypatch.setattr(
            "slcli.config_click.inspect_server_certificate", lambda _url: certificate
        )
        monkeypatch.setattr("slcli.config_click.save_managed_certificate", lambda _cert: None)
        monkeypatch.setattr("slcli.config_click.check_web_server_auth", mock_check)

        result = _trust_certificate_if_requested(
            "https://web.example.com",
            "access-token",
            {
                "server_reachable": False,
                "certificate_error": True,
                "certificate": certificate.to_dict(),
            },
            certificate.fingerprint,
            auth_scheme="bearer",
        )

        assert result == retry_status
        mock_check.assert_called_once_with(
            "https://web.example.com", "access-token", auth_scheme="bearer"
        )

    def test_reachable_server_skips_certificate_trust_flow(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A partial probe certificate error should not block a reachable profile."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda _url, _api_key: {
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {"Auth": "ok", "Files": "certificate_error"},
                "certificate_error": True,
            },
        )

        def fail_if_trust_flow_runs(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("certificate trust flow should not run for a reachable server")

        monkeypatch.setattr(
            "slcli.config_click._trust_certificate_if_requested", fail_if_trust_flow_runs
        )

        result = CliRunner().invoke(
            make_cli(),
            [
                "config",
                "add",
                "--profile",
                "reachable",
                "--url",
                "https://example.com",
                "--api-key",
                VALID_API_KEY,
                "--web-url",
                "https://web.example.com",
            ],
            input="\n",
        )

        assert result.exit_code == 0, result.output
        assert config_file.exists()

    def test_list_trusted_certificates_json(self, monkeypatch: Any) -> None:
        """Trust list should expose certificate metadata as JSON."""
        monkeypatch.setattr(
            "slcli.config_click.get_managed_trust_records",
            lambda: [{"origin": "https://example.com:443", "fingerprint": "A" * 64}],
        )

        result = CliRunner().invoke(make_cli(), ["config", "trust", "list", "--format", "json"])

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)[0]["fingerprint"] == "A" * 64

    def test_show_server_certificate_json(self, monkeypatch: Any) -> None:
        """Trust show should inspect and expose the current certificate as JSON."""
        from slcli.ssl_trust import ServerCertificate

        certificate = ServerCertificate(
            origin="https://example.com:443",
            pem=b"pem",
            fingerprint="A" * 64,
            subject="subject",
            issuer="issuer",
            sans=["example.com"],
            not_before="before",
            not_after="after",
            self_signed=True,
        )
        inspect = MagicMock(return_value=certificate)
        monkeypatch.setattr("slcli.config_click.inspect_server_certificate", inspect)

        result = CliRunner().invoke(
            make_cli(),
            ["config", "trust", "show", "--url", "https://example.com", "-f", "json"],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["fingerprint"] == "A" * 64
        inspect.assert_called_once_with("https://example.com")

    def test_show_server_certificate_table_uses_active_url_without_saving(
        self, monkeypatch: Any
    ) -> None:
        """Trust show should use the active API URL and leave managed trust unchanged."""
        from slcli.ssl_trust import ServerCertificate
        from slcli.utils import ResolvedConfigValue

        certificate = ServerCertificate(
            origin="https://active.example.com:443",
            pem=b"pem",
            fingerprint="B" * 64,
            subject="subject",
            issuer="issuer",
            sans=[],
            not_before="before",
            not_after="after",
            self_signed=False,
        )
        inspect = MagicMock(return_value=certificate)
        save = MagicMock()
        monkeypatch.setattr(
            "slcli.config_click.get_base_url",
            lambda: "https://active-web.example.com",
        )
        monkeypatch.setattr(
            "slcli.config_click.get_base_url_resolution",
            lambda: ResolvedConfigValue("https://active-api.example.com", "profile:active"),
        )
        monkeypatch.setattr("slcli.config_click.inspect_server_certificate", inspect)
        monkeypatch.setattr("slcli.config_click.save_managed_certificate", save)

        result = CliRunner().invoke(make_cli(), ["config", "trust", "show"])

        assert result.exit_code == 0, result.output
        assert "SHA-256: " + "B" * 64 in result.output
        inspect.assert_called_once_with("https://active-api.example.com")
        save.assert_not_called()

    def test_show_server_certificate_reports_inspection_failure(self, monkeypatch: Any) -> None:
        """Trust show should report network failures without changing trust state."""
        monkeypatch.setattr(
            "slcli.config_click.inspect_server_certificate",
            MagicMock(side_effect=OSError("connection failed")),
        )

        result = CliRunner().invoke(
            make_cli(), ["config", "trust", "show", "--url", "https://example.com"]
        )

        assert result.exit_code == ExitCodes.NETWORK_ERROR
        assert "Could not inspect the server certificate" in result.output

    def test_add_trusted_certificate_rejects_fingerprint_mismatch(self, monkeypatch: Any) -> None:
        """Trust add must reject a certificate that differs from the supplied fingerprint."""
        from slcli.ssl_trust import ServerCertificate

        certificate = ServerCertificate(
            origin="https://example.com:443",
            pem=b"pem",
            fingerprint="B" * 64,
            subject="subject",
            issuer="issuer",
            sans=[],
            not_before="before",
            not_after="after",
            self_signed=True,
        )
        monkeypatch.setattr(
            "slcli.config_click.inspect_server_certificate", lambda _url: certificate
        )
        saved_certificates: list[ServerCertificate] = []
        monkeypatch.setattr(
            "slcli.config_click.save_managed_certificate",
            lambda certificate_to_save: saved_certificates.append(certificate_to_save),
        )

        result = CliRunner().invoke(
            make_cli(),
            ["config", "trust", "add", "--url", "https://example.com", "--fingerprint", "C" * 64],
        )

        assert result.exit_code != 0
        assert "does not match" in result.output
        assert saved_certificates == []


class TestDeleteProfile:
    """Tests for the delete command."""

    def test_delete_file_pkce_profile_removes_legacy_tokens(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Deleting a file-backed PKCE profile also removes its old OS token items."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "dev-id",
                            "server": "https://example.com",
                            "auth-mode": "pkce",
                            "credential-store": "file",
                            "pkce-credentials": {"access-token": "token"},
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

        result = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])

        assert result.exit_code == 0
        cleanup.assert_called_once_with("dev-id", "file", "dev", "pkce")
        assert "dev" not in json.loads(config_file.read_text()).get("profiles", {})

    def test_delete_file_api_key_profile_removes_legacy_tokens(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Old PKCE tokens are removed even after switching to file-backed API keys."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "dev-id",
                            "server": "https://example.com",
                            "auth-mode": "api-key",
                            "credential-store": "file",
                            "api-key": VALID_API_KEY,
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

        result = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])

        assert result.exit_code == 0
        cleanup.assert_called_once_with("dev-id", "file", "dev", "api-key")

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

    def test_delete_profile_keeps_pending_record_when_cleanup_fails(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A failed credential cleanup leaves a persisted retry record."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "profile-id",
                            "server": "https://dev.example.com",
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

        result = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])

        assert result.exit_code == ExitCodes.GENERAL_ERROR
        assert "Deletion is pending" in result.output
        saved = json.loads(config_file.read_text())
        assert "dev" not in saved.get("profiles", {})
        assert saved["pending-credential-deletions"] == [
            {"id": "profile-id", "name": "dev", "store": "os", "auth-mode": "api-key"}
        ]

    def test_delete_profile_does_not_clean_credentials_when_save_fails(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """A failed profile-removal save must leave credentials untouched."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "profile-id",
                            "server": "https://dev.example.com",
                            "credential-store": "os",
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

        def fail_save(_config: Any) -> None:
            raise RuntimeError("config is read-only")

        monkeypatch.setattr("slcli.profiles.ProfileConfig.save", fail_save)

        result = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])

        assert result.exit_code != 0
        assert "Credentials were not removed" in result.output
        cleanup.assert_not_called()
        assert "dev" in json.loads(config_file.read_text())["profiles"]

    def test_delete_profile_retries_pending_removal(self, tmp_path: Path, monkeypatch: Any) -> None:
        """A later delete finishes the same persisted credential cleanup."""
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "dev",
                    "profiles": {
                        "dev": {
                            "id": "profile-id",
                            "server": "https://dev.example.com",
                            "credential-store": "os",
                        }
                    },
                }
            )
        )
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        cleanup = MagicMock(side_effect=[CredentialStoreError("store locked"), None])
        monkeypatch.setattr("slcli.credentials.delete_profile_credentials", cleanup)

        first = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])
        assert first.exit_code == ExitCodes.GENERAL_ERROR
        assert (
            json.loads(config_file.read_text())["pending-credential-deletions"][0]["id"]
            == "profile-id"
        )

        result = CliRunner().invoke(make_cli(), ["config", "delete", "dev", "--force"])

        assert result.exit_code == 0
        assert "pending-credential-deletions" not in json.loads(config_file.read_text())
        assert cleanup.call_count == 2

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
        monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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
        monkeypatch.setattr("slcli.config_click.set_credential", lambda *a, **kw: None)

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


class TestPkceProfileVerification:
    """Tests for PKCE verification against Web Server routes."""

    def test_pkce_trusts_web_certificate_before_browser_login(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """PKCE must establish Web UI trust before exchanging the browser code."""
        from slcli.config_click import _add_profile_impl
        from slcli.pkce import PkceLoginResult

        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        events: list[str] = []

        def mock_web_probe(
            url: str, credential: str, auth_scheme: str = "bearer"
        ) -> dict[str, Any]:
            events.append(f"probe:{credential}")
            if not credential:
                return {
                    "server_reachable": False,
                    "certificate_error": True,
                    "certificate": {"fingerprint": "AA"},
                    "platform": "unknown",
                    "services": {"Web Server": "certificate_error"},
                }
            return {
                "server_reachable": True,
                "auth_valid": True,
                "services": {"Web Server": "ok"},
                "platform": "unknown",
            }

        monkeypatch.setattr("slcli.config_click.check_web_server_auth", mock_web_probe)

        def trust_certificate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            events.append("trust")
            return mock_web_probe(args[0], "trusted")

        def perform_login(*args: Any, **kwargs: Any) -> PkceLoginResult:
            events.append("login")
            return PkceLoginResult("access-token", "refresh-token")

        monkeypatch.setattr("slcli.config_click._trust_certificate_if_requested", trust_certificate)
        monkeypatch.setattr("slcli.pkce.perform_pkce_login", perform_login)
        monkeypatch.setattr("slcli.pkce.save_pkce_credentials", lambda *args: None)
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda *_args, **_kwargs: {"platform": "SLE"},
        )

        _add_profile_impl(
            profile="pkce",
            url="https://api.example.com",
            api_key=None,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
            trust_fingerprint="AA",
            auth_mode="pkce",
            client_id="client-id",
        )

        assert events == ["probe:", "trust", "probe:trusted", "login", "probe:access-token"]

    def test_pkce_login_uses_web_server_identity_probe(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """PKCE login must not probe the separate API host during the prototype."""
        from slcli.config_click import _add_profile_impl
        from slcli.pkce import PkceLoginResult

        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.pkce.perform_pkce_login",
            lambda _web_url, _client_id, _scopes: PkceLoginResult(
                access_token="access-token", refresh_token="refresh-token"
            ),
        )
        mock_web_probe = MagicMock(
            return_value={
                "server_reachable": True,
                "platform": "unknown",
                "auth_valid": True,
                "services": {"Web Server": "ok"},
            }
        )
        monkeypatch.setattr("slcli.config_click.check_web_server_auth", mock_web_probe)
        mock_service_probe = MagicMock(return_value={"platform": "SLE"})
        monkeypatch.setattr("slcli.config_click.check_service_status", mock_service_probe)
        monkeypatch.setattr("slcli.pkce.save_pkce_credentials", lambda *args: None)

        _add_profile_impl(
            profile="pkce",
            url="https://api.example.com",
            api_key=None,
            web_url="https://web.example.com",
            workspace="",
            set_current=True,
            readonly=False,
            auth_mode="pkce",
            client_id="client-id",
        )

        assert mock_web_probe.call_args_list[0] == (
            ("https://web.example.com", ""),
            {"auth_scheme": "bearer"},
        )
        assert mock_web_probe.call_args_list[-1] == (
            ("https://web.example.com", "access-token"),
            {"auth_scheme": "bearer"},
        )
        mock_service_probe.assert_called_once_with(
            "https://web.example.com", "access-token", auth_scheme="bearer"
        )
        saved = json.loads(config_file.read_text())
        assert saved["profiles"]["pkce"]["server"] == "https://api.example.com"
        assert saved["profiles"]["pkce"]["platform"] == "SLE"

    def test_pkce_credential_failure_restores_existing_profile(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """Failed PKCE credential storage restores the profile and current selection."""
        from slcli.config_click import _add_profile_impl
        from slcli.pkce import PkceLoginResult

        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "current-profile": "other",
                    "profiles": {
                        "pkce": {
                            "server": "https://old-api.example.com",
                            "api-key": "old-api-key",
                            "web-url": "https://old-web.example.com",
                        },
                        "other": {
                            "server": "https://other-api.example.com",
                            "api-key": "other-api-key",
                        },
                    },
                }
            )
        )
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.check_web_server_auth",
            lambda *_args, **_kwargs: {
                "server_reachable": True,
                "auth_valid": True,
                "services": {"Web Server": "ok"},
                "platform": "unknown",
            },
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda *_args, **_kwargs: {"platform": "unknown"},
        )
        monkeypatch.setattr(
            "slcli.pkce.perform_pkce_login",
            lambda *_args, **_kwargs: PkceLoginResult("new-access-token", "new-refresh-token"),
        )

        def fail_to_save_credentials(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("keyring unavailable")

        monkeypatch.setattr("slcli.pkce.save_pkce_credentials", fail_to_save_credentials)

        with pytest.raises(SystemExit) as exc_info:
            _add_profile_impl(
                profile="pkce",
                url="https://new-api.example.com",
                api_key=None,
                web_url="https://new-web.example.com",
                workspace="",
                set_current=True,
                readonly=False,
                auth_mode="pkce",
                client_id="client-id",
            )

        assert exc_info.value.code == ExitCodes.GENERAL_ERROR
        saved = json.loads(config_file.read_text())
        assert saved["current-profile"] == "other"
        assert saved["profiles"]["pkce"]["server"] == "https://old-api.example.com"
        assert saved["profiles"]["pkce"]["api-key"] == "old-api-key"


class TestSlsProfileVerification:
    """Tests for SLS-specific API-key verification."""

    def test_rejects_mixed_unauthorized_and_not_found_services(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        """SLS verification rejects a key when no service accepts it."""
        from slcli.config_click import _add_profile_impl

        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        monkeypatch.setattr(
            "slcli.config_click.check_service_status",
            lambda *_args, **_kwargs: {
                "server_reachable": True,
                "auth_valid": False,
                "services": {"Auth": "unauthorized", "Comments": "not_found"},
                "platform": PLATFORM_SLS,
            },
        )

        with pytest.raises(SystemExit) as exc_info:
            _add_profile_impl(
                profile="sls",
                url="https://api.example.com",
                api_key=VALID_API_KEY,
                web_url="https://web.example.com",
                workspace="",
                set_current=True,
                readonly=False,
            )

        assert exc_info.value.code == ExitCodes.PERMISSION_DENIED
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

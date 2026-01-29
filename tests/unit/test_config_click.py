"""Unit tests for the config_click CLI commands."""

import json
from pathlib import Path
from typing import Any, Dict

import click
from click.testing import CliRunner

from slcli.config_click import register_config_commands


def make_cli() -> click.Group:
    """Create a test CLI with config commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_config_commands(test_cli)
    return test_cli


class TestListProfiles:
    """Tests for the list-profiles command."""

    def test_list_profiles_empty(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test listing profiles when none exist."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "list-profiles"])

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
        result = runner.invoke(cli, ["config", "list-profiles"])

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
        result = runner.invoke(cli, ["config", "list-profiles", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 1
        assert output[0]["name"] == "test"
        assert output[0]["server"] == "https://test.example.com"


class TestCurrentProfile:
    """Tests for the current-profile command."""

    def test_current_profile_none(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test showing current profile when none is set."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        cli = make_cli()
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "current-profile"])

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
        result = runner.invoke(cli, ["config", "current-profile"])

        assert result.exit_code == 0
        assert "myprofile" in result.output


class TestUseProfile:
    """Tests for the use-profile command."""

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
        result = runner.invoke(cli, ["config", "use-profile", "new"])

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
        result = runner.invoke(cli, ["config", "use-profile", "nonexistent"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()


class TestViewConfig:
    """Tests for the view command."""

    def test_view_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test viewing the full config."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {"server": "https://test.com", "api-key": "secret"},
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
        # Should show profile info
        assert "test" in result.output
        # Note: view command doesn't mask API keys by default
        # It shows profile name and server


class TestDeleteProfile:
    """Tests for the delete-profile command."""

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
        result = runner.invoke(cli, ["config", "delete-profile", "todelete", "--force"])

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
        result = runner.invoke(cli, ["config", "delete-profile", "nonexistent", "--force"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

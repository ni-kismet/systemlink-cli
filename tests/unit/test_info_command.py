"""Unit tests for slcli info command."""

import json
from typing import Any
from unittest.mock import patch

from click.testing import CliRunner

from slcli.main import cli
from slcli.profiles import Profile


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_command_table_format_sle(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLE platform."""
        test_profile = Profile(
            name="test",
            server="https://demo-api.lifecyclesolutions.ni.com",
            api_key="test-key",
            web_url="https://demo.lifecyclesolutions.ni.com",
            platform="SLE",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://demo-api.lifecyclesolutions.ni.com"
            mock_web_url.return_value = "https://demo.lifecyclesolutions.ni.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "SystemLink CLI Info" in result.output
        assert "Connected" in result.output
        assert "SystemLink Enterprise" in result.output
        assert "Dynamic Form Fields" in result.output
        assert "Available" in result.output

    def test_info_command_table_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "SystemLink CLI Info" in result.output
        assert "Connected" in result.output
        assert "SystemLink Server" in result.output
        assert "Dynamic Form Fields" in result.output
        assert "Not available" in result.output

    def test_info_command_json_format_sle(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLE platform."""
        test_profile = Profile(
            name="test",
            server="https://demo-api.lifecyclesolutions.ni.com",
            api_key="test-key",
            web_url="https://demo.lifecyclesolutions.ni.com",
            platform="SLE",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://demo-api.lifecyclesolutions.ni.com"
            mock_web_url.return_value = "https://demo.lifecyclesolutions.ni.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLE"
        assert output["logged_in"] is True
        assert output["features"]["Dynamic Form Fields"] is True

    def test_info_command_json_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "-f", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLS"
        assert output["logged_in"] is True
        assert output["features"]["Dynamic Form Fields"] is False

    def test_info_command_not_logged_in(self, monkeypatch: Any) -> None:
        """Test info command when not logged in."""
        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform._get_keyring_config"
        ) as mock_keyring:
            mock_profile.return_value = None
            mock_base_url.side_effect = Exception("Not configured")
            mock_web_url.side_effect = Exception("Not configured")
            mock_api_key.side_effect = Exception("Not configured")
            mock_keyring.return_value = {}

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Not logged in" in result.output
        assert "Unknown" in result.output

"""Unit tests for slcli info command."""

import json
from typing import Any

from click.testing import CliRunner

from slcli.main import cli


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_command_table_format_sle(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLE platform."""
        config = {
            "api_url": "https://demo-api.lifecyclesolutions.ni.com",
            "web_url": "https://demo.lifecyclesolutions.ni.com",
            "api_key": "test-key",
            "platform": "SLE",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

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
        config = {
            "api_url": "https://my-server.local",
            "web_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

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
        config = {
            "api_url": "https://demo-api.lifecyclesolutions.ni.com",
            "web_url": "https://demo.lifecyclesolutions.ni.com",
            "api_key": "test-key",
            "platform": "SLE",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        result = runner.invoke(cli, ["info", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLE"
        assert output["logged_in"] is True
        assert output["features"]["Dynamic Form Fields"] is True

    def test_info_command_json_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "web_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        result = runner.invoke(cli, ["info", "-f", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["platform"] == "SLS"
        assert output["logged_in"] is True
        assert output["features"]["Dynamic Form Fields"] is False

    def test_info_command_not_logged_in(self, monkeypatch: Any) -> None:
        """Test info command when not logged in."""

        def mock_get_password(service: str, key: str) -> None:
            return None

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Not logged in" in result.output
        assert "Unknown" in result.output

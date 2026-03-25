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
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "Test Monitor": "ok", "Work Order": "ok"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
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
        assert "Service Health" in result.output
        assert "Auth" in result.output
        assert "OK" in result.output

    def test_info_command_table_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with table format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "Work Order": "not_found",
            },
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
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
        assert "Service Health" in result.output
        assert "Work Order" in result.output
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
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "Test Monitor": "ok", "Work Order": "ok"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
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
        assert output["services"]["Auth"] == "ok"

    def test_info_command_json_format_sls(self, monkeypatch: Any) -> None:
        """Test info command with JSON format for SLS platform."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "Work Order": "not_found",
            },
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
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
        assert "features" not in output

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

    def test_info_command_server_unreachable(self, monkeypatch: Any) -> None:
        """Test info command shows unreachable when server cannot be contacted."""
        test_profile = Profile(
            name="test",
            server="https://offline.example.com",
            api_key="test-key",
            web_url="https://offline.example.com",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": False,
            "auth_valid": None,
            "services": {"Auth": "unreachable", "Test Monitor": "unreachable"},
            "platform": "unreachable",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://offline.example.com"
            mock_web_url.return_value = "https://offline.example.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "Server unreachable" in result.output

    def test_info_command_api_key_unauthorized(self, monkeypatch: Any) -> None:
        """Test info command shows unauthorized when API key is invalid."""
        test_profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="bad-key",
            web_url="https://example.com",
            platform="SLE",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": False,
            "services": {"Auth": "unauthorized", "Test Monitor": "unauthorized"},
            "platform": "SLE",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "bad-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "API key unauthorized" in result.output
        assert "Unauthorized" in result.output

    def test_info_command_skip_health(self, monkeypatch: Any) -> None:
        """Test info command with --skip-health skips service checks."""
        test_profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="test-key",
            web_url="https://example.com",
            platform="SLE",
        )

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status"
        ) as mock_check:
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://api.example.com"
            mock_web_url.return_value = "https://example.com"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--skip-health"])

        assert result.exit_code == 0
        assert "SystemLink Enterprise" in result.output
        assert "Service Health" not in result.output
        mock_check.assert_not_called()

    def test_info_command_reports_file_query_fallback(self, monkeypatch: Any) -> None:
        """Test info command shows query-files-linq when Elasticsearch is unavailable."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "File": "fallback",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files-linq",
            "elasticsearch_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info"])

        assert result.exit_code == 0
        assert "query-files-linq" in result.output
        assert "Elasticsearch unavailable" in result.output
        assert "Fallback (no Elasticsearch)" in result.output

    def test_info_command_json_reports_file_query_fallback(self, monkeypatch: Any) -> None:
        """Test info JSON includes file query capability details."""
        test_profile = Profile(
            name="test",
            server="https://my-server.local",
            api_key="test-key",
            web_url="https://my-server.local",
            platform="SLS",
        )
        mock_status = {
            "server_reachable": True,
            "auth_valid": True,
            "services": {
                "Auth": "ok",
                "Test Monitor": "ok",
                "File": "fallback",
                "Work Order": "not_found",
            },
            "file_query_endpoint": "query-files-linq",
            "elasticsearch_available": False,
            "platform": "SLS",
        }

        with patch("slcli.profiles.get_active_profile") as mock_profile, patch(
            "slcli.utils.get_base_url"
        ) as mock_base_url, patch("slcli.utils.get_web_url") as mock_web_url, patch(
            "slcli.utils.get_api_key"
        ) as mock_api_key, patch(
            "slcli.platform.check_service_status", return_value=mock_status
        ):
            mock_profile.return_value = test_profile
            mock_base_url.return_value = "https://my-server.local"
            mock_web_url.return_value = "https://my-server.local"
            mock_api_key.return_value = "test-key"

            runner = CliRunner()
            result = runner.invoke(cli, ["info", "--format", "json"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["file_query_endpoint"] == "query-files-linq"
        assert output["elasticsearch_available"] is False
        assert output["services"]["File"] == "fallback"

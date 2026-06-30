"""Unit tests for platform feature gating on CLI commands."""

import json
from typing import Any

import pytest
from click.testing import CliRunner

from slcli.main import cli
from slcli.platform import clear_platform_cache


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear the platform cache before each test."""
    clear_platform_cache()


class TestFeatureGatingDFF:
    """Tests for feature gating on DFF commands."""

    def test_dff_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that DFF commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        result = runner.invoke(cli, ["customfield", "list"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Dynamic Form Fields is not available on SystemLink Server" in result.output
        assert "requires SystemLink Enterprise" in result.output

    def test_dff_help_not_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that DFF --help is not blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        result = runner.invoke(cli, ["customfield", "--help"])

        assert result.exit_code == 0
        assert "Manage SystemLink custom field configurations" in result.output


class TestFeatureGatingTemplates:
    """Tests for feature gating on template commands."""

    def test_template_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that template commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")

        runner = CliRunner()
        result = runner.invoke(cli, ["template", "list"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Test Plan Templates is not available on SystemLink Server" in result.output


class TestFeatureGatingWorkflows:
    """Tests for feature gating on workflow commands."""

    def test_workflow_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that workflow commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")

        runner = CliRunner()
        result = runner.invoke(cli, ["workitem", "workflow", "list"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Workflows is not available on SystemLink Server" in result.output


class TestFeatureGatingWorkitemTemplates:
    """Tests for feature gating on workitem template commands."""

    def test_workitem_template_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that workitem template commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")

        runner = CliRunner()
        result = runner.invoke(cli, ["workitem", "template", "list"])

        assert result.exit_code == 2
        assert "Test Plan Templates is not available on SystemLink Server" in result.output


class TestFeatureGatingComments:
    """Tests for feature gating on comment commands."""

    def test_comment_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that comment commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")

        runner = CliRunner()
        result = runner.invoke(cli, ["comment", "list"])

        assert result.exit_code == 2
        assert "Comments is not available on SystemLink Server" in result.output
        assert "requires the Comments service" in result.output


class TestFeatureGatingDataFrame:
    """Tests for feature gating on dataframe commands."""

    def test_dataframe_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that dataframe commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")

        runner = CliRunner()
        result = runner.invoke(cli, ["dataframe", "list"])

        assert result.exit_code == 2
        assert "DataFrames is not available on SystemLink Server" in result.output
        assert "requires the DataFrame service" in result.output


class TestFeatureGatingRuntimePlatformDisplay:
    """Tests for live platform display in feature gating messages."""

    def test_template_command_uses_runtime_platform_display(self, monkeypatch: Any) -> None:
        """Test unavailable feature messages avoid 'unknown' when SLS is detectable."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.platform._get_service_status", lambda _service: "not_found")
        monkeypatch.setattr(
            "slcli.platform.check_service_status",
            lambda api_url, api_key: {"platform": "SLS"},
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["template", "list"])

        assert result.exit_code == 2
        assert "SystemLink Server" in result.output
        assert "unknown" not in result.output.lower()


class TestFeatureGatingFunctions:
    """Tests for feature gating on function commands (hidden)."""

    def test_function_command_blocked_on_sls(self, monkeypatch: Any) -> None:
        """Test that function commands are blocked on SLS platform."""
        config = {
            "api_url": "https://my-server.local",
            "api_key": "test-key",
            "platform": "SLS",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)

        runner = CliRunner()
        # Use 'init' command which exists
        result = runner.invoke(cli, ["function", "init"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Function Execution is not available on SystemLink Server" in result.output


class TestFeatureGatingSLE:
    """Tests that features work on SLE platform."""

    def test_dff_command_allowed_on_sle(self, monkeypatch: Any) -> None:
        """Test that DFF commands proceed on SLE platform (may fail for other reasons)."""
        config = {
            "api_url": "https://demo-api.lifecyclesolutions.ni.com",
            "api_key": "test-key",
            "platform": "SLE",
        }

        def mock_get_password(service: str, key: str) -> str:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps(config)
            return ""

        monkeypatch.setattr("slcli.platform.keyring.get_password", mock_get_password)
        monkeypatch.setattr("slcli.utils.keyring.get_password", mock_get_password)

        # Mock the API request to avoid actual network call
        def mock_make_api_request(*args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def json(self) -> dict:
                    return {"configurations": []}

            return MockResponse()

        monkeypatch.setattr("slcli.dff_click.make_api_request", mock_make_api_request)
        monkeypatch.setattr("slcli.utils.make_api_request", mock_make_api_request)

        runner = CliRunner()
        result = runner.invoke(cli, ["customfield", "config", "list", "--format", "json"])

        # Should not be blocked by feature gating (exit code 2)
        # It may fail for other reasons, but not due to platform gating
        assert "is not available on" not in result.output

"""Unit tests for workspace CLI commands."""

import json

import click
import pytest
from click.testing import CliRunner

from slcli.workspace_click import register_workspace_commands


def patch_keyring(monkeypatch):
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def make_cli():
    """Create CLI instance with workspace commands for testing."""

    @click.group()
    def test_cli():
        pass

    register_workspace_commands(test_cli)
    return test_cli


@pytest.fixture
def runner():
    return CliRunner()


def mock_requests(monkeypatch, method, response_json, status_code=200):
    """Mock requests module for testing."""

    class MockResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return response_json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("HTTP error")

    monkeypatch.setattr("requests." + method, lambda *a, **kw: MockResponse())


def test_list_workspaces_success(monkeypatch, runner):
    """Test listing workspaces with a successful response."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Workspace 1",
                            "enabled": True,
                            "default": True,
                        },
                        {
                            "id": "ws2",
                            "name": "Workspace 2",
                            "enabled": False,
                            "default": False,
                        },
                    ]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list"])
    assert result.exit_code == 0
    assert "Workspace 1" in result.output
    assert "Workspace 2" not in result.output  # Disabled workspace filtered out


def test_list_workspaces_include_disabled(monkeypatch, runner):
    """Test listing workspaces including disabled ones."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Workspace 1",
                            "enabled": True,
                            "default": True,
                        },
                        {
                            "id": "ws2",
                            "name": "Workspace 2",
                            "enabled": False,
                            "default": False,
                        },
                    ]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list", "--include-disabled"])
    assert result.exit_code == 0
    assert "Workspace 1" in result.output
    assert "Workspace 2" in result.output  # Disabled workspace included


def test_list_workspaces_json_format(monkeypatch, runner):
    """Test listing workspaces with JSON output."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Workspace 1",
                            "enabled": True,
                            "default": True,
                        }
                    ]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list", "--format", "json"])
    assert result.exit_code == 0

    # Parse JSON output
    output_data = json.loads(result.output)
    assert len(output_data) == 1
    assert output_data[0]["name"] == "Workspace 1"


def test_list_workspaces_empty(monkeypatch, runner):
    """Test listing workspaces when none exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list"])
    assert result.exit_code == 0
    assert "No workspaces found." in result.output


def test_disable_workspace_success(monkeypatch, runner):
    """Test disabling a workspace successfully."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {"id": "test-ws-id", "name": "Test Workspace", "enabled": True},
                        {"id": "other-ws", "name": "Other Workspace", "enabled": True},
                    ]
                }

        return R()

    def mock_put(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "test-ws-id", "name": "Test Workspace", "enabled": False}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "disable", "--id", "test-ws-id"], input="y\n")
    assert result.exit_code == 0
    assert "Workspace 'Test Workspace' disabled successfully" in result.output


def test_disable_workspace_not_found(monkeypatch, runner):
    """Test disabling a workspace that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "disable", "--id", "nonexistent-id"], input="y\n")
    assert result.exit_code == 3  # NOT_FOUND exit code
    assert "Workspace with ID 'nonexistent-id' not found" in result.output


def test_disable_workspace_already_disabled(monkeypatch, runner):
    """Test disabling a workspace that is already disabled."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {"id": "test-ws-id", "name": "Test Workspace", "enabled": False},
                    ]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "disable", "--id", "test-ws-id"], input="y\n")
    assert result.exit_code == 1  # GENERAL_ERROR exit code
    assert "Workspace 'Test Workspace' is already disabled" in result.output


def test_get_workspace_success(monkeypatch, runner):
    """Test getting workspace details successfully."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {
                            "id": "test-ws-id",
                            "name": "Test Workspace",
                            "enabled": True,
                            "default": False,
                        },
                    ]
                }

        return R()

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                if "testplan-templates" in str(a):
                    return {"testPlanTemplates": [{"id": "template-1", "name": "Test Template"}]}
                elif "workflows" in str(a):
                    return {
                        "workflows": [
                            {"id": "workflow-1", "name": "Test Workflow", "workspace": "test-ws-id"}
                        ]
                    }
                else:
                    return {"notebooks": [{"id": "notebook-1", "name": "Test Notebook"}]}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "get", "--id", "test-ws-id"])
    assert result.exit_code == 0
    assert "Workspace Information: Test Workspace" in result.output
    assert "Test Plan Templates (1)" in result.output
    assert "Workflows (1)" in result.output


def test_get_workspace_not_found(monkeypatch, runner):
    """Test getting details for workspace that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "get", "--name", "nonexistent"])
    assert result.exit_code == 3  # NOT_FOUND exit code
    assert "Workspace 'nonexistent' not found" in result.output


def test_get_workspace_with_permission_errors(monkeypatch, runner):
    """Test getting workspace info when some resources have permission errors."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workspaces": [
                        {
                            "id": "test-ws-id",
                            "name": "Test Workspace",
                            "enabled": True,
                            "default": False,
                        },
                    ]
                }

        return R()

    def mock_post(*a, **kw):
        if "testplan-templates" in str(a):
            # Simulate permission error for templates
            raise Exception("401 Unauthorized")
        elif "workflows" in str(a):
            # Return successful response for workflows
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "workflows": [
                            {"id": "workflow-1", "name": "Test Workflow", "workspace": "test-ws-id"}
                        ]
                    }

            return R()
        else:
            # Simulate permission error for notebooks
            raise Exception("403 Forbidden")

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()

    # Test table format shows error messages
    result = runner.invoke(cli, ["workspace", "get", "--id", "test-ws-id"])
    assert result.exit_code == 0
    assert "Workspace Information: Test Workspace" in result.output
    assert "Test Plan Templates (0)" in result.output
    assert "Access denied (insufficient permissions)" in result.output
    assert "Workflows (1)" in result.output
    assert "Test Workflow" in result.output
    assert "Notebooks (0)" in result.output
    assert "Access forbidden" in result.output

    # Test JSON format includes access_errors
    result = runner.invoke(cli, ["workspace", "get", "--id", "test-ws-id", "--format", "json"])
    assert result.exit_code == 0
    import json

    output_data = json.loads(result.output)
    assert "access_errors" in output_data
    assert output_data["access_errors"]["templates"] == "Access denied (insufficient permissions)"
    assert output_data["access_errors"]["notebooks"] == "Access forbidden"
    assert "workflows" not in output_data["access_errors"]  # Should not have workflow errors

import json

import click
import pytest
from click.testing import CliRunner

from slcli.workflows_click import register_workflows_commands
from .test_utils import patch_keyring


def make_cli():
    """Create a dummy CLI for testing."""

    @click.group()
    def cli():
        pass

    register_workflows_commands(cli)
    return cli


@pytest.fixture
def runner():
    return CliRunner()


def mock_requests(monkeypatch, method, response_json, status_code=200):
    class MockResponse:
        def __init__(self):
            self.status_code = status_code

        def json(self):
            return response_json

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception("HTTP error")

    monkeypatch.setattr("requests." + method, lambda *a, **kw: MockResponse())


def test_list_workflows_success(monkeypatch, runner):
    """Test listing workflows with a successful response."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workflows": [
                        {
                            "id": "wf123",
                            "name": "Test Workflow",
                            "description": "Test workflow description",
                            "workspace": "ws456",
                        }
                    ]
                }

        return R()

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": [{"id": "ws456", "name": "Test Workspace"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workflows", "list"])
    assert result.exit_code == 0
    assert "Test Workflow" in result.output
    assert "Test Workspace" in result.output


def test_list_workflows_with_workspace_filter(monkeypatch, runner):
    """Test listing workflows with workspace filter."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "workflows": [
                        {
                            "id": "wf123",
                            "name": "Test Workflow",
                            "description": "Test workflow description",
                            "workspace": "ws456",
                        }
                    ]
                }

        return R()

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": [{"id": "ws456", "name": "Test Workspace"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workflows", "list", "--workspace", "Test"])
    assert result.exit_code == 0
    assert "Test Workflow" in result.output


def test_list_workflows_empty(monkeypatch, runner):
    """Test listing workflows with no results."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workflows": []}

        return R()

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workflows", "list"])
    assert result.exit_code == 0
    assert "No workflows found" in result.output


def test_export_workflow_success(monkeypatch, runner):
    """Test exporting a workflow successfully."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "id": "wf123",
                    "name": "Test Workflow",
                    "description": "Test workflow description",
                    "definition": {"states": []},
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["workflows", "export", "--id", "wf123", "--output", "test.json"]
        )
        assert result.exit_code == 0
        assert "Workflow exported to test.json" in result.output

        # Check that file was created with correct content
        with open("test.json", "r") as f:
            data = json.load(f)
            assert data["id"] == "wf123"
            assert data["name"] == "Test Workflow"


def test_export_workflow_not_found(monkeypatch, runner):
    """Test exporting a workflow that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return None

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["workflows", "export", "--id", "nonexistent", "--output", "test.json"]
        )
        assert result.exit_code == 1
        assert "not found" in result.output


def test_import_workflow_success(monkeypatch, runner):
    """Test importing a workflow successfully."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            @property
            def status_code(self):
                return 201

            @property
            def text(self):
                return '{"id": "wf123"}'

            def json(self):
                return {"id": "wf123"}

        return R()

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": [{"id": "ws456", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        # Create test workflow file with workspace
        workflow_data = {
            "name": "Test Workflow",
            "description": "Test description",
            "definition": {"states": []},
            "workspace": "ws456",
        }
        with open("test_workflow.json", "w") as f:
            json.dump(workflow_data, f)

        result = runner.invoke(cli, ["workflows", "import", "--file", "test_workflow.json"])
        assert result.exit_code == 0
        assert "Workflow imported successfully" in result.output


def test_import_workflow_failure(monkeypatch, runner):
    """Test importing a workflow with failure."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            @property
            def status_code(self):
                return 400

            @property
            def text(self):
                return """{
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "code": -251041,
                        "message": "One or more errors occurred. See the contained list for details of each error.",
                        "args": [],
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.InputValidationError",
                                "message": "Validation for input $ failed with the following error. JSON deserialization for type 'NationalInstruments.WorkOrder.Model.Api.V1.Requests.CreateWorkflowRequest' was missing required properties, including the following: states",
                                "args": ["$", "JSON deserialization for type 'NationalInstruments.WorkOrder.Model.Api.V1.Requests.CreateWorkflowRequest' was missing required properties, including the following: states"],
                                "innerErrors": []
                            },
                            {
                                "name": "Skyline.WorkOrder.InputValidationError",
                                "message": "Validation for input request failed with the following error. The request field is required.",
                                "args": ["request", "The request field is required."],
                                "innerErrors": []
                            }
                        ]
                    }
                }"""

            def json(self):
                return {
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "code": -251041,
                        "message": "One or more errors occurred. See the contained list for details of each error.",
                        "args": [],
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.InputValidationError",
                                "message": "Validation for input $ failed with the following error. JSON deserialization for type 'NationalInstruments.WorkOrder.Model.Api.V1.Requests.CreateWorkflowRequest' was missing required properties, including the following: states",
                                "args": [
                                    "$",
                                    "JSON deserialization for type 'NationalInstruments.WorkOrder.Model.Api.V1.Requests.CreateWorkflowRequest' was missing required properties, including the following: states",
                                ],
                                "innerErrors": [],
                            },
                            {
                                "name": "Skyline.WorkOrder.InputValidationError",
                                "message": "Validation for input request failed with the following error. The request field is required.",
                                "args": ["request", "The request field is required."],
                                "innerErrors": [],
                            },
                        ],
                    }
                }

        return R()

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": [{"id": "ws456", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        # Create test workflow file with workspace
        workflow_data = {
            "name": "Test Workflow",
            "description": "Test description",
            "workspace": "ws456",
        }
        with open("test_workflow.json", "w") as f:
            json.dump(workflow_data, f)

        result = runner.invoke(cli, ["workflows", "import", "--file", "test_workflow.json"])
        assert result.exit_code == 1
        assert "Workflow import failed" in result.output
        assert "One or more errors occurred" in result.output
        assert "InputValidationError" in result.output
        assert "missing required properties" in result.output


def test_delete_workflow_success(monkeypatch, runner):
    """Test deleting a workflow successfully."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            @property
            def status_code(self):
                return 204

            @property
            def text(self):
                return ""

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workflows", "delete", "--id", "wf123"])
    assert result.exit_code == 0
    assert "deleted successfully" in result.output


def test_delete_workflow_failure(monkeypatch, runner):
    """Test deleting a workflow with failure."""
    patch_keyring(monkeypatch)

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            @property
            def status_code(self):
                return 200  # Delete API returns 200 even for failures

            @property
            def text(self):
                return json.dumps(
                    {
                        "deletedWorkflowIds": [],
                        "failedWorkflowIds": ["nonexistent"],
                        "error": {
                            "name": "Skyline.OneOrMoreErrorsOccurred",
                            "code": -251041,
                            "message": "One or more errors occurred. See the contained list for details of each error.",
                            "resourceType": None,
                            "resourceId": None,
                            "args": [],
                            "innerErrors": [
                                {
                                    "name": "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess",
                                    "code": None,
                                    "message": "Workflow with ID nonexistent does not exist or you do not have permission to perform the requested operation.",
                                    "resourceType": "workflow",
                                    "resourceId": "nonexistent",
                                    "args": ["nonexistent"],
                                    "innerErrors": [],
                                }
                            ],
                        },
                    }
                )

            def json(self):
                return {
                    "deletedWorkflowIds": [],
                    "failedWorkflowIds": ["nonexistent"],
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "code": -251041,
                        "message": "One or more errors occurred. See the contained list for details of each error.",
                        "resourceType": None,
                        "resourceId": None,
                        "args": [],
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess",
                                "code": None,
                                "message": "Workflow with ID nonexistent does not exist or you do not have permission to perform the requested operation.",
                                "resourceType": "workflow",
                                "resourceId": "nonexistent",
                                "args": ["nonexistent"],
                                "innerErrors": [],
                            }
                        ],
                    },
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workflows", "delete", "--id", "nonexistent"])
    assert result.exit_code != 0
    assert "Failed to delete workflow" in result.output


def test_update_workflow_success(monkeypatch, runner):
    """Test updating a workflow successfully."""
    patch_keyring(monkeypatch)

    def mock_put(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            @property
            def status_code(self):
                return 200

            @property
            def text(self):
                return ""

            def json(self):
                return {}

        return R()

    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    with runner.isolated_filesystem():
        # Create test workflow file
        workflow_data = {
            "name": "Updated Workflow",
            "description": "Updated description",
            "definition": {"states": []},
        }
        with open("updated_workflow.json", "w") as f:
            json.dump(workflow_data, f)

        result = runner.invoke(
            cli, ["workflows", "update", "--id", "wf123", "--file", "updated_workflow.json"]
        )
        assert result.exit_code == 0
        assert "updated successfully" in result.output

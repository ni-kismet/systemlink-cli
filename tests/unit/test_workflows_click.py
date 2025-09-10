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
    result = runner.invoke(cli, ["workflow", "list"])
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
    result = runner.invoke(cli, ["workflow", "list", "--workspace", "Test"])
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
    result = runner.invoke(cli, ["workflow", "list"])
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
            cli, ["workflow", "export", "--id", "wf123", "--output", "test.json"]
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
            cli, ["workflow", "export", "--id", "nonexistent", "--output", "test.json"]
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

        result = runner.invoke(cli, ["workflow", "import", "--file", "test_workflow.json"])
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

        result = runner.invoke(cli, ["workflow", "import", "--file", "test_workflow.json"])
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
    result = runner.invoke(cli, ["workflow", "delete", "--id", "wf123"])
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
    result = runner.invoke(cli, ["workflow", "delete", "--id", "nonexistent"])
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
            cli, ["workflow", "update", "--id", "wf123", "--file", "updated_workflow.json"]
        )
        assert result.exit_code == 0
        assert "updated successfully" in result.output


# --- New tests for workflow preview / Mermaid generation --- #


def _sample_workflow_for_mermaid():  # helper (not a test)
    return {
        "name": "SampleWF",
        "description": "Sample workflow for mermaid generation",
        "workspace": "ws123",
        "actions": [
            {
                "name": "PING",
                "displayText": "Ping",
                "privilegeSpecificity": ["Submit"],
                "iconClass": "RESUME",
                "executionAction": {"type": "MANUAL", "action": "PING"},
            },
            {
                "name": "GO",
                "displayText": "Go",
                "privilegeSpecificity": ["ExecuteTest"],
                "iconClass": "RUN",
                "executionAction": {
                    "type": "NOTEBOOK",
                    "action": "GO",
                    "notebookId": "abcdef1234567890",
                },
            },
            {
                "name": "PLAN",
                "displayText": "Plan-Schedule",
                "privilegeSpecificity": [],
                "executionAction": {"type": "SCHEDULE", "action": "PLAN"},
            },
            {
                "name": "UNPLAN",
                "displayText": "Unplan-Schedule",
                "privilegeSpecificity": [],
                "executionAction": {"type": "UNSCHEDULE", "action": "UNPLAN"},
            },
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": True,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "PING",
                                "nextState": "READY",
                                "nextSubstate": "READY",
                                "showInUI": True,
                            },
                            {
                                "action": "GO",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": False,  # hidden action
                            },
                        ],
                    }
                ],
            },
            {
                "name": "READY",
                "dashboardAvailable": False,
                "defaultSubstate": "READY",
                "substates": [
                    {
                        "name": "READY",
                        "displayText": "Ready",
                        "availableActions": [
                            {
                                "action": "PLAN",
                                "nextState": "SCHEDULED",
                                "nextSubstate": "SCHEDULED",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "SCHEDULED",
                "dashboardAvailable": False,
                "defaultSubstate": "SCHEDULED",
                "substates": [
                    {
                        "name": "SCHEDULED",
                        "displayText": "Sched",
                        "availableActions": [
                            {
                                "action": "UNPLAN",
                                "nextState": "READY",
                                "nextSubstate": "READY",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }


def test_generate_mermaid_basic():
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = _sample_workflow_for_mermaid()
    code = generate_mermaid_diagram(wf)
    # Basic structure
    assert code.startswith("stateDiagram-v2"), code
    # Multiline state label present (dashboard metadata line)
    assert "(1 action" in code or "1 action" in code  # depending on hidden count formatting
    # Emoji for MANUAL action
    assert "🧑" in code
    # Notebook action hidden with hidden marker
    assert "hidden" in code
    # Icon lightning indicator
    assert "⚡️" in code
    # No legend inside Mermaid source
    assert "LEGEND :" not in code


def test_generate_mermaid_hierarchical_composite():
    """Verify composite state block, default pointer, and _BASE id suffix handling."""
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = {
        "actions": [
            {
                "name": "Start",
                "displayText": "Start",
                "iconClass": "PLAY",
                "executionAction": {"action": "Start", "type": "MANUAL"},
                "privilegeSpecificity": [],
            }
        ],
        "states": [
            {
                "name": "IN_PROGRESS",
                "defaultSubstate": "IN_PROGRESS",
                "dashboardAvailable": False,
                "substates": [
                    {"name": "IN_PROGRESS", "displayText": "In Progress", "availableActions": []},
                    {
                        "name": "Connected",
                        "displayText": "Connected",
                        "availableActions": [
                            {
                                "action": "Start",
                                "nextState": "IN_PROGRESS",
                                "nextSubstate": "Running",
                                "showInUI": True,
                            }
                        ],
                    },
                    {"name": "Running", "displayText": "Running", "availableActions": []},
                ],
            }
        ],
    }
    code = generate_mermaid_diagram(wf)
    # Composite block header
    assert "state IN_PROGRESS {" in code
    # Default pointer targets _BASE node
    assert "[*] --> IN_PROGRESS_BASE" in code
    # Base node label
    assert "IN_PROGRESS_BASE:" in code
    # Other substate nodes present (sanitized IDs)
    assert "IN_PROGRESS_Connected:" in code
    assert "IN_PROGRESS_Running:" in code
    # Transition uses internal IDs (source internal, target internal)
    assert any(
        "IN_PROGRESS_Connected --> IN_PROGRESS_Running" in line for line in code.splitlines()
    )


def test_generate_mermaid_hidden_action_marker():
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = _sample_workflow_for_mermaid()
    code = generate_mermaid_diagram(wf)
    # Hidden action should have newline then 'hidden'
    assert any(line.strip().endswith("hidden") for line in code.splitlines())


def test_generate_html_contains_external_legend():
    from slcli.workflow_preview import generate_mermaid_diagram, generate_html_with_mermaid

    wf = _sample_workflow_for_mermaid()
    mermaid = generate_mermaid_diagram(wf)
    html = generate_html_with_mermaid(wf, mermaid)
    assert '<div class="legend"' in html
    # Legend table present and contains expected emoji + description cells
    assert "⚡️" in html  # icon legend entry
    # Manual action legend is rendered in separate table cells; verify both parts
    assert "🧑</td><td>Manual action" in html
    # Ensure legend items are not accidentally inside Mermaid code block
    mermaid_section = html.split('<div class="mermaid">', 1)[1].split("</div>", 1)[0]
    assert "Manual action" not in mermaid_section


def test_preview_mmd_output(monkeypatch, runner):
    """End-to-end preview with --format mmd should not embed legend and should include emojis."""
    patch_keyring(monkeypatch)

    # Mock GET workflow fetch
    workflow_payload = _sample_workflow_for_mermaid()

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return workflow_payload

    monkeypatch.setattr("requests.get", lambda *a, **k: R())

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["workflow", "preview", "--id", "wf123", "--format", "mmd", "--output", "out.mmd"]
        )
        assert result.exit_code == 0, result.output
        with open("out.mmd", "r", encoding="utf-8") as f:
            mmd = f.read()
        assert "LEGEND :" not in mmd
        assert "🧑" in mmd
        assert "⚡️" in mmd


def test_preview_html_output(monkeypatch, runner):
    """End-to-end preview HTML should include external legend but not legend inside mermaid code."""
    patch_keyring(monkeypatch)

    workflow_payload = _sample_workflow_for_mermaid()

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return workflow_payload

    monkeypatch.setattr("requests.get", lambda *a, **k: R())

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["workflow", "preview", "--id", "wf123", "--format", "html", "--output", "out.html"],
        )
        assert result.exit_code == 0, result.output
        html = open("out.html", "r", encoding="utf-8").read()
        assert '<div class="legend"' in html
        assert "🧑</td><td>Manual action" in html
        # Icon class legend row has two separate cells as well
        assert "⚡️ NAME</td><td>UI icon class" in html  # legend entry
        mermaid_section = html.split('<div class="mermaid">', 1)[1].split("</div>", 1)[0]
        assert "Manual action" not in mermaid_section


def test_mermaid_sanitization_and_truncation():
    """Verify sanitization of problematic characters and notebook ID truncation."""
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = _sample_workflow_for_mermaid()
    wf["actions"][0]["displayText"] = "Ping:Check /test [alpha]"  # colon, slash, brackets
    wf["actions"][0]["privilegeSpecificity"] = ["Execute:Test", "Run/It"]
    code = generate_mermaid_diagram(wf)
    # Colon -> space, slash -> -, [ ] -> ( )
    assert "Ping Check -test (alpha)" in code
    # Privileges group sanitized
    assert "(Execute Test, Run-It)" in code
    # Notebook ID truncated to first 8 chars + ...
    assert "NB abcdef12..." in code


def test_mermaid_privileges_multiple():
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = _sample_workflow_for_mermaid()
    wf["actions"][1]["privilegeSpecificity"] = ["PrivA", "PrivB"]
    code = generate_mermaid_diagram(wf)
    assert "(PrivA, PrivB)" in code


def test_mermaid_action_without_icon():
    from slcli.workflow_preview import generate_mermaid_diagram

    wf = _sample_workflow_for_mermaid()
    wf["actions"][1].pop("iconClass", None)
    code = generate_mermaid_diagram(wf)
    # Ensure lightning present at least once (PING has icon)
    assert "⚡️" in code


def test_preview_no_emoji_flag(monkeypatch, runner):
    patch_keyring(monkeypatch)
    workflow_payload = _sample_workflow_for_mermaid()

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return workflow_payload

    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "workflow",
                "preview",
                "--id",
                "wf123",
                "--format",
                "mmd",
                "--no-emoji",
                "--output",
                "out.mmd",
            ],
        )
        assert result.exit_code == 0, result.output
        content = open("out.mmd", "r", encoding="utf-8").read()
        assert "🧑" not in content and "📓" not in content


def test_preview_no_legend_flag(monkeypatch, runner):
    patch_keyring(monkeypatch)
    workflow_payload = _sample_workflow_for_mermaid()

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return workflow_payload

    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "workflow",
                "preview",
                "--id",
                "wf123",
                "--format",
                "html",
                "--output",
                "out.html",
                "--no-legend",
            ],
        )
        assert result.exit_code == 0, result.output
        html = open("out.html", "r", encoding="utf-8").read()
        assert '<div class="legend"' not in html


def test_preview_stdin(monkeypatch, runner):
    patch_keyring(monkeypatch)
    cli = make_cli()
    wf = _sample_workflow_for_mermaid()
    import json as _json

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["workflow", "preview", "--file", "-", "--format", "mmd", "--output", "wf.mmd"],
            input=_json.dumps(wf),
        )
        assert result.exit_code == 0, result.output
        content = open("wf.mmd", "r", encoding="utf-8").read()
        assert content.startswith("stateDiagram-v2")

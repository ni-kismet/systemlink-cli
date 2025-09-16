import json

import click
import pytest
from typing import Any
from click.testing import CliRunner

from slcli.templates_click import register_templates_commands
from .test_utils import patch_keyring


def make_cli() -> click.Group:
    """Create a dummy CLI for testing."""

    @click.group()
    def cli() -> None:
        pass

    register_templates_commands(cli)
    return cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def mock_requests(
    monkeypatch: Any, method: str, response_json: Any, status_code: int = 200
) -> None:
    class MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> Any:
            return response_json

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise Exception("HTTP error")

    monkeypatch.setattr("requests." + method, lambda *a, **kw: MockResponse())


def test_list_templates_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing templates with a successful response."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Workspace1"}]}

        return R()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "testPlanTemplates": [{"id": "t1", "name": "Template1", "workspace": "ws1"}]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["template", "list"])
    assert result.exit_code == 0
    assert "Template1" in result.output


def test_list_templates_with_workspace_filter(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing templates with workspace filter."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {"id": "ws1", "name": "Workspace1"},
                        {"id": "ws2", "name": "Workspace2"},
                    ]
                }

        return R()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # Get the payload to check for filtering
                payload = kw.get("json", {})
                filter_clause = payload.get("filter", "")

                all_templates = [
                    {"id": "t1", "name": "Template1", "workspace": "ws1"},
                    {"id": "t2", "name": "Template2", "workspace": "ws2"},
                ]

                # Apply workspace filtering if present
                if 'WORKSPACE == "ws1"' in filter_clause:
                    # Filter to only ws1 templates
                    filtered_templates = [t for t in all_templates if t["workspace"] == "ws1"]
                elif 'WORKSPACE == "ws2"' in filter_clause:
                    # Filter to only ws2 templates
                    filtered_templates = [t for t in all_templates if t["workspace"] == "ws2"]
                else:
                    # No filter, return all
                    filtered_templates = all_templates

                return {"testPlanTemplates": filtered_templates}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()

    # Test filtering by workspace name
    result = runner.invoke(cli, ["template", "list", "--workspace", "Workspace1"])
    assert result.exit_code == 0
    assert "Template1" in result.output
    assert "Template2" not in result.output


def test_list_templates_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing templates when none exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": []}

        return R()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"testPlanTemplates": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["template", "list"])
    assert result.exit_code == 0
    assert "No test plan templates found." in result.output


def test_export_template_success(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Test exporting a template successfully."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"testPlanTemplates": [{"id": "t1", "name": "Template1"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    output_file = tmp_path / "out.json"
    result = runner.invoke(cli, ["template", "export", "--id", "t1", "--output", str(output_file)])
    assert result.exit_code == 0
    assert output_file.read_text().startswith("{")
    assert "exported to" in result.output


def test_export_template_auto_filename(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Test exporting a template with auto-generated filename."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"testPlanTemplates": [{"id": "t1", "name": "Test Template Name"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    # Change to the tmp_path directory for the test
    import os

    original_cwd = os.getcwd()
    os.chdir(tmp_path)

    try:
        cli = make_cli()
        result = runner.invoke(cli, ["template", "export", "--id", "t1"])
        assert result.exit_code == 0

        # Check that the auto-generated filename was created
        expected_file = tmp_path / "test-template-name.json"
        assert expected_file.exists()
        assert expected_file.read_text().startswith("{")
        assert "exported to test-template-name.json" in result.output
    finally:
        os.chdir(original_cwd)


def test_export_template_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Test exporting a template that does not exist."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"testPlanTemplates": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["template", "export", "--id", "notfound", "--output", "out.json"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_import_template_success(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Test importing a template successfully."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            text = "{}"  # Add text attribute for response parsing

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    input_file = tmp_path / "in.json"
    input_file.write_text(json.dumps({"id": "t1", "name": "Template1"}))
    result = runner.invoke(cli, ["template", "import", "--file", str(input_file)])
    assert result.exit_code == 0
    assert "imported successfully" in result.output


def test_import_template_partial_failure(
    monkeypatch: Any, runner: CliRunner, tmp_path: Any
) -> None:
    """Test importing a template with partial failures."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            text = """{
                "failedTestPlanTemplates": [{"name": "Test Template"}],
                "error": {
                    "name": "Skyline.OneOrMoreErrorsOccurred",
                    "message": "One or more errors occurred.",
                    "innerErrors": [
                        {
                            "name": "Skyline.WorkOrder.WorkspaceNotFoundOrNoAccess",
                            "message": "Workspace does not exist or you do not have permission.",
                            "resourceId": "Test Template",
                            "resourceType": "test plan template"
                        }
                    ]
                }
            }"""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "failedTestPlanTemplates": [{"name": "Test Template"}],
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "message": "One or more errors occurred.",
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.WorkspaceNotFoundOrNoAccess",
                                "message": "Workspace does not exist or you do not have permission.",
                                "resourceId": "Test Template",
                                "resourceType": "test plan template",
                            }
                        ],
                    },
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    input_file = tmp_path / "in.json"
    input_file.write_text(json.dumps({"id": "t1", "name": "Test Template"}))
    result = runner.invoke(cli, ["template", "import", "--file", str(input_file)])
    assert result.exit_code == 1
    assert "Template import failed" in result.output
    assert "WorkspaceNotFoundOrNoAccess" in result.output
    assert "Test Template" in result.output


def test_delete_template_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a template successfully."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["template", "delete", "--id", "t1"])
    assert result.exit_code == 0
    assert "deleted successfully" in result.output


def test_delete_template_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a template with a failure response."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 400

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

            text = "error"

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["template", "delete", "--id", "bad"])
    assert result.exit_code != 0
    assert "Failed to delete" in result.output

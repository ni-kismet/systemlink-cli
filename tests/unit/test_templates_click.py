import json

import click
import pytest
from click.testing import CliRunner

from slcli.templates_click import register_templates_commands


def make_cli():
    """Create a dummy CLI for testing."""

    @click.group()
    def cli():
        pass

    register_templates_commands(cli)
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


def test_list_templates_success(monkeypatch, runner):
    """Test listing templates with a successful response."""

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": [{"id": "ws1", "name": "Workspace1"}]}

        return R()

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "testPlanTemplates": [{"id": "t1", "name": "Template1", "workspace": "ws1"}]
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["templates", "list"])
    assert result.exit_code == 0
    assert "Template1" in result.output


def test_list_templates_empty(monkeypatch, runner):
    """Test listing templates when none exist."""

    def mock_get(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"workspaces": []}

        return R()

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"testPlanTemplates": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["templates", "list"])
    assert result.exit_code == 0
    assert "No test plan templates found." in result.output


def test_export_template_success(monkeypatch, runner, tmp_path):
    """Test exporting a template successfully."""

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"testPlanTemplates": [{"id": "t1", "name": "Template1"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    output_file = tmp_path / "out.json"
    result = runner.invoke(cli, ["templates", "export", "--id", "t1", "--output", str(output_file)])
    assert result.exit_code == 0
    assert output_file.read_text().startswith("{")
    assert "exported to" in result.output


def test_export_template_not_found(monkeypatch, runner):
    """Test exporting a template that does not exist."""

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"testPlanTemplates": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["templates", "export", "--id", "notfound", "--output", "out.json"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_import_template_success(monkeypatch, runner, tmp_path):
    """Test importing a template successfully."""

    def mock_post(*a, **kw):
        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    input_file = tmp_path / "in.json"
    input_file.write_text(json.dumps({"id": "t1", "name": "Template1"}))
    result = runner.invoke(cli, ["templates", "import", "--file", str(input_file)])
    assert result.exit_code == 0
    assert "imported successfully" in result.output


def test_delete_template_success(monkeypatch, runner):
    """Test deleting a template successfully."""

    def mock_post(*a, **kw):
        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["templates", "delete", "--id", "t1"])
    assert result.exit_code == 0
    assert "deleted successfully" in result.output


def test_delete_template_failure(monkeypatch, runner):
    """Test deleting a template with a failure response."""

    def mock_post(*a, **kw):
        class R:
            status_code = 400

            def raise_for_status(self):
                pass

            def json(self):
                return {}

            text = "error"

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    cli = make_cli()
    result = runner.invoke(cli, ["templates", "delete", "--id", "bad"])
    assert result.exit_code != 0
    assert "Failed to delete" in result.output

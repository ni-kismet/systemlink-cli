"""Unit tests for policy CLI commands."""

import json
from typing import Any
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner

from slcli.main import cli


def make_cli() -> Any:
    """Create a CLI instance for testing."""
    return cli


def mock_response(data: Any, status_code: int = 200) -> Any:
    """Create a mock API response object."""

    class R:
        def __init__(self, data: Any, code: int) -> None:
            self._data = data
            self.status_code = code

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

        def json(self) -> Any:
            return self._data

    return R(data, status_code)


class TestPolicyList:
    """Tests for policy list command."""

    def test_list_policies_success(self, monkeypatch: Any) -> None:
        """Test successful policy listing."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(
                {
                    "policies": [
                        {
                            "id": "policy-1",
                            "name": "Admin Policy",
                            "type": "role",
                            "builtIn": False,
                            "statements": [{"actions": ["*"], "resource": ["*"], "workspace": "*"}],
                        },
                        {
                            "id": "policy-2",
                            "name": "Read-Only Policy",
                            "type": "custom",
                            "builtIn": False,
                            "statements": [
                                {"actions": ["read"], "resource": ["*"], "workspace": "*"}
                            ],
                        },
                    ]
                }
            )

            result = runner.invoke(cli_instance, ["auth", "policy", "list"])
            assert result.exit_code == 0
            assert "Admin Policy" in result.output
            assert "Read-Only Policy" in result.output

    def test_list_policies_json_format(self, monkeypatch: Any) -> None:
        """Test policy listing with JSON output."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        policies = [
            {
                "id": "policy-1",
                "name": "Admin Policy",
                "type": "role",
                "builtIn": False,
            }
        ]

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response({"policies": policies})

            result = runner.invoke(cli_instance, ["auth", "policy", "list", "--format", "json"])
            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert isinstance(output_data, list)
            assert output_data[0]["name"] == "Admin Policy"

    def test_list_policies_with_type_filter(self, monkeypatch: Any) -> None:
        """Test policy listing with type filter."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response({"policies": []})

            result = runner.invoke(cli_instance, ["auth", "policy", "list", "--type", "role"])
            assert result.exit_code == 0
            # Verify query parameter was passed in URL (URL-encoded)
            call_args = mock_request.call_args
            url = call_args[0][1]  # Second positional argument is the URL
            assert "type=role" in url

    def test_list_policies_empty(self, monkeypatch: Any) -> None:
        """Test policy listing when no policies exist."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response({"policies": []})

            result = runner.invoke(cli_instance, ["auth", "policy", "list"])
            assert result.exit_code == 0
            assert "No policies found" in result.output


class TestPolicyGet:
    """Tests for policy get command."""

    def test_get_policy_success(self, monkeypatch: Any) -> None:
        """Test successful policy retrieval."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        policy_data = {
            "id": "policy-1",
            "name": "Admin Policy",
            "type": "role",
            "builtIn": False,
            "userId": "user-1",
            "created": "2024-01-01T00:00:00Z",
            "updated": "2024-01-01T00:00:00Z",
            "statements": [
                {
                    "actions": ["niuser:*"],
                    "resource": ["*"],
                    "workspace": "*",
                    "description": "Full admin access",
                }
            ],
            "properties": {},
        }

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(policy_data)

            result = runner.invoke(cli_instance, ["auth", "policy", "get", "policy-1"])
            assert result.exit_code == 0
            assert "Admin Policy" in result.output
            assert "role" in result.output

    def test_get_policy_json_format(self, monkeypatch: Any) -> None:
        """Test policy get with JSON output."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        policy_data = {
            "id": "policy-1",
            "name": "Admin Policy",
            "type": "role",
            "builtIn": False,
        }

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(policy_data)

            result = runner.invoke(
                cli_instance, ["auth", "policy", "get", "policy-1", "--format", "json"]
            )
            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert output_data["id"] == "policy-1"


class TestPolicyCreate:
    """Tests for policy create command (template-based)."""

    def test_create_policy_from_template(self, monkeypatch: Any) -> None:
        """Test policy creation from a template with workspace."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(
                {"id": "policy-xyz", "name": "FromTemplate", "type": "custom"}
            )

            result = runner.invoke(
                cli_instance,
                [
                    "auth",
                    "policy",
                    "create",
                    "template-123",
                    "--name",
                    "FromTemplate",
                    "--workspace",
                    "ws-1",
                ],
            )

            assert result.exit_code == 0
            assert "Policy created" in result.output
            mock_request.assert_called_once_with(
                "POST",
                "http://localhost/niauth/v1/policies",
                payload={
                    "name": "FromTemplate",
                    "type": "custom",
                    "templateId": "template-123",
                    "workspace": "ws-1",
                },
            )


class TestPolicyDelete:
    """Tests for policy delete command."""

    def test_delete_policy_with_confirmation(self, monkeypatch: Any) -> None:
        """Test policy deletion with user confirmation."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            with patch("slcli.policy_click._fetch_policy_details") as mock_fetch:
                mock_fetch.return_value = {"id": "policy-1", "name": "MyPolicy"}
                mock_request.return_value = mock_response({}, 204)
                with patch("slcli.policy_click.questionary.confirm") as mock_confirm:
                    mock_confirm.return_value.ask.return_value = True
                    result = runner.invoke(cli_instance, ["auth", "policy", "delete", "policy-1"])
                assert result.exit_code == 0
                assert "Policy deleted" in result.output

    def test_delete_policy_force(self, monkeypatch: Any) -> None:
        """Test policy deletion with --force flag."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response({}, 204)

            result = runner.invoke(
                cli_instance,
                ["auth", "policy", "delete", "policy-1", "--force"],
            )
            assert result.exit_code == 0
            assert "Policy deleted" in result.output


class TestTemplateCreate:
    """Tests for reusable policy template creation."""

    @pytest.mark.parametrize("wrapped", [False, True])
    @pytest.mark.parametrize("template_type", ["user", "SERVICE"])
    def test_create_template(
        self, monkeypatch: Any, tmp_path: Any, wrapped: bool, template_type: str
    ) -> None:
        """Post workspace-free statements to the template endpoint."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")
        statements = [{"actions": ["testresult:Read"], "resource": ["*"]}]
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(
            json.dumps({"statements": statements} if wrapped else statements), encoding="utf-8"
        )
        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(
                {"id": "template-new", "name": "Reader", "type": template_type.lower()}
            )
            result = CliRunner().invoke(
                cli,
                [
                    "auth",
                    "template",
                    "create",
                    "--name",
                    "Reader",
                    "--type",
                    template_type,
                    "--statements-file",
                    str(statements_file),
                    "--properties",
                    "description=Read access",
                    "-p",
                    "team=QA",
                ],
            )
            assert result.exit_code == 0, result.output
            assert "Policy template created" in result.output
            assert "template-new" in result.output
            mock_request.assert_called_once_with(
                "POST",
                "http://localhost/niauth/v1/policy-templates",
                payload={
                    "name": "Reader",
                    "type": template_type.lower(),
                    "statements": statements,
                    "properties": {"description": "Read access", "team": "QA"},
                },
            )

    def test_create_template_json(self, monkeypatch: Any, tmp_path: Any) -> None:
        """Default to user templates and return the full response as JSON."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")
        statements = [{"actions": ["testresult:Read"], "resource": ["*"]}]
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(json.dumps(statements), encoding="utf-8")
        created = {"id": "template-new", "name": "Reader", "type": "user", "statements": statements}
        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(created)
            result = CliRunner().invoke(
                cli,
                [
                    "auth",
                    "template",
                    "create",
                    "--name",
                    "Reader",
                    "--statements-file",
                    str(statements_file),
                    "--format",
                    "json",
                ],
            )
            assert result.exit_code == 0, result.output
            assert json.loads(result.output) == created
            assert mock_request.call_args.kwargs["payload"] == {
                "name": "Reader",
                "type": "user",
                "statements": statements,
            }

    @pytest.mark.parametrize(
        "content",
        [
            "not json",
            "{}",
            "[]",
            '{"statements": {}}',
            "[null]",
            '[{"actions": [], "resource": ["*"]}]',
            '[{"actions": ["read"], "resource": "*"}]',
        ],
    )
    def test_create_template_invalid_statements(self, tmp_path: Any, content: str) -> None:
        """Reject malformed statements before making any API request."""
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(content, encoding="utf-8")
        with patch("slcli.policy_click.make_api_request") as mock_request:
            result = CliRunner().invoke(
                cli,
                [
                    "auth",
                    "template",
                    "create",
                    "--name",
                    "Reader",
                    "--statements-file",
                    str(statements_file),
                ],
            )
            assert result.exit_code == 2, result.output
            assert "Error:" in result.output
            mock_request.assert_not_called()

    @pytest.mark.parametrize(
        "options",
        [
            [],
            ["--statements-file", "missing.json"],
            ["--statements-file", "statements.json", "--type", "custom"],
            ["--statements-file", "statements.json", "--properties", "invalid"],
        ],
    )
    def test_create_template_invalid_options(self, tmp_path: Any, options: list[str]) -> None:
        """Reject missing inputs, invalid types, and malformed properties."""
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(
            '[{"actions": ["testresult:Read"], "resource": ["*"]}]', encoding="utf-8"
        )
        options = [
            str(statements_file) if value == "statements.json" else value for value in options
        ]
        with patch("slcli.policy_click.make_api_request") as mock_request:
            result = CliRunner().invoke(
                cli, ["auth", "template", "create", "--name", "Reader", *options]
            )
            assert result.exit_code == 2, result.output
            mock_request.assert_not_called()

    def test_create_template_readonly(self, tmp_path: Any) -> None:
        """Block creation before making requests when the profile is read-only."""
        statements_file = tmp_path / "statements.json"
        statements_file.write_text("[]", encoding="utf-8")
        with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
            with patch("slcli.policy_click.make_api_request") as mock_request:
                result = CliRunner().invoke(
                    cli,
                    [
                        "auth",
                        "template",
                        "create",
                        "--name",
                        "Reader",
                        "--statements-file",
                        str(statements_file),
                    ],
                )
                assert result.exit_code == 4, result.output
                assert "readonly mode" in result.output
                mock_request.assert_not_called()

    @pytest.mark.parametrize(
        "error, exit_code",
        [(requests.HTTPError("Forbidden"), 4), (requests.ConnectionError("Connection failed"), 5)],
    )
    def test_create_template_api_error(
        self, monkeypatch: Any, tmp_path: Any, error: Exception, exit_code: int
    ) -> None:
        """Preserve API permission and network error exit codes."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(
            '[{"actions": ["testresult:Read"], "resource": ["*"]}]', encoding="utf-8"
        )
        with patch("slcli.policy_click.make_api_request", side_effect=error):
            result = CliRunner().invoke(
                cli,
                [
                    "auth",
                    "template",
                    "create",
                    "--name",
                    "Reader",
                    "--statements-file",
                    str(statements_file),
                ],
            )
            assert result.exit_code == exit_code, result.output

    def test_create_template_response_json_error_is_api_error(
        self, monkeypatch: Any, tmp_path: Any
    ) -> None:
        """Treat response JSON decoding failures as API errors, not invalid input."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")
        statements_file = tmp_path / "statements.json"
        statements_file.write_text(
            '[{"actions": ["testresult:Read"], "resource": ["*"]}]', encoding="utf-8"
        )
        response = mock_response({})
        with patch.object(response, "json", side_effect=ValueError("invalid API response JSON")):
            with patch("slcli.policy_click.make_api_request", return_value=response):
                result = CliRunner().invoke(
                    cli,
                    [
                        "auth",
                        "template",
                        "create",
                        "--name",
                        "Reader",
                        "--statements-file",
                        str(statements_file),
                    ],
                )
        assert result.exit_code == 1, result.output
        assert "Error: invalid API response JSON" in result.output

    def test_policy_statements_still_require_workspace(self) -> None:
        """Workspace-free validation remains specific to template payloads."""
        from slcli.policy_utils import _build_policy_payload

        with pytest.raises(ValueError, match="workspace"):
            _build_policy_payload(
                "Reader", "custom", statements=[{"actions": ["read"], "resource": ["*"]}]
            )


class TestTemplateList:
    """Tests for policy template list command."""

    def test_list_templates_success(self, monkeypatch: Any) -> None:
        """Test successful template listing."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(
                {
                    "policyTemplates": [
                        {
                            "id": "template-1",
                            "name": "User Template",
                            "type": "user",
                            "builtIn": True,
                            "statements": [
                                {"actions": ["read"], "resource": ["*"], "workspace": "*"}
                            ],
                        }
                    ]
                }
            )

            result = runner.invoke(cli_instance, ["auth", "template", "list"])
            assert result.exit_code == 0
            assert "User Template" in result.output

    def test_list_templates_json_format(self, monkeypatch: Any) -> None:
        """Test template listing with JSON output."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        templates = [
            {
                "id": "template-1",
                "name": "User Template",
                "type": "user",
                "builtIn": True,
            }
        ]

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response({"policyTemplates": templates})

            result = runner.invoke(cli_instance, ["auth", "template", "list", "--format", "json"])
            assert result.exit_code == 0
            output_data = json.loads(result.output)
            assert isinstance(output_data, list)
            assert output_data[0]["name"] == "User Template"


class TestTemplateGet:
    """Tests for policy template get command."""

    def test_get_template_success(self, monkeypatch: Any) -> None:
        """Test successful template retrieval."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        template_data = {
            "id": "template-1",
            "name": "User Template",
            "type": "user",
            "builtIn": True,
            "userId": "system",
            "created": "2024-01-01T00:00:00Z",
            "updated": "2024-01-01T00:00:00Z",
            "statements": [
                {
                    "actions": ["niuser:Read"],
                    "resource": ["user-*"],
                    "workspace": "*",
                }
            ],
            "properties": {},
        }

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.return_value = mock_response(template_data)

            result = runner.invoke(cli_instance, ["auth", "template", "get", "template-1"])
            assert result.exit_code == 0
            assert "User Template" in result.output
            assert "user" in result.output


class TestPolicyExportImportDiff:
    """Tests for policy diff command."""

    def test_diff_policies_basic(self, monkeypatch: Any) -> None:
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        p1 = {
            "id": "p1",
            "name": "A",
            "type": "custom",
            "workspace": "ws-alpha",
            "statements": [{"actions": ["read"], "resource": ["*"], "workspace": "default"}],
        }
        p2 = {
            "id": "p2",
            "name": "B",
            "type": "custom",
            "workspace": "ws-beta",
            "statements": [{"actions": ["write"], "resource": ["data/*"], "workspace": "*"}],
        }

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.side_effect = [mock_response(p1), mock_response(p2)]
            result = runner.invoke(cli_instance, ["auth", "policy", "diff", "p1", "p2"])

            assert result.exit_code == 0
            assert "Policy Diff" in result.output
            assert "Only in policy 1:" in result.output
            assert "Only in policy 2:" in result.output
            assert "Workspace: ws-alpha  vs  ws-beta" in result.output


class TestPolicyUpdate:
    """Tests for policy update command."""

    def test_update_policy_uses_existing_statements_when_not_provided(
        self, monkeypatch: Any
    ) -> None:
        """Update should use current statements if none provided."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        existing_policy = {
            "id": "policy-1",
            "name": "OldName",
            "type": "custom",
            "statements": [{"actions": ["read"], "resource": ["*"], "workspace": "*"}],
        }
        updated_policy = {**existing_policy, "name": "NewName"}

        with patch("slcli.policy_click.make_api_request") as mock_request:
            mock_request.side_effect = [
                mock_response(existing_policy),
                mock_response(updated_policy),
            ]

            result = runner.invoke(
                cli_instance,
                ["auth", "policy", "update", "policy-1", "--name", "NewName"],
            )

            assert result.exit_code == 0
            assert "Policy updated" in result.output

            put_call = mock_request.call_args_list[1]
            payload = put_call.kwargs.get("payload")
            assert payload is not None
            assert payload["name"] == "NewName"
            assert payload["statements"] == existing_policy["statements"]


class TestTemplateDelete:
    """Tests for template delete command."""

    def test_delete_template_with_confirmation(self, monkeypatch: Any) -> None:
        """Delete template asks for confirmation."""
        monkeypatch.setenv("SLCLI_API_URL", "http://localhost")
        monkeypatch.setenv("SLCLI_API_KEY", "test")

        cli_instance = make_cli()
        runner = CliRunner()

        with patch("slcli.policy_click._fetch_template_details") as mock_fetch:
            mock_fetch.return_value = {"id": "template-1", "name": "Template"}
            with patch("slcli.policy_click.make_api_request") as mock_request:
                mock_request.return_value = mock_response({}, 204)
                with patch("slcli.policy_click.questionary.confirm") as mock_confirm:
                    mock_confirm.return_value.ask.return_value = True
                    result = runner.invoke(
                        cli_instance,
                        ["auth", "template", "delete", "template-1"],
                    )

                assert result.exit_code == 0
                assert "Policy template deleted" in result.output

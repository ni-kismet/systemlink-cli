"""Unit tests for user CLI commands."""

import json
from typing import Any, Optional
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from slcli.user_click import register_user_commands


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def mock_response(data: Any, status_code: int = 200) -> Any:
    """Create a mock response object with json and status code."""

    class MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> Any:
            return data

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise Exception("HTTP error")

    return MockResponse()


def make_cli() -> click.Group:
    """Create CLI instance with user commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_user_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> Any:
    return CliRunner()


def mock_requests(
    monkeypatch: Any, method: str, response_json: Any, status_code: int = 200
) -> None:
    """Mock requests module for testing."""

    class MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> Any:
            return response_json

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise Exception("HTTP error")

    monkeypatch.setattr("requests." + method.lower(), lambda *a, **kw: MockResponse())


class TestUserList:
    """Test user list command."""

    def test_list_users_table_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test listing users in table format."""
        patch_keyring(monkeypatch)
        mock_users: dict[str, Any] = {
            "users": [
                {
                    "id": "user1",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john.doe@example.com",
                    "status": "active",
                },
                {
                    "id": "user2",
                    "firstName": "Jane",
                    "lastName": "Smith",
                    "email": "jane.smith@example.com",
                    "status": "pending",
                },
            ]
        }
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list"])

        assert result.exit_code == 0
        assert "John" in result.output
        assert "Doe" in result.output
        assert "jane.smith@example.com" in result.output

    def test_list_users_json_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test listing users in JSON format."""
        patch_keyring(monkeypatch)
        mock_users: dict[str, Any] = {
            "users": [
                {
                    "id": "user1",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john.doe@example.com",
                    "status": "active",
                }
            ]
        }
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list", "--format", "json"])

        assert result.exit_code == 0
        users_json = json.loads(result.output)
        assert len(users_json) == 1
        assert users_json[0]["firstName"] == "John"

    def test_list_users_with_filter(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test listing users with filter."""
        patch_keyring(monkeypatch)
        mock_users: dict[str, Any] = {"users": []}
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list", "--filter", 'firstName.StartsWith("John")'])

        assert result.exit_code == 0
        assert "No users found." in result.output

    def test_list_users_empty_result(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test listing users with empty result."""
        patch_keyring(monkeypatch)
        mock_users: dict[str, Any] = {"users": []}
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list"])

        assert result.exit_code == 0
        assert "No users found." in result.output


class TestUserGet:
    """Test user get command."""

    def test_get_user_table_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details in table format."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
            "login": "johndoe",
            "orgId": "org1",
        }

        def mock_requests_func(method: str, *args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    return mock_user

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "User Details:" in result.output
        assert "John" in result.output
        assert "john.doe@example.com" in result.output

    def test_get_user_with_policies_table_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details with policies in table format."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
            "policies": ["policy1", "policy2"],
        }

        mock_policies = {
            "policy1": {
                "id": "policy1",
                "name": "Admin Policy",
                "type": "role",
                "statements": [
                    {
                        "actions": ["*"],
                        "resource": ["*"],
                        "workspace": "workspace1",
                        "description": "Full admin access",
                    }
                ],
            },
            "policy2": {
                "id": "policy2",
                "name": "Read Only Policy",
                "type": "permission",
                "statements": [
                    {
                        "actions": ["read"],
                        "resource": ["data/*"],
                        "workspace": "workspace2",
                        "description": "Read only access to data",
                    }
                ],
            },
        }

        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        # Extract policy ID from URL
                        policy_id = url.split("/")[-1]
                        return mock_policies.get(policy_id, {})
                    return {}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "User Details:" in result.output
        assert "Policies:" in result.output
        assert "Admin Policy" in result.output

    def test_get_user_with_policies_json_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details with policies in JSON format."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
            "policies": ["policy1"],
        }

        mock_policy = {
            "id": "policy1",
            "name": "Admin Policy",
            "type": "role",
            "statements": [
                {
                    "actions": ["*"],
                    "resource": ["*"],
                    "workspace": "workspace1",
                    "description": "Full admin access",
                }
            ],
        }

        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy
                    return {}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1", "--format", "json"])

        assert result.exit_code == 0
        import json

        output_data = json.loads(result.output)
        assert "expanded_policies" in output_data
        assert len(output_data["expanded_policies"]) == 1
        assert output_data["expanded_policies"][0]["name"] == "Admin Policy"

    def test_get_user_with_policy_templates(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details with policies that use templates."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
            "policies": ["policy1"],
        }

        mock_policy_with_template = {
            "id": "policy1",
            "name": "Template-based Policy",
            "type": "role",
            "templateId": "template1",
            "workspace": "workspace1",
            "statements": [],  # Empty since it uses a template
        }

        mock_template = {
            "id": "template1",
            "name": "Admin Template",
            "type": "role",
            "statements": [
                {
                    "actions": ["*"],
                    "resource": ["*"],
                    "description": "Full admin access via template",
                }
            ],
        }

        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy_with_template
                    elif "/policy-templates/" in url:
                        return mock_template
                    return {}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "Template-based Policy" in result.output
        assert "Template: Admin Template" in result.output
        assert "Full admin access via template" in result.output

    def test_get_user_with_policy_templates_json_format(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test getting user details with policy templates in JSON format."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
            "policies": ["policy1"],
        }

        mock_policy_with_template = {
            "id": "policy1",
            "name": "Template-based Policy",
            "type": "role",
            "templateId": "template1",
            "workspace": "workspace1",
            "statements": [],
        }

        mock_template = {
            "id": "template1",
            "name": "Admin Template",
            "type": "role",
            "statements": [
                {
                    "actions": ["*"],
                    "resource": ["*"],
                    "description": "Full admin access via template",
                }
            ],
        }

        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy_with_template
                    elif "/policy-templates/" in url:
                        return mock_template
                    return {}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1", "--format", "json"])

        assert result.exit_code == 0
        import json

        output_data = json.loads(result.output)
        assert "expanded_policies" in output_data
        assert len(output_data["expanded_policies"]) == 1

        policy = output_data["expanded_policies"][0]
        assert policy["name"] == "Template-based Policy"
        assert "template" in policy
        assert policy["template"]["name"] == "Admin Template"
        assert len(policy["statements"]) == 1  # Should have template statements
        assert policy["statements"][0]["description"] == "Full admin access via template"

    def test_get_user_json_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details in JSON format."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "status": "active",
        }
        mock_requests(monkeypatch, "get", mock_user)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1", "--format", "json"])

        assert result.exit_code == 0
        user_json = json.loads(result.output)
        assert user_json["firstName"] == "John"

    def test_get_user_by_email_table_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details by email in table format."""
        patch_keyring(monkeypatch)
        mock_query_response: dict[str, Any] = {
            "users": [
                {
                    "id": "user1",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john.doe@example.com",
                    "status": "active",
                    "login": "johndoe",
                    "orgId": "org1",
                }
            ]
        }
        mock_requests(monkeypatch, "post", mock_query_response)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--email", "john.doe@example.com"])

        assert result.exit_code == 0
        assert "User Details:" in result.output
        assert "John" in result.output
        assert "john.doe@example.com" in result.output

    def test_get_user_by_email_json_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user details by email in JSON format."""
        patch_keyring(monkeypatch)
        mock_query_response: dict[str, Any] = {
            "users": [
                {
                    "id": "user1",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john.doe@example.com",
                    "status": "active",
                }
            ]
        }
        mock_requests(monkeypatch, "post", mock_query_response)

        cli = make_cli()
        result = runner.invoke(
            cli, ["user", "get", "--email", "john.doe@example.com", "--format", "json"]
        )

        assert result.exit_code == 0
        user_json = json.loads(result.output)
        assert user_json["firstName"] == "John"

    def test_get_user_by_email_not_found(self, runner: Any, monkeypatch: Any) -> None:
        """Test getting user by email when user not found."""
        patch_keyring(monkeypatch)
        mock_query_response: dict[str, Any] = {"users": []}
        mock_requests(monkeypatch, "post", mock_query_response)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--email", "nonexistent@example.com"])

        assert result.exit_code == 3  # NOT_FOUND
        assert "✗ User with email 'nonexistent@example.com' not found." in result.output

    def test_get_user_no_params(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user with no ID or email provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Must provide either --id or --email." in result.output

    def test_get_user_both_params(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user with both ID and email provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli, ["user", "get", "--id", "user1", "--email", "john.doe@example.com"]
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Cannot specify both --id and --email. Choose one." in result.output

    def test_get_user_permission_denied(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test getting user when access is denied."""
        patch_keyring(monkeypatch)

        # Mock a 401 Unauthorized response
        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            import requests

            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 401

                def json(self) -> Any:
                    return {
                        "error": {
                            "args": [],
                            "code": -254850,
                            "innerErrors": [],
                            "message": "Not allowed to access resource.",
                            "name": "Unauthorized",
                        }
                    }

                def raise_for_status(self) -> None:
                    error = requests.HTTPError("Unauthorized")
                    error.response = self
                    raise error

            response = MockResponse()
            error = requests.HTTPError("Unauthorized")
            error.response = response
            raise error

        monkeypatch.setattr("requests.get", mock_requests_func)
        monkeypatch.setattr("requests.post", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 4  # PERMISSION_DENIED
        assert "✗ Access denied to user information (insufficient permissions)." in result.output

    def test_get_user_with_policy_permission_errors(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test getting user with policies when policy access is denied."""
        patch_keyring(monkeypatch)

        def mock_requests_func(url: str, *args: Any, **kwargs: Any) -> Any:
            import requests

            class MockResponse:
                def __init__(self) -> None:
                    if "/niauth/v1/policies/" in url:
                        # Policy access denied
                        self.status_code = 401
                    else:
                        # User access allowed
                        self.status_code = 200

                def json(self) -> Any:
                    if "/niauth/v1/policies/" in url:
                        return {
                            "error": {
                                "args": [],
                                "code": -254850,
                                "innerErrors": [],
                                "message": "Not allowed to access resource.",
                                "name": "Unauthorized",
                            }
                        }
                    else:
                        # Return user data with policies
                        return {
                            "id": "user1",
                            "firstName": "John",
                            "lastName": "Doe",
                            "email": "john.doe@example.com",
                            "policies": ["policy1", "policy2"],
                        }

                def raise_for_status(self) -> None:
                    if self.status_code >= 400:
                        error = requests.HTTPError("Unauthorized")
                        error.response = self
                        raise error

            response = MockResponse()
            if "/niauth/v1/policies/" in url and response.status_code == 401:
                error = requests.HTTPError("Unauthorized")
                error.response = response
                raise error
            return response

        monkeypatch.setattr("requests.get", mock_requests_func)
        monkeypatch.setattr("requests.post", lambda *a, **kw: mock_requests_func(a[0]))

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "John" in result.output
        assert (
            "✗ Access denied to the following policies (insufficient permissions):" in result.output
        )
        assert "Policy ID: policy1" in result.output
        assert "Policy ID: policy2" in result.output


class TestUserCreate:
    """Test user create command."""

    def test_create_user_success(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user successfully."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
        }
        mock_requests(monkeypatch, "post", mock_user)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created" in result.output
        assert "new-user-id" in result.output

    def test_create_user_with_policies(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with policies."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
        }
        mock_requests(monkeypatch, "post", mock_user)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--policies",
                "policy1,policy2",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created" in result.output

    def test_create_user_with_single_policy(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with --policy single ID."""
        patch_keyring(monkeypatch)
        captured_payload: dict[str, Any] = {}

        def mock_post_with_capture(url: str, json: Any = None, **kwargs: Any) -> Any:
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    return {"id": "new-user-id", "email": "john.doe@example.com"}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.post", mock_post_with_capture)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--policy",
                "policy1",
            ],
        )

        assert result.exit_code == 0
        assert captured_payload.get("policies") == ["policy1"]

    def test_create_user_with_workspace_policies(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Create user while generating workspace policies from templates."""
        patch_keyring(monkeypatch)

        def mock_get_password(service: str, key: str) -> Optional[str]:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps({"api_url": "http://localhost", "api_key": "test"})
            if key == "SYSTEMLINK_API_KEY":
                return "test"
            return None

        monkeypatch.setattr("slcli.utils.keyring.get_password", mock_get_password)

        cli = make_cli()
        runner_local = runner

        template_resp = {"id": "template-dev-123", "name": "templateDev"}
        policy_resp = {"id": "pol-ws-1", "name": "generated"}
        user_resp = {"id": "new-user-id", "email": "john.doe@example.com"}

        with patch("slcli.user_click.make_api_request") as mock_request, patch(
            "slcli.user_click.resolve_workspace_id"
        ) as mock_resolve:
            # First call: template lookup, second: policy creation, third: user creation
            mock_request.side_effect = [
                mock_response({"policyTemplates": [template_resp]}),
                mock_response(policy_resp),
                mock_response(user_resp),
            ]
            mock_resolve.return_value = "dev"

            result = runner_local.invoke(
                cli,
                [
                    "user",
                    "create",
                    "--type",
                    "user",
                    "--first-name",
                    "John",
                    "--last-name",
                    "Doe",
                    "--email",
                    "john.doe@example.com",
                    "--workspace-policies",
                    "dev:templateDev",
                ],
            )

            assert result.exit_code == 0
            # First call looks up template, second call creates policy, third call creates user
            assert len(mock_request.call_args_list) == 3
            user_call = mock_request.call_args_list[2]
            user_payload = user_call.kwargs.get("payload")
            assert user_payload
            assert user_payload.get("policies") == ["pol-ws-1"]

    def test_create_user_workspace_policies_invalid_format(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test workspace-policies with invalid format (missing colon)."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--workspace-policies",
                "invalidformat",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies format" in result.output

    def test_create_user_workspace_policies_empty_workspace(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test workspace-policies with empty workspace name."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--workspace-policies",
                ":template123",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies entry" in result.output

    def test_create_user_workspace_policies_empty_template(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test workspace-policies with empty template ID."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--workspace-policies",
                "workspace:",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies entry" in result.output

    def test_create_user_workspace_policies_workspace_not_found(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test workspace-policies with workspace that cannot be resolved."""
        patch_keyring(monkeypatch)

        cli = make_cli()

        with patch("slcli.user_click.resolve_workspace_id") as mock_resolve:
            mock_resolve.return_value = ""  # Workspace not found

            result = runner.invoke(
                cli,
                [
                    "user",
                    "create",
                    "--type",
                    "user",
                    "--first-name",
                    "John",
                    "--last-name",
                    "Doe",
                    "--email",
                    "john.doe@example.com",
                    "--workspace-policies",
                    "nonexistent:template123",
                ],
            )

            assert result.exit_code == 3  # NOT_FOUND
            assert "✗ Could not resolve workspace 'nonexistent'" in result.output

    def test_create_user_invalid_properties(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with invalid properties JSON."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--properties",
                "invalid-json",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid JSON format for properties." in result.output

    def test_create_user_with_prompts(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with prompts for missing required fields."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
        }
        mock_requests(monkeypatch, "post", mock_user)

        cli = make_cli()
        # Simulate user input for the prompts (including account type)
        result = runner.invoke(
            cli,
            ["user", "create"],
            input="user\nJohn\nDoe\njohn.doe@example.com\n",
        )

        assert result.exit_code == 0
        assert "Account type" in result.output
        assert "User's first name:" in result.output
        assert "User's last name:" in result.output
        assert "User's email address:" in result.output
        assert "✓ User created" in result.output
        assert "new-user-id" in result.output

    def test_create_user_partial_prompts(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with some fields provided and others prompted."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
        }
        mock_requests(monkeypatch, "post", mock_user)

        cli = make_cli()
        # Provide type and first name but prompt for last name and email
        result = runner.invoke(
            cli,
            ["user", "create", "--type", "user", "--first-name", "John"],
            input="Doe\njohn.doe@example.com\n",
        )

        assert result.exit_code == 0
        assert "User's first name:" not in result.output  # Should not prompt for first name
        assert "User's last name:" in result.output
        assert "User's email address:" in result.output
        assert "✓ User created" in result.output

    def test_create_user_invalid_email_format(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with invalid email format."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            ["user", "create"],
            input="user\nJohn\nDoe\ninvalid-email\n",
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid email format." in result.output

    def test_create_user_niua_id_defaults_to_email(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that niuaId defaults to email when not provided."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "niuaId": "john.doe@example.com",
        }

        # Capture the request payload
        captured_payload: dict[str, Any] = {}

        def mock_post_with_capture(url: str, json: Any = None, **kwargs: Any) -> Any:
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    return mock_user

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.post", mock_post_with_capture)
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created" in result.output
        # Verify that niuaId was set to email in the payload
        assert captured_payload.get("niuaId") == "john.doe@example.com"

    def test_create_user_custom_niua_id(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a user with custom niuaId."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "new-user-id",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "niuaId": "custom-niua-id",
        }

        # Capture the request payload
        captured_payload: dict[str, Any] = {}

        def mock_post_with_capture(url: str, json: Any = None, **kwargs: Any) -> Any:
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    return mock_user

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.post", mock_post_with_capture)
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
                "--niua-id",
                "custom-niua-id",
            ],
        )

        assert result.exit_code == 0
        assert "✓ User created" in result.output
        # Verify that custom niuaId was used
        assert captured_payload.get("niuaId") == "custom-niua-id"

    def test_create_user_api_validation_error(self, runner: Any, monkeypatch: Any) -> None:
        """Test handling of API validation errors."""
        patch_keyring(monkeypatch)

        # Mock an HTTP error with the specific API error format
        class MockHTTPError(Exception):
            def __init__(self) -> None:
                self.response = MockResponse()

        class MockResponse:
            def json(self) -> Any:
                return {
                    "error": {
                        "args": [],
                        "code": -254851,
                        "innerErrors": [],
                        "message": "The niuaId field is required.",
                        "name": "Auth.ValidationError",
                    }
                }

        def mock_post_with_error(*args: Any, **kwargs: Any) -> Any:
            raise MockHTTPError()

        monkeypatch.setattr("requests.post", mock_post_with_error)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "user",
                "--first-name",
                "John",
                "--last-name",
                "Doe",
                "--email",
                "john.doe@example.com",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ The niuaId field is required." in result.output


class TestUserUpdate:
    """Test user update command."""

    def test_update_user_success(self, runner: Any, monkeypatch: Any) -> None:
        """Test updating a user successfully."""
        patch_keyring(monkeypatch)
        mock_user = {
            "id": "user1",
            "firstName": "Jane",
            "lastName": "Doe",
            "email": "jane.doe@example.com",
        }
        mock_requests(monkeypatch, "put", mock_user)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "update", "--id", "user1", "--first-name", "Jane"])

        assert result.exit_code == 0
        assert "✓ User updated" in result.output

    def test_update_user_with_single_policy(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test updating a user with --policy single ID."""
        patch_keyring(monkeypatch)
        captured_payload: dict[str, Any] = {}

        def mock_put_with_capture(url: str, json: Any = None, **kwargs: Any) -> Any:
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self) -> None:
                    self.status_code = 200

                def json(self) -> Any:
                    return {"id": "user1", "email": "jane.doe@example.com"}

                def raise_for_status(self) -> None:
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.put", mock_put_with_capture)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "user1",
                "--policy",
                "policyA",
            ],
        )

        assert result.exit_code == 0
        assert captured_payload.get("policies") == ["policyA"]

    def test_update_user_with_workspace_policies(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Update user and generate workspace policies from templates."""
        patch_keyring(monkeypatch)

        def mock_get_password(service: str, key: str) -> Optional[str]:
            if key == "SYSTEMLINK_CONFIG":
                return json.dumps({"api_url": "http://localhost", "api_key": "test"})
            if key == "SYSTEMLINK_API_KEY":
                return "test"
            return None

        monkeypatch.setattr("slcli.utils.keyring.get_password", mock_get_password)

        cli = make_cli()
        runner_local = runner

        existing_user_resp = {"id": "user1", "type": "user"}
        template_resp = {"id": "template-qa-123", "name": "templateQA"}
        policy_resp = {"id": "pol-ws-2", "name": "generated"}
        user_resp = {"id": "user1", "email": "jane.doe@example.com"}

        with patch("slcli.user_click.make_api_request") as mock_request, patch(
            "slcli.user_click.resolve_workspace_id"
        ) as mock_resolve:
            # First: get user, Second: template lookup, Third: policy creation, Fourth: update
            mock_request.side_effect = [
                mock_response(existing_user_resp),
                mock_response({"policyTemplates": [template_resp]}),
                mock_response(policy_resp),
                mock_response(user_resp),
            ]
            mock_resolve.return_value = "qa"

            result = runner_local.invoke(
                cli,
                [
                    "user",
                    "update",
                    "--id",
                    "user1",
                    "--workspace-policies",
                    "qa:templateQA",
                ],
            )

            assert result.exit_code == 0
            assert len(mock_request.call_args_list) == 4
            user_call = mock_request.call_args_list[3]
            payload = user_call.kwargs.get("payload")
            assert payload
            assert payload.get("policies") == ["pol-ws-2"]

    def test_update_user_workspace_policies_invalid_format(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test update with workspace-policies invalid format (missing colon)."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "user1",
                "--workspace-policies",
                "invalidformat",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies format" in result.output

    def test_update_user_workspace_policies_empty_workspace(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test update with workspace-policies with empty workspace name."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "user1",
                "--workspace-policies",
                ":template123",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies entry" in result.output

    def test_update_user_workspace_policies_empty_template(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test update with workspace-policies with empty template ID."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "user1",
                "--workspace-policies",
                "workspace:",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid workspace-policies entry" in result.output

    def test_update_user_workspace_policies_workspace_not_found(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test update with workspace-policies with workspace that cannot be resolved."""
        patch_keyring(monkeypatch)

        cli = make_cli()

        with patch("slcli.user_click.resolve_workspace_id") as mock_resolve:
            mock_resolve.return_value = ""  # Workspace not found

            result = runner.invoke(
                cli,
                [
                    "user",
                    "update",
                    "--id",
                    "user1",
                    "--workspace-policies",
                    "nonexistent:template123",
                ],
            )

            assert result.exit_code == 3  # NOT_FOUND
            assert "✗ Could not resolve workspace 'nonexistent'" in result.output

    def test_update_user_no_fields(self, runner: Any, monkeypatch: Any) -> None:
        """Test updating a user with no fields provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "update", "--id", "user1"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ No fields provided to update." in result.output

    def test_update_user_invalid_properties(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test updating a user with invalid properties JSON."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "user1",
                "--properties",
                "invalid-json",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid JSON format for properties." in result.output


class TestUserDelete:
    """Test user delete command."""

    def test_delete_user_success(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test deleting a user successfully."""
        patch_keyring(monkeypatch)
        mock_requests(monkeypatch, "delete", {})

        cli = make_cli()
        # Use --yes to bypass confirmation prompt in tests
        result = runner.invoke(cli, ["user", "delete", "--id", "user1", "--yes"])

        assert result.exit_code == 0
        assert "✓ User deleted" in result.output
        assert "user1" in result.output

    def test_delete_user_cancelled(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test deleting a user when cancelled."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        # Simulate user cancelling the confirmation
        result = runner.invoke(cli, ["user", "delete", "--id", "user1"], input="n\n")

        assert result.exit_code == 1  # Cancelled by user
        assert "Aborted!" in result.output


class TestServiceAccounts:
    """Test service account support in user commands."""

    def test_create_service_account_success(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test creating a service account successfully (lastName defaults to ServiceAccount)."""
        patch_keyring(monkeypatch)

        mock_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "CI Bot",
            "lastName": "ServiceAccount",
            "status": "active",
        }

        captured_payload: dict[str, Any] = {}

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payload.update(kw.get("json", {}))

            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return mock_service_account

            return R()

        monkeypatch.setattr("requests.post", mock_post)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "service",
                "--first-name",
                "CI Bot",
            ],
        )

        assert result.exit_code == 0
        assert "✓ Service account created" in result.output
        assert "CI Bot" in result.output
        # Verify lastName was defaulted to ServiceAccount
        assert captured_payload.get("lastName") == "ServiceAccount"

    def test_create_service_account_rejects_email(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that service accounts reject email field."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "service",
                "--first-name",
                "CI Bot",
                "--email",
                "bot@example.com",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Service accounts cannot have: --email" in result.output

    def test_create_service_account_rejects_multiple_invalid_fields(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that service accounts reject multiple invalid fields."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
                "--type",
                "service",
                "--first-name",
                "CI Bot",
                "--email",
                "bot@example.com",
                "--phone",
                "555-1234",
            ],
        )

        assert result.exit_code == 2
        assert "--email" in result.output
        assert "--phone" in result.output

    def test_list_users_with_type_filter_service(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test listing users filtered by service type."""
        patch_keyring(monkeypatch)

        mock_users: dict[str, Any] = {
            "users": [
                {
                    "id": "svc1",
                    "type": "service",
                    "firstName": "CI Bot",
                    "lastName": "",
                    "email": "",
                    "status": "active",
                }
            ]
        }
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list", "--type", "service"])

        assert result.exit_code == 0
        assert "CI Bot" in result.output
        assert "Service" in result.output

    def test_list_users_shows_type_column(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test that list users shows the Type column."""
        patch_keyring(monkeypatch)

        mock_users: dict[str, Any] = {
            "users": [
                {
                    "id": "user1",
                    "type": "user",
                    "firstName": "John",
                    "lastName": "Doe",
                    "email": "john@example.com",
                    "status": "active",
                },
                {
                    "id": "svc1",
                    "type": "service",
                    "firstName": "CI Bot",
                    "lastName": "",
                    "email": "",
                    "status": "active",
                },
            ]
        }
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list"])

        assert result.exit_code == 0
        assert "Type" in result.output  # Type column header
        assert "User" in result.output  # User type
        assert "Service" in result.output  # Service type

    def test_get_service_account_shows_type(self, runner: CliRunner, monkeypatch: Any) -> None:
        """Test that get command shows type for service accounts."""
        patch_keyring(monkeypatch)

        mock_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "CI Bot",
            "lastName": "",
            "status": "active",
            "orgId": "org1",
        }

        def mock_get(*a: Any, **kw: Any) -> Any:
            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return mock_service_account

            return R()

        monkeypatch.setattr("requests.get", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "svc1"])

        assert result.exit_code == 0
        assert "Service Account Details:" in result.output
        assert "Type: Service Account" in result.output
        # Should not show email, phone, login for service accounts
        assert "Email:" not in result.output

    def test_update_service_account_rejects_email(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that updating a service account rejects email field."""
        patch_keyring(monkeypatch)

        mock_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "CI Bot",
            "status": "active",
        }

        def mock_get(*a: Any, **kw: Any) -> Any:
            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return mock_service_account

            return R()

        monkeypatch.setattr("requests.get", mock_get)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "svc1",
                "--email",
                "bot@example.com",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Service accounts cannot be updated with: --email" in result.output

    def test_update_service_account_allows_first_name(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that updating a service account allows first-name."""
        patch_keyring(monkeypatch)

        mock_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "CI Bot",
            "status": "active",
        }

        updated_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "Deploy Bot",
            "status": "active",
        }

        call_count = [0]

        def mock_get(*a: Any, **kw: Any) -> Any:
            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return mock_service_account

            return R()

        def mock_put(*a: Any, **kw: Any) -> Any:
            call_count[0] += 1

            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return updated_service_account

            return R()

        monkeypatch.setattr("requests.get", mock_get)
        monkeypatch.setattr("requests.put", mock_put)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "svc1",
                "--first-name",
                "Deploy Bot",
            ],
        )

        assert result.exit_code == 0
        assert "✓ Service account updated" in result.output
        assert call_count[0] == 1  # PUT was called

    def test_update_service_account_rejects_accepted_tos(
        self, runner: CliRunner, monkeypatch: Any
    ) -> None:
        """Test that updating a service account rejects accepted-tos field."""
        patch_keyring(monkeypatch)

        mock_service_account = {
            "id": "svc1",
            "type": "service",
            "firstName": "CI Bot",
            "status": "active",
        }

        def mock_get(*a: Any, **kw: Any) -> Any:
            class R:
                status_code = 200

                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
                    return mock_service_account

            return R()

        monkeypatch.setattr("requests.get", mock_get)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "update",
                "--id",
                "svc1",
                "--accepted-tos",
                "true",
            ],
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "Service accounts cannot be updated with: --accepted-tos" in result.output

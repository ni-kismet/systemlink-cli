"""Unit tests for user CLI commands."""

import json

import click
import pytest
from click.testing import CliRunner

from slcli.user_click import register_user_commands


def patch_keyring(monkeypatch):
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def make_cli():
    """Create CLI instance with user commands for testing."""

    @click.group()
    def test_cli():
        pass

    register_user_commands(test_cli)
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

    monkeypatch.setattr("requests." + method.lower(), lambda *a, **kw: MockResponse())


class TestUserList:
    """Test user list command."""

    def test_list_users_table_format(self, runner, monkeypatch):
        """Test listing users in table format."""
        patch_keyring(monkeypatch)
        mock_users = {
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

    def test_list_users_json_format(self, runner, monkeypatch):
        """Test listing users in JSON format."""
        patch_keyring(monkeypatch)
        mock_users = {
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

    def test_list_users_with_filter(self, runner, monkeypatch):
        """Test listing users with filter."""
        patch_keyring(monkeypatch)
        mock_users = {"users": []}
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list", "--filter", 'firstName.StartsWith("John")'])

        assert result.exit_code == 0
        assert "No users found." in result.output

    def test_list_users_empty_result(self, runner, monkeypatch):
        """Test listing users with empty result."""
        patch_keyring(monkeypatch)
        mock_users = {"users": []}
        mock_requests(monkeypatch, "post", mock_users)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "list"])

        assert result.exit_code == 0
        assert "No users found." in result.output


class TestUserGet:
    """Test user get command."""

    def test_get_user_table_format(self, runner, monkeypatch):
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

        def mock_requests_func(method, *args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    return mock_user

                def raise_for_status(self):
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "User Details:" in result.output
        assert "John" in result.output
        assert "john.doe@example.com" in result.output

    def test_get_user_with_policies_table_format(self, runner, monkeypatch):
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

        def mock_requests_func(url, *args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        # Extract policy ID from URL
                        policy_id = url.split("/")[-1]
                        return mock_policies.get(policy_id, {})
                    return {}

                def raise_for_status(self):
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "User Details:" in result.output
        assert "Policies:" in result.output
        assert "Admin Policy" in result.output

    def test_get_user_with_policies_json_format(self, runner, monkeypatch):
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

        def mock_requests_func(url, *args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy
                    return {}

                def raise_for_status(self):
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

    def test_get_user_with_policy_templates(self, runner, monkeypatch):
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

        def mock_requests_func(url, *args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy_with_template
                    elif "/policy-templates/" in url:
                        return mock_template
                    return {}

                def raise_for_status(self):
                    pass

            return MockResponse()

        monkeypatch.setattr("requests.get", mock_requests_func)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--id", "user1"])

        assert result.exit_code == 0
        assert "Template-based Policy" in result.output
        assert "Template: Admin Template" in result.output
        assert "Full admin access via template" in result.output

    def test_get_user_with_policy_templates_json_format(self, runner, monkeypatch):
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

        def mock_requests_func(url, *args, **kwargs):
            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    if "/users/" in url:
                        return mock_user
                    elif "/policies/" in url:
                        return mock_policy_with_template
                    elif "/policy-templates/" in url:
                        return mock_template
                    return {}

                def raise_for_status(self):
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

    def test_get_user_json_format(self, runner, monkeypatch):
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

    def test_get_user_by_email_table_format(self, runner, monkeypatch):
        """Test getting user details by email in table format."""
        patch_keyring(monkeypatch)
        mock_query_response = {
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

    def test_get_user_by_email_json_format(self, runner, monkeypatch):
        """Test getting user details by email in JSON format."""
        patch_keyring(monkeypatch)
        mock_query_response = {
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

    def test_get_user_by_email_not_found(self, runner, monkeypatch):
        """Test getting user by email when user not found."""
        patch_keyring(monkeypatch)
        mock_query_response = {"users": []}
        mock_requests(monkeypatch, "post", mock_query_response)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get", "--email", "nonexistent@example.com"])

        assert result.exit_code == 3  # NOT_FOUND
        assert "✗ User with email 'nonexistent@example.com' not found." in result.output

    def test_get_user_no_params(self, runner, monkeypatch):
        """Test getting user with no ID or email provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "get"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Must provide either --id or --email." in result.output

    def test_get_user_both_params(self, runner, monkeypatch):
        """Test getting user with both ID and email provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli, ["user", "get", "--id", "user1", "--email", "john.doe@example.com"]
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Cannot specify both --id and --email. Choose one." in result.output

    def test_get_user_permission_denied(self, runner, monkeypatch):
        """Test getting user when access is denied."""
        patch_keyring(monkeypatch)

        # Mock a 401 Unauthorized response
        def mock_requests_func(url, *args, **kwargs):
            import requests

            class MockResponse:
                def __init__(self):
                    self.status_code = 401

                def json(self):
                    return {
                        "error": {
                            "args": [],
                            "code": -254850,
                            "innerErrors": [],
                            "message": "Not allowed to access resource.",
                            "name": "Unauthorized",
                        }
                    }

                def raise_for_status(self):
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

    def test_get_user_with_policy_permission_errors(self, runner, monkeypatch):
        """Test getting user with policies when policy access is denied."""
        patch_keyring(monkeypatch)

        def mock_requests_func(url, *args, **kwargs):
            import requests

            class MockResponse:
                def __init__(self):
                    if "/niauth/v1/policies/" in url:
                        # Policy access denied
                        self.status_code = 401
                    else:
                        # User access allowed
                        self.status_code = 200

                def json(self):
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

                def raise_for_status(self):
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

    def test_create_user_success(self, runner, monkeypatch):
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

    def test_create_user_with_policies(self, runner, monkeypatch):
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

    def test_create_user_invalid_properties(self, runner, monkeypatch):
        """Test creating a user with invalid properties JSON."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
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

    def test_create_user_with_prompts(self, runner, monkeypatch):
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
        # Simulate user input for the prompts
        result = runner.invoke(
            cli,
            ["user", "create"],
            input="John\nDoe\njohn.doe@example.com\n",
        )

        assert result.exit_code == 0
        assert "User's first name:" in result.output
        assert "User's last name:" in result.output
        assert "User's email address:" in result.output
        assert "✓ User created" in result.output
        assert "new-user-id" in result.output

    def test_create_user_partial_prompts(self, runner, monkeypatch):
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
        # Provide first name but prompt for last name and email
        result = runner.invoke(
            cli,
            ["user", "create", "--first-name", "John"],
            input="Doe\njohn.doe@example.com\n",
        )

        assert result.exit_code == 0
        assert "User's first name:" not in result.output  # Should not prompt for first name
        assert "User's last name:" in result.output
        assert "User's email address:" in result.output
        assert "✓ User created" in result.output

    def test_create_user_invalid_email_format(self, runner, monkeypatch):
        """Test creating a user with invalid email format."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            ["user", "create"],
            input="John\nDoe\ninvalid-email\n",
        )

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ Invalid email format." in result.output

    def test_create_user_niua_id_defaults_to_email(self, runner, monkeypatch):
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
        captured_payload = {}

        def mock_post_with_capture(url, json=None, **kwargs):
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    return mock_user

                def raise_for_status(self):
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

    def test_create_user_custom_niua_id(self, runner, monkeypatch):
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
        captured_payload = {}

        def mock_post_with_capture(url, json=None, **kwargs):
            captured_payload.update(json or {})

            class MockResponse:
                def __init__(self):
                    self.status_code = 200

                def json(self):
                    return mock_user

                def raise_for_status(self):
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

    def test_create_user_api_validation_error(self, runner, monkeypatch):
        """Test handling of API validation errors."""
        patch_keyring(monkeypatch)

        # Mock an HTTP error with the specific API error format
        class MockHTTPError(Exception):
            def __init__(self):
                self.response = MockResponse()

        class MockResponse:
            def json(self):
                return {
                    "error": {
                        "args": [],
                        "code": -254851,
                        "innerErrors": [],
                        "message": "The niuaId field is required.",
                        "name": "Auth.ValidationError",
                    }
                }

        def mock_post_with_error(*args, **kwargs):
            raise MockHTTPError()

        monkeypatch.setattr("requests.post", mock_post_with_error)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "user",
                "create",
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

    def test_update_user_success(self, runner, monkeypatch):
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

    def test_update_user_no_fields(self, runner, monkeypatch):
        """Test updating a user with no fields provided."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["user", "update", "--id", "user1"])

        assert result.exit_code == 2  # INVALID_INPUT
        assert "✗ No fields provided to update." in result.output

    def test_update_user_invalid_properties(self, runner, monkeypatch):
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

    def test_delete_user_success(self, runner, monkeypatch):
        """Test deleting a user successfully."""
        patch_keyring(monkeypatch)
        mock_requests(monkeypatch, "delete", {})

        cli = make_cli()
        # Use --yes to bypass confirmation prompt in tests
        result = runner.invoke(cli, ["user", "delete", "--id", "user1", "--yes"])

        assert result.exit_code == 0
        assert "✓ User deleted" in result.output
        assert "user1" in result.output

    def test_delete_user_cancelled(self, runner, monkeypatch):
        """Test deleting a user when cancelled."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        # Simulate user cancelling the confirmation
        result = runner.invoke(cli, ["user", "delete", "--id", "user1"], input="n\n")

        assert result.exit_code == 1  # Cancelled by user
        assert "Aborted!" in result.output

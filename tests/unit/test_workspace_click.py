"""Unit tests for workspace CLI commands."""

import json
from typing import Any
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

import click
import pytest
from click.testing import CliRunner

from slcli.workspace_click import register_workspace_commands


@pytest.mark.parametrize("name", ["R&D", "a+b #1", "Lab/\u6e2c\u8a66"])
def test_workspace_filter_is_url_encoded(monkeypatch: Any, name: str) -> None:
    """Workspace names remain one query value even when they contain URL delimiters."""
    from slcli.workspace_click import _fetch_workspaces_page

    request = Mock()
    request.return_value.json.return_value = {"workspaces": [], "totalCount": 0}
    monkeypatch.setattr("slcli.workspace_click.get_base_url", lambda: "https://example.com")
    monkeypatch.setattr("slcli.workspace_click.make_api_request", request)

    assert _fetch_workspaces_page(name) == ([], 0, None)
    query = parse_qs(urlparse(request.call_args.args[1]).query)
    assert query == {"take": ["25"], "skip": ["0"], "name": [f"*{name}*"]}


@pytest.mark.parametrize("output_format", ["table", "json"])
@pytest.mark.parametrize("take,disabled_count", [(200, 0), (1, 1)])
def test_workspace_pagination_preserves_matching_records(
    monkeypatch: Any, output_format: str, take: int, disabled_count: int
) -> None:
    """Capped requests and disabled-only pages cannot skip later matching workspaces."""
    fetched_offsets = []
    records = [{"id": f"ws-{index}", "enabled": index >= disabled_count} for index in range(250)]

    def request(method: str, url: str, **kwargs: Any) -> Mock:
        query = parse_qs(urlparse(url).query)
        size = int(query["take"][0])
        skip = int(query["skip"][0])
        fetched_offsets.append(skip)
        response = Mock()
        response.json.return_value = {
            "workspaces": records[skip : skip + size],
            "totalCount": len(records),
        }
        return response

    displayed = []
    monkeypatch.setattr("slcli.workspace_click.get_base_url", lambda: "https://example.com")
    monkeypatch.setattr("slcli.workspace_click.make_api_request", request)
    monkeypatch.setattr("slcli.workspace_click.is_interactive_environment", lambda: True)
    monkeypatch.setattr("slcli.workspace_click.click.confirm", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "slcli.table_utils.output_formatted_list", lambda items, *args: displayed.extend(items)
    )

    result = CliRunner().invoke(
        make_cli(), ["workspace", "list", "--format", output_format, "--take", str(take)]
    )
    assert result.exit_code == 0, result.output
    expected = records[disabled_count:]
    if output_format == "json":
        assert json.loads(result.output) == expected[:take]
    else:
        assert displayed == expected
    if take > 100:
        assert fetched_offsets[:2] == [0, 100]


def test_workspace_empty_filtered_result_is_explicit(monkeypatch: Any) -> None:
    """An exhausted disabled-only result has one clear empty state."""
    monkeypatch.setattr(
        "slcli.workspace_click._fetch_workspaces_page",
        lambda *args, **kwargs: ([{"id": "disabled", "enabled": False}], 1, None),
    )
    result = CliRunner().invoke(make_cli(), ["workspace", "list"])
    assert result.exit_code == 0
    assert result.output.strip() == "No workspaces found."


def patch_keyring(monkeypatch: Any) -> None:
    """Set environment credentials used by CLI tests."""
    monkeypatch.setenv("SLCLI_API_KEY", "test-key")
    monkeypatch.setenv("SLCLI_API_URL", "https://test.com")


def make_cli() -> click.Group:
    """Create CLI instance with workspace commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_workspace_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
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

    monkeypatch.setattr("requests." + method, lambda *a, **kw: MockResponse())


def test_list_workspaces_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing workspaces with a successful response."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
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
                    ],
                    "totalCount": 2,
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    # Provide "n" input to decline showing more pages
    result = runner.invoke(cli, ["workspace", "list"], input="n\n")
    assert result.exit_code == 0
    assert "Workspace 1" in result.output
    assert "Workspace 2" not in result.output  # Disabled workspace filtered out


def test_list_workspaces_include_disabled(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing workspaces including disabled ones."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
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
                    ],
                    "totalCount": 2,
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list", "--include-disabled"])
    assert result.exit_code == 0
    assert "Workspace 1" in result.output
    assert "Workspace 2" in result.output  # Disabled workspace included


def test_list_workspaces_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing workspaces with JSON output."""
    patch_keyring(monkeypatch)

    call_count = 0

    def mock_get(*a: Any, **kw: Any) -> Any:
        nonlocal call_count
        call_count += 1

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Workspace 1",
                            "enabled": True,
                            "default": True,
                        }
                    ],
                    "totalCount": 1,
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
    # Verify only one API call was made for JSON format
    assert call_count == 1


def test_list_workspaces_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing workspaces when none exist."""
    patch_keyring(monkeypatch)

    call_count = 0

    def mock_get(*a: Any, **kw: Any) -> Any:
        nonlocal call_count
        call_count += 1

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [], "totalCount": 0}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "list"])
    assert result.exit_code == 0
    assert "No workspaces found." in result.output
    # Verify only one API call was made
    assert call_count == 1


def test_disable_workspace_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test disabling a workspace successfully."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {"id": "test-ws-id", "name": "Test Workspace", "enabled": True},
                        {"id": "other-ws", "name": "Other Workspace", "enabled": True},
                    ],
                    "totalCount": 2,
                }

        return R()

    def mock_put(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"id": "test-ws-id", "name": "Test Workspace", "enabled": False}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "disable", "--id", "test-ws-id"], input="y\n")
    assert result.exit_code == 0
    assert "Workspace 'Test Workspace' disabled successfully" in result.output


def test_disable_workspace_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Test disabling a workspace that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": []}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "disable", "--id", "nonexistent-id"], input="y\n")
    assert result.exit_code == 3  # NOT_FOUND exit code
    assert "Workspace with ID 'nonexistent-id' not found" in result.output


def test_disable_workspace_already_disabled(monkeypatch: Any, runner: CliRunner) -> None:
    """Test disabling a workspace that is already disabled."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
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


def test_get_workspace_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting workspace details successfully."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {
                            "id": "test-ws-id",
                            "name": "Test Workspace",
                            "enabled": True,
                            "default": False,
                        },
                    ],
                    "totalCount": 1,
                }

        return R()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
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
    result = runner.invoke(cli, ["workspace", "get", "--workspace", "test-ws-id"])
    assert result.exit_code == 0
    assert "Workspace Information: Test Workspace" in result.output
    assert "Test Plan Templates (1)" in result.output
    assert "Workflows (1)" in result.output


def test_get_workspace_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting details for workspace that doesn't exist."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [], "totalCount": 0}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workspace", "get", "--workspace", "nonexistent"])
    assert result.exit_code == 3  # NOT_FOUND exit code
    assert "Workspace 'nonexistent' not found" in result.output


def test_get_workspace_with_permission_errors(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting workspace info when some resources have permission errors."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {
                            "id": "test-ws-id",
                            "name": "Test Workspace",
                            "enabled": True,
                            "default": False,
                        },
                    ],
                    "totalCount": 1,
                }

        return R()

    def mock_post(*a: Any, **kw: Any) -> Any:
        if "testplan-templates" in str(a):
            # Simulate permission error for templates
            raise Exception("401 Unauthorized")
        elif "workflows" in str(a):
            # Return successful response for workflows
            class R:
                def raise_for_status(self) -> None:
                    pass

                def json(self) -> Any:
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
    result = runner.invoke(cli, ["workspace", "get", "--workspace", "test-ws-id"])
    assert result.exit_code == 0
    assert "Workspace Information: Test Workspace" in result.output
    assert "Test Plan Templates (0)" in result.output
    assert "Access denied (insufficient permissions)" in result.output
    assert "Workflows (1)" in result.output
    assert "Test Workflow" in result.output
    assert "Notebooks (0)" in result.output
    assert "Access forbidden" in result.output

    # Test JSON format includes access_errors
    result = runner.invoke(
        cli, ["workspace", "get", "--workspace", "test-ws-id", "--format", "json"]
    )
    assert result.exit_code == 0
    import json

    output_data = json.loads(result.output)
    assert "access_errors" in output_data
    assert output_data["access_errors"]["templates"] == "Access denied (insufficient permissions)"
    assert output_data["access_errors"]["notebooks"] == "Access forbidden"
    assert "workflows" not in output_data["access_errors"]  # Should not have workflow errors


def test_list_workspaces_with_filter(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing workspaces with --filter flag using server-side filtering."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        # Verify that the API is being called with the *TEXT* filter pattern
        url = a[0] if a else ""
        if "name=*prod*" in url:
            # Filtered response
            workspaces = [
                {
                    "id": "ws1",
                    "name": "Production Workspace",
                    "enabled": True,
                    "default": False,
                },
                {
                    "id": "ws3",
                    "name": "Production Data",
                    "enabled": True,
                    "default": False,
                },
            ]
        else:
            # No filter
            workspaces = [
                {
                    "id": "ws1",
                    "name": "Production Workspace",
                    "enabled": True,
                    "default": False,
                },
                {
                    "id": "ws2",
                    "name": "Test Workspace",
                    "enabled": True,
                    "default": False,
                },
                {
                    "id": "ws3",
                    "name": "Production Data",
                    "enabled": True,
                    "default": False,
                },
            ]

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": workspaces, "totalCount": len(workspaces)}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    # Test filter for "prod" (server-side filtering with *TEXT* pattern)
    result = runner.invoke(cli, ["workspace", "list", "--filter", "prod"])
    assert result.exit_code == 0
    assert "Production Workspace" in result.output
    assert "Production Data" in result.output
    assert "Test Workspace" not in result.output


def test_list_workspaces_filter_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test --filter flag with JSON output using server-side filtering."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {
                            "id": "ws1",
                            "name": "Production A",
                            "enabled": True,
                            "default": False,
                        },
                        {
                            "id": "ws3",
                            "name": "Production C",
                            "enabled": True,
                            "default": False,
                        },
                    ],
                    "totalCount": 2,
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    result = runner.invoke(cli, ["workspace", "list", "--filter", "production", "--format", "json"])
    assert result.exit_code == 0

    output_data = json.loads(result.output)
    assert len(output_data) == 2
    assert all("Production" in ws["name"] for ws in output_data)


def test_list_workspaces_take_limits_api_calls(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that --take parameter limits API requests, not just display."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        url = a[0] if a else ""
        # Verify that take parameter is being sent to API
        assert "take=" in url

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # Parse the take parameter to verify it's being respected
                if "take=25" in url:
                    # Return exactly 25 items
                    return {
                        "workspaces": [
                            {
                                "id": f"ws{i}",
                                "name": f"Workspace {i}",
                                "enabled": True,
                                "default": False,
                            }
                            for i in range(1, 26)
                        ],
                        "totalCount": 25,
                    }
                elif "take=50" in url:
                    # Return exactly 50 items
                    return {
                        "workspaces": [
                            {
                                "id": f"ws{i}",
                                "name": f"Workspace {i}",
                                "enabled": True,
                                "default": False,
                            }
                            for i in range(1, 51)
                        ],
                        "totalCount": 50,
                    }
                else:
                    return {"workspaces": [], "totalCount": 0}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    # Test that --take 50 is passed to API
    result = runner.invoke(cli, ["workspace", "list", "--take", "50"])
    assert result.exit_code == 0
    # Verify that the API was called with the take parameter
    assert "Workspace 1" in result.output


def test_list_workspaces_filter_uses_server_side(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that filtering uses server-side API with *TEXT* pattern."""
    patch_keyring(monkeypatch)

    called_with_filter = False

    def mock_get(*a: Any, **kw: Any) -> Any:
        nonlocal called_with_filter
        url = a[0] if a else ""
        if "name=*test*" in url:
            called_with_filter = True

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                if "name=*test*" in url:
                    # Server has already filtered
                    return {
                        "workspaces": [
                            {
                                "id": "ws1",
                                "name": "Test Workspace A",
                                "enabled": True,
                                "default": False,
                            },
                            {
                                "id": "ws2",
                                "name": "Production Test",
                                "enabled": True,
                                "default": False,
                            },
                        ],
                        "totalCount": 2,
                    }
                else:
                    return {"workspaces": [], "totalCount": 0}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    # Test filter with uppercase (should convert to lowercase for API)
    result = runner.invoke(cli, ["workspace", "list", "--filter", "test"])
    assert result.exit_code == 0
    assert called_with_filter  # Verify server-side filter was used


def test_list_workspaces_lazy_loading(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that workspace list uses lazy loading - only fetches first page initially."""
    patch_keyring(monkeypatch)

    api_call_count = 0

    def mock_get(*a: Any, **kw: Any) -> Any:
        nonlocal api_call_count
        api_call_count += 1
        url = a[0] if a else ""

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # Simulate 100 total workspaces, but only return the requested page
                if "skip=0" in url:
                    # First page
                    return {
                        "workspaces": [
                            {
                                "id": f"ws{i}",
                                "name": f"Workspace {i}",
                                "enabled": True,
                                "default": False,
                            }
                            for i in range(1, 26)  # 25 workspaces
                        ],
                        "totalCount": 100,  # Indicate there are more
                    }
                else:
                    # Shouldn't be called since we're not clicking "yes" to continue
                    return {"workspaces": [], "totalCount": 100}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    cli = make_cli()

    # List workspaces in table format without clicking "yes" to continue
    result = runner.invoke(cli, ["workspace", "list"], input="n\n")
    assert result.exit_code == 0

    # Verify only ONE API call was made (for the first page)
    assert api_call_count == 1, f"Expected 1 API call, but got {api_call_count}"

    # Verify first page content is displayed
    assert "Workspace 1" in result.output
    assert "Workspace 25" in result.output

    # Verify pagination prompt was shown
    assert "Showing 25 workspace(s) so far" in result.output

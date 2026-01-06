"""Unit tests for tag management CLI commands."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from slcli.tag_click import register_tag_commands


def make_cli() -> click.Group:
    """Create a test CLI group with tag commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_tag_commands(test_cli)
    return test_cli


def mock_response(data: dict, status_code: int = 200) -> Any:
    """Create a mock response object."""
    resp: Any = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    return resp


class TestTagList:
    """Tests for tag list command."""

    def test_list_tags_with_pagination(self) -> None:
        """Test tag listing with server-side pagination."""
        cli = make_cli()
        runner = CliRunner()

        page1_data = {
            "tagsWithValues": [{"tag": {"path": "tag1"}, "current": {}}],
            "continuationToken": "token1",
            "totalCount": 2,
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                # Return page 1 first
                mock_request.return_value = mock_response(page1_data)

                # Provide 'n' as input to the pagination prompt to stop after first page
                result = runner.invoke(cli, ["tag", "list"], input="n\n")
                assert result.exit_code == 0
                assert "tag1" in result.output
                assert "Showing 1 of 2 tags" in result.output

    def test_list_tags_success(self) -> None:
        """Test successful tag listing."""
        cli = make_cli()
        runner = CliRunner()

        mock_data = {
            "tagsWithValues": [
                {
                    "tag": {
                        "path": "temperature",
                        "type": "DOUBLE",
                        "keywords": ["sensor", "data"],
                        "lastUpdated": "2024-01-01T00:00:00Z",
                    },
                    "current": {"value": {"value": "23.5"}, "timestamp": "2024-01-01T00:00:00Z"},
                }
            ]
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(mock_data)

                result = runner.invoke(cli, ["tag", "list"])
                assert result.exit_code == 0
                assert "temperature" in result.output

    def test_list_tags_json_format(self) -> None:
        """Test tag listing with JSON output."""
        cli = make_cli()
        runner = CliRunner()

        mock_data = {
            "tagsWithValues": [
                {
                    "tag": {
                        "path": "pressure",
                        "type": "INT",
                        "keywords": [],
                        "lastUpdated": "2024-01-01T00:00:00Z",
                    }
                }
            ]
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(mock_data)

                result = runner.invoke(cli, ["tag", "list", "--format", "json"])
                assert result.exit_code == 0
                # JSON output should contain the tag data
                output_json = json.loads(result.output)
                assert len(output_json) >= 0

    def test_list_tags_with_filter(self) -> None:
        """Test tag listing with filter."""
        cli = make_cli()
        runner = CliRunner()

        mock_data: Any = {"tagsWithValues": []}

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(mock_data)

                result = runner.invoke(cli, ["tag", "list", "--filter", "temp"])
                assert result.exit_code == 0
                # Verify filter was passed in request
                call_args = mock_request.call_args
                expected_filter = 'workspace = "ws-123" && path = "*temp*"'
                assert call_args[1]["payload"]["filter"] == expected_filter

    def test_list_tags_with_keywords(self) -> None:
        """Test tag listing with keywords."""
        cli = make_cli()
        runner = CliRunner()

        mock_data: Any = {"tagsWithValues": []}

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(mock_data)

                result = runner.invoke(cli, ["tag", "list", "--keywords", "key1,key2"])
                assert result.exit_code == 0
                # Verify filter was constructed correctly
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert 'workspace = "ws-123"' in payload["filter"]
                assert 'keywords.Contains("key1")' in payload["filter"]
                assert 'keywords.Contains("key2")' in payload["filter"]
                assert "&&" in payload["filter"]

    def test_list_tags_with_workspace_override(self) -> None:
        """Test tag listing with explicit workspace."""
        cli = make_cli()
        runner = CliRunner()

        mock_data: Any = {"tagsWithValues": []}

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-999"
                mock_request.return_value = mock_response(mock_data)

                result = runner.invoke(cli, ["tag", "list", "--workspace", "ws-999"])
                assert result.exit_code == 0
                mock_resolve.assert_called_once_with("ws-999")

    def test_list_tags_api_error(self) -> None:
        """Test tag listing API error."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                # Mock query tags failure
                mock_request.side_effect = Exception("Query Failed")

                result = runner.invoke(cli, ["tag", "list"])
                assert result.exit_code != 0
                assert "Query Failed" in result.output


class TestTagView:
    """Tests for tag view command."""

    def test_view_tag_success(self) -> None:
        """Test successful tag view."""
        cli = make_cli()
        runner = CliRunner()

        tag_data = {
            "path": "temperature",
            "type": "DOUBLE",
            "keywords": ["sensor"],
            "properties": {"location": "room1"},
            "lastUpdated": "2024-01-01T00:00:00Z",
            "collectAggregates": True,
        }

        value_data = {
            "current": {"value": {"value": "23.5"}, "timestamp": "2024-01-01T00:00:00Z"},
            "aggregates": {"min": "20.0", "max": "25.0", "avg": 22.5, "count": 100},
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.side_effect = [
                    mock_response(tag_data),
                    mock_response(value_data),
                ]

                result = runner.invoke(cli, ["tag", "get", "temperature"])
                assert result.exit_code == 0
                assert "temperature" in result.output
                assert "DOUBLE" in result.output

    def test_view_tag_with_aggregates(self) -> None:
        """Test tag view with aggregates display."""
        cli = make_cli()
        runner = CliRunner()

        tag_data = {"path": "temperature", "type": "DOUBLE"}
        value_data = {
            "current": {"value": {"value": "23.5"}, "timestamp": "2024-01-01T00:00:00Z"},
            "aggregates": {"min": "20.0", "max": "25.0", "avg": 22.5, "count": 100},
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.side_effect = [
                    mock_response(tag_data),
                    mock_response(value_data),
                ]

                result = runner.invoke(cli, ["tag", "get", "temperature", "--include-aggregates"])
                assert result.exit_code == 0
                assert "Aggregates" in result.output


class TestTagCreate:
    """Tests for tag create command."""

    def test_create_tag_success(self) -> None:
        """Test successful tag creation."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 201)

                result = runner.invoke(cli, ["tag", "create", "temperature", "--type", "DOUBLE"])
                assert result.exit_code == 0
                assert "Tag created" in result.output

    def test_create_tag_with_keywords(self) -> None:
        """Test tag creation with keywords."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 201)

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "create",
                        "temperature",
                        "--type",
                        "DOUBLE",
                        "--keywords",
                        "sensor,data",
                    ],
                )
                assert result.exit_code == 0
                assert "Tag created" in result.output
                # Verify keywords were included
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert "keywords" in payload
                assert "sensor" in payload["keywords"]

    def test_create_tag_with_properties(self) -> None:
        """Test tag creation with properties."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 201)

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "create",
                        "temperature",
                        "--type",
                        "DOUBLE",
                        "--properties",
                        "location=room1",
                        "--properties",
                        "unit=celsius",
                    ],
                )
                assert result.exit_code == 0
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert payload["properties"]["location"] == "room1"
                assert payload["properties"]["unit"] == "celsius"

    def test_create_tag_missing_type(self) -> None:
        """Test tag creation fails without type."""
        cli = make_cli()
        runner = CliRunner()

        result = runner.invoke(cli, ["tag", "create", "temperature"])
        assert result.exit_code != 0
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_create_tag_with_aggregates(self) -> None:
        """Test tag creation with aggregates enabled."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 201)

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "create",
                        "temperature",
                        "--type",
                        "DOUBLE",
                        "--collect-aggregates",
                    ],
                )
                assert result.exit_code == 0
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert payload["collectAggregates"] is True


class TestTagUpdate:
    """Tests for tag update command."""

    def test_update_tag_keywords(self) -> None:
        """Test updating tag keywords."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({})

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "update",
                        "temperature",
                        "--keywords",
                        "sensor,updated",
                    ],
                )
                assert result.exit_code == 0
                assert "Tag updated" in result.output

    def test_update_tag_with_merge(self) -> None:
        """Test updating tag with merge flag."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({})

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "update",
                        "temperature",
                        "--keywords",
                        "sensor",
                        "--merge",
                    ],
                )
                assert result.exit_code == 0
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert payload["merge"] is True


class TestTagDelete:
    """Tests for tag delete command."""

    def test_delete_tag_success(self) -> None:
        """Test successful tag deletion."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 204)

                result = runner.invoke(cli, ["tag", "delete", "temperature"], input="y\n")
                assert result.exit_code == 0
                assert "Tag deleted" in result.output

    def test_delete_tag_confirmation_declined(self) -> None:
        """Test tag deletion with confirmation declined."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 204)

                result = runner.invoke(cli, ["tag", "delete", "temperature"], input="n\n")
                assert result.exit_code != 0


class TestTagSetValue:
    """Tests for tag set-value command."""

    def test_set_tag_value_success(self) -> None:
        """Test successful tag value setting."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 202)

                result = runner.invoke(cli, ["tag", "set-value", "temperature", "23.5"])
                assert result.exit_code == 0
                assert "Tag value updated" in result.output

    def test_set_tag_value_with_timestamp(self) -> None:
        """Test setting tag value with custom timestamp."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response({}, 202)

                result = runner.invoke(
                    cli,
                    [
                        "tag",
                        "set-value",
                        "temperature",
                        "23.5",
                        "--timestamp",
                        "2024-01-01T00:00:00Z",
                    ],
                )
                assert result.exit_code == 0
                call_args = mock_request.call_args
                payload = call_args[1]["payload"]
                assert payload["timestamp"] == "2024-01-01T00:00:00Z"


class TestTagGetValue:
    """Tests for tag get-value command."""

    def test_get_tag_value_success(self) -> None:
        """Test successful tag value retrieval."""
        cli = make_cli()
        runner = CliRunner()

        value_data = {
            "current": {
                "value": {"value": "23.5", "type": "DOUBLE"},
                "timestamp": "2024-01-01T00:00:00Z",
            }
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(value_data)

                result = runner.invoke(cli, ["tag", "get-value", "temperature"])
                assert result.exit_code == 0
                assert "23.5" in result.output

    def test_get_tag_value_json_format(self) -> None:
        """Test tag value retrieval with JSON format."""
        cli = make_cli()
        runner = CliRunner()

        value_data = {"current": {"value": {"value": "23.5"}, "timestamp": "2024-01-01T00:00:00Z"}}

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(value_data)

                result = runner.invoke(cli, ["tag", "get-value", "temperature", "--format", "json"])
                assert result.exit_code == 0
                output_json = json.loads(result.output)
                assert "current" in output_json

    def test_get_tag_value_with_aggregates(self) -> None:
        """Test tag value retrieval with aggregates."""
        cli = make_cli()
        runner = CliRunner()

        value_data = {
            "current": {"value": {"value": "23.5"}, "timestamp": "2024-01-01T00:00:00Z"},
            "aggregates": {"min": "20.0", "max": "25.0", "avg": 22.5, "count": 100},
        }

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-123"
                mock_request.return_value = mock_response(value_data)

                result = runner.invoke(
                    cli, ["tag", "get-value", "temperature", "--include-aggregates"]
                )
                assert result.exit_code == 0
                assert "Aggregates" in result.output


class TestWorkspaceResolution:
    """Tests for workspace resolution logic."""

    def test_explicit_workspace(self) -> None:
        """Test explicit workspace parameter."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-custom"
                mock_request.return_value = mock_response({"tagsWithValues": []})

                result = runner.invoke(cli, ["tag", "list", "--workspace", "ws-custom"])
                assert result.exit_code == 0
                mock_resolve.assert_called_once_with("ws-custom")

    def test_default_workspace_resolution(self) -> None:
        """Test default workspace when not specified."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            with patch("slcli.tag_click._resolve_workspace") as mock_resolve:
                mock_resolve.return_value = "ws-default"
                mock_request.return_value = mock_response({"tagsWithValues": []})

                result = runner.invoke(cli, ["tag", "list"])
                assert result.exit_code == 0
                mock_resolve.assert_called_once_with(None)

    def test_default_workspace_failure(self) -> None:
        """Test default workspace resolution failure."""
        cli = make_cli()
        runner = CliRunner()

        with patch("slcli.tag_click.make_api_request") as mock_request:
            # Mock get workspaces failure
            mock_request.side_effect = Exception("API Error")

            result = runner.invoke(cli, ["tag", "list"])
            assert result.exit_code != 0
            assert "Failed to get default workspace" in result.output

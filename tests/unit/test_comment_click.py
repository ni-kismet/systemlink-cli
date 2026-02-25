"""Unit tests for comment CLI commands."""

import json
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from slcli.comment_click import register_comment_commands


def make_cli() -> click.Group:
    """Create a test CLI group with comment commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_comment_commands(test_cli)
    return test_cli


def mock_response(data: Any, status_code: int = 200) -> Any:
    """Create a mock HTTP response."""
    resp: Any = MagicMock()
    resp.json.return_value = data
    resp.status_code = status_code
    return resp


def mock_response_no_body(status_code: int) -> Any:
    """Create a mock HTTP response with no body (e.g. 204)."""
    resp: Any = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {}
    return resp


SAMPLE_COMMENTS = [
    {
        "id": "aaa111bbb222ccc333ddd444",
        "message": "First comment here",
        "resourceType": "testmonitor:Result",
        "resourceId": "res-001",
        "workspace": "ws-001",
        "createdBy": "user-abc",
        "createdAt": "2026-01-01T10:00:00Z",
        "updatedBy": "user-abc",
        "updatedAt": "2026-01-02T11:30:00Z",
        "mentionedUsers": [],
    },
    {
        "id": "bbb222ccc333ddd444eee555",
        "message": "Second comment with a longer message that should be truncated in the table",
        "resourceType": "testmonitor:Result",
        "resourceId": "res-001",
        "workspace": "ws-001",
        "createdBy": "user-xyz",
        "createdAt": "2026-01-03T09:15:00Z",
        "updatedBy": None,
        "updatedAt": None,
        "mentionedUsers": ["user-abc"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# comment list
# ─────────────────────────────────────────────────────────────────────────────


class TestCommentList:
    """Tests for `slcli comment list`."""

    def test_list_table_success(self, monkeypatch: Any) -> None:
        """List comments in table format resolves user names."""
        user_map = {"user-abc": "Alice Smith", "user-xyz": "Bob Jones"}

        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click._build_user_map", return_value=user_map
        ):
            mock_req.return_value = mock_response({"comments": SAMPLE_COMMENTS})

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "--resource-type",
                    "testmonitor:Result",
                    "--resource-id",
                    "res-001",
                ],
                input="n\n",  # decline pagination prompt
            )

        assert result.exit_code == 0
        assert "aaa111bbb222ccc333ddd444" in result.output
        assert "First comment here" in result.output
        assert "Alice Smith" in result.output

    def test_list_json_success(self, monkeypatch: Any) -> None:
        """List comments in JSON format outputs raw comment list."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response({"comments": SAMPLE_COMMENTS})

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "--resource-type",
                    "testmonitor:Result",
                    "--resource-id",
                    "res-001",
                    "--format",
                    "json",
                ],
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert len(parsed) == 2
        assert parsed[0]["id"] == "aaa111bbb222ccc333ddd444"

    def test_list_empty(self, monkeypatch: Any) -> None:
        """List command prints 'No comments found' when API returns empty list."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response({"comments": []})

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "--resource-type",
                    "niapm:Asset",
                    "--resource-id",
                    "asset-001",
                ],
            )

        assert result.exit_code == 0
        assert "No comments found" in result.output

    def test_list_empty_json(self, monkeypatch: Any) -> None:
        """List command in JSON format outputs [] when no comments found."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response({"comments": []})

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "-r",
                    "DataSpace",
                    "-i",
                    "ds-001",
                    "-f",
                    "json",
                ],
            )

        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    def test_list_api_error(self, monkeypatch: Any) -> None:
        """List command exits with error on API failure."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.side_effect = Exception("connection error")

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "-r",
                    "testmonitor:Result",
                    "-i",
                    "res-001",
                ],
            )

        assert result.exit_code != 0

    def test_list_user_id_fallback(self, monkeypatch: Any) -> None:
        """Table falls back to raw user ID when name lookup fails."""
        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click._build_user_map", return_value={}
        ):
            mock_req.return_value = mock_response({"comments": [SAMPLE_COMMENTS[0]]})

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "list",
                    "-r",
                    "testmonitor:Result",
                    "-i",
                    "res-001",
                ],
                input="n\n",
            )

        assert result.exit_code == 0
        # Falls back to raw user ID
        assert "user-abc" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# comment add
# ─────────────────────────────────────────────────────────────────────────────


class TestCommentAdd:
    """Tests for `slcli comment add`."""

    def test_add_success(self, monkeypatch: Any) -> None:
        """Add a comment successfully."""
        created = [{"id": "new-comment-id-001", "message": "Great work!"}]

        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click.get_workspace_map", return_value={"ws-001": "default"}
        ):
            mock_req.return_value = mock_response({"createdComments": created}, status_code=201)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "--resource-type",
                    "testmonitor:Result",
                    "--resource-id",
                    "res-001",
                    "--workspace",
                    "default",
                    "--message",
                    "Great work!",
                ],
            )

        assert result.exit_code == 0
        assert "Comment added" in result.output
        assert "new-comment-id-001" in result.output

    def test_add_with_mentions(self, monkeypatch: Any) -> None:
        """Add a comment with user mentions includes resourceName in payload."""
        created = [{"id": "mention-comment-id", "message": "Hey there"}]

        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click.get_workspace_map", return_value={"ws-001": "default"}
        ):
            mock_req.return_value = mock_response({"createdComments": created}, status_code=201)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "-r",
                    "niapm:Asset",
                    "-i",
                    "asset-001",
                    "-w",
                    "ws-001",
                    "-m",
                    "Hey there",
                    "-n",
                    "My Asset",
                    "-u",
                    "https://localhost/comments/mention-comment-id",
                    "--mention",
                    "user-abc",
                    "--mention",
                    "user-xyz",
                ],
            )

        assert result.exit_code == 0
        assert "Comment added" in result.output
        # Verify mentions, resourceName, resourceTypeName, and commentUrl in payload
        call_payload = mock_req.call_args[1].get("payload") or mock_req.call_args[0][2]
        comment_payload = call_payload["comments"][0]
        assert "user-abc" in comment_payload["mentionedUsers"]
        assert "user-xyz" in comment_payload["mentionedUsers"]
        assert comment_payload["resourceName"] == "My Asset"
        assert comment_payload["resourceTypeName"] == "Asset"
        assert comment_payload["commentUrl"] == "https://localhost/comments/mention-comment-id"

    def test_add_mentions_without_resource_name_fails(self, monkeypatch: Any) -> None:
        """Add rejects --mention without --resource-name."""
        with patch("slcli.comment_click.make_api_request"), patch(
            "slcli.comment_click.get_workspace_map", return_value={}
        ):
            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "-r",
                    "testmonitor:Result",
                    "-i",
                    "res-001",
                    "-w",
                    "ws-001",
                    "-m",
                    "ping",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code != 0
        assert "--resource-name" in result.output or "--resource-name" in (result.stderr or "")

    def test_add_mentions_without_comment_url_fails(self, monkeypatch: Any) -> None:
        """Add rejects --mention without --comment-url."""
        with patch("slcli.comment_click.make_api_request"), patch(
            "slcli.comment_click.get_workspace_map", return_value={}
        ):
            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "-r",
                    "testmonitor:Result",
                    "-i",
                    "res-001",
                    "-w",
                    "ws-001",
                    "-m",
                    "ping",
                    "-n",
                    "My Result",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code != 0
        assert "--comment-url" in result.output or "--comment-url" in (result.stderr or "")

    def test_add_partial_failure(self, monkeypatch: Any) -> None:
        """Add exits with error code when some comments fail."""
        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click.get_workspace_map", return_value={}
        ):
            mock_req.return_value = mock_response(
                {
                    "createdComments": [],
                    "failedComments": [{"resourceType": "badType", "message": "oops"}],
                },
                status_code=200,
            )

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "-r",
                    "badType",
                    "-i",
                    "bad-id",
                    "-w",
                    "ws-001",
                    "-m",
                    "oops",
                ],
            )

        assert result.exit_code != 0

    def test_add_api_error(self, monkeypatch: Any) -> None:
        """Add command exits with error on API failure."""
        with patch("slcli.comment_click.make_api_request") as mock_req, patch(
            "slcli.comment_click.get_workspace_map", return_value={}
        ):
            mock_req.side_effect = Exception("Unauthorized")

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "add",
                    "-r",
                    "testmonitor:Result",
                    "-i",
                    "res-001",
                    "-w",
                    "ws-001",
                    "-m",
                    "hello",
                ],
            )

        assert result.exit_code != 0

    def test_add_readonly_mode(self, monkeypatch: Any) -> None:
        """Add is blocked in readonly mode."""
        monkeypatch.setattr(
            "slcli.comment_click.check_readonly_mode", lambda *a, **kw: __import__("sys").exit(4)
        )

        runner = CliRunner()
        result = runner.invoke(
            make_cli(),
            [
                "comment",
                "add",
                "-r",
                "testmonitor:Result",
                "-i",
                "res-001",
                "-w",
                "ws-001",
                "-m",
                "blocked",
            ],
        )

        assert result.exit_code == 4


# ─────────────────────────────────────────────────────────────────────────────
# comment update
# ─────────────────────────────────────────────────────────────────────────────


class TestCommentUpdate:
    """Tests for `slcli comment update`."""

    def test_update_success(self, monkeypatch: Any) -> None:
        """Update a comment's message successfully (204 response)."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response_no_body(204)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "aaa111bbb222ccc333ddd444",
                    "--message",
                    "Updated text",
                ],
            )

        assert result.exit_code == 0
        assert "Comment updated" in result.output
        assert "aaa111bbb222ccc333ddd444" in result.output

    def test_update_with_mentions(self, monkeypatch: Any) -> None:
        """Update passes mentionedUsers, resourceName, and resourceTypeName when mentions used."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response_no_body(204)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "comment-id-001",
                    "--message",
                    "Ping you",
                    "-n",
                    "My Result",
                    "-r",
                    "testmonitor:Result",
                    "-u",
                    "https://localhost/comments/comment-id-001",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code == 0
        call_payload = mock_req.call_args[1].get("payload") or mock_req.call_args[0][2]
        assert call_payload["mentionedUsers"] == ["user-abc"]
        assert call_payload["resourceName"] == "My Result"
        assert call_payload["resourceTypeName"] == "Test Result"
        assert call_payload["commentUrl"] == "https://localhost/comments/comment-id-001"

    def test_update_mentions_without_resource_type_fails(self, monkeypatch: Any) -> None:
        """Update rejects --mention without --resource-type."""
        with patch("slcli.comment_click.make_api_request"):
            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "comment-id-001",
                    "--message",
                    "ping",
                    "-n",
                    "My Result",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code != 0
        assert "--resource-type" in result.output or "--resource-type" in (result.stderr or "")

    def test_update_mentions_without_resource_name_fails(self, monkeypatch: Any) -> None:
        """Update rejects --mention without --resource-name."""
        with patch("slcli.comment_click.make_api_request"):
            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "comment-id-001",
                    "--message",
                    "ping",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code != 0
        assert "--resource-name" in result.output or "--resource-name" in (result.stderr or "")

    def test_update_mentions_without_comment_url_fails(self, monkeypatch: Any) -> None:
        """Update rejects --mention without --comment-url."""
        with patch("slcli.comment_click.make_api_request"):
            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "comment-id-001",
                    "--message",
                    "ping",
                    "-n",
                    "My Result",
                    "-r",
                    "testmonitor:Result",
                    "--mention",
                    "user-abc",
                ],
            )

        assert result.exit_code != 0
        assert "--comment-url" in result.output or "--comment-url" in (result.stderr or "")

    def test_update_api_error(self, monkeypatch: Any) -> None:
        """Update exits with error on API failure."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.side_effect = Exception("not found")

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "update",
                    "bad-id",
                    "--message",
                    "does not matter",
                ],
            )

        assert result.exit_code != 0

    def test_update_readonly_mode(self, monkeypatch: Any) -> None:
        """Update is blocked in readonly mode."""
        monkeypatch.setattr(
            "slcli.comment_click.check_readonly_mode", lambda *a, **kw: __import__("sys").exit(4)
        )

        runner = CliRunner()
        result = runner.invoke(
            make_cli(),
            ["comment", "update", "some-id", "--message", "blocked"],
        )

        assert result.exit_code == 4


# ─────────────────────────────────────────────────────────────────────────────
# comment delete
# ─────────────────────────────────────────────────────────────────────────────


class TestCommentDelete:
    """Tests for `slcli comment delete`."""

    def test_delete_single_success(self, monkeypatch: Any) -> None:
        """Delete a single comment with a 204 response."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response_no_body(204)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                ["comment", "delete", "aaa111bbb222ccc333ddd444"],
            )

        assert result.exit_code == 0
        assert "Deleted 1 comment" in result.output

    def test_delete_multiple_success(self, monkeypatch: Any) -> None:
        """Delete multiple comments with a 204 response."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response_no_body(204)

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "delete",
                    "aaa111bbb222ccc333ddd444",
                    "bbb222ccc333ddd444eee555",
                ],
            )

        assert result.exit_code == 0
        assert "Deleted 2 comment(s)" in result.output

    def test_delete_partial_success(self, monkeypatch: Any) -> None:
        """Delete exits with error when some IDs fail (200 partial response)."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.return_value = mock_response(
                {
                    "deletedCommentIds": ["aaa111bbb222ccc333ddd444"],
                    "failedCommentIds": ["bbb222ccc333ddd444eee555"],
                },
                status_code=200,
            )

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                [
                    "comment",
                    "delete",
                    "aaa111bbb222ccc333ddd444",
                    "bbb222ccc333ddd444eee555",
                ],
            )

        assert result.exit_code != 0
        assert "Deleted 1 comment" in result.output
        assert "Failed to delete 1 comment" in result.output

    def test_delete_too_many_ids(self, monkeypatch: Any) -> None:
        """Delete rejects more than 1000 comment IDs."""
        runner = CliRunner()
        many_ids = [f"id-{i}" for i in range(1001)]
        result = runner.invoke(make_cli(), ["comment", "delete"] + many_ids)

        assert result.exit_code != 0

    def test_delete_api_error(self, monkeypatch: Any) -> None:
        """Delete exits with error on API failure."""
        with patch("slcli.comment_click.make_api_request") as mock_req:
            mock_req.side_effect = Exception("permission denied")

            runner = CliRunner()
            result = runner.invoke(
                make_cli(),
                ["comment", "delete", "some-id"],
            )

        assert result.exit_code != 0

    def test_delete_readonly_mode(self, monkeypatch: Any) -> None:
        """Delete is blocked in readonly mode."""
        monkeypatch.setattr(
            "slcli.comment_click.check_readonly_mode", lambda *a, **kw: __import__("sys").exit(4)
        )

        runner = CliRunner()
        result = runner.invoke(make_cli(), ["comment", "delete", "some-id"])

        assert result.exit_code == 4


# ─────────────────────────────────────────────────────────────────────────────
# helper unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHelpers:
    """Tests for internal helper functions."""

    def test_truncate_short(self) -> None:
        """Short text is not truncated."""
        from slcli.comment_click import _truncate

        assert _truncate("Hello", 20) == "Hello"

    def test_truncate_long(self) -> None:
        """Long text is truncated with ellipsis."""
        from slcli.comment_click import _truncate

        result = _truncate("A" * 60, 20)
        assert len(result) == 20
        assert result.endswith("…")

    def test_truncate_strips_newlines(self) -> None:
        """Newlines are replaced with spaces for table display."""
        from slcli.comment_click import _truncate

        assert "\n" not in _truncate("line1\nline2", 50)

    def test_format_datetime_valid(self) -> None:
        """ISO-8601 datetime is formatted to YYYY-MM-DD HH:MM."""
        from slcli.comment_click import _format_datetime

        assert _format_datetime("2026-01-15T09:30:00.000Z") == "2026-01-15 09:30"

    def test_format_datetime_none(self) -> None:
        """None input returns empty string."""
        from slcli.comment_click import _format_datetime

        assert _format_datetime(None) == ""

    def test_format_user_with_map(self) -> None:
        """User ID is resolved to display name from map."""
        from slcli.comment_click import _format_user

        assert _format_user("uid-1", {"uid-1": "Jane Doe"}) == "Jane Doe"

    def test_format_user_fallback(self) -> None:
        """Unknown user ID returns raw ID."""
        from slcli.comment_click import _format_user

        assert _format_user("uid-unknown", {}) == "uid-unknown"

    def test_format_user_none(self) -> None:
        """None user ID returns empty string."""
        from slcli.comment_click import _format_user

        assert _format_user(None, {}) == ""

    def test_build_user_map_deduplicates(self, monkeypatch: Any) -> None:
        """_build_user_map deduplicates IDs, calling _fetch_user_display_name once per unique ID."""
        from slcli.comment_click import _build_user_map

        call_log: list = []

        def fake_fetch(uid: str) -> Optional[str]:
            call_log.append(uid)
            return f"Name of {uid}"

        monkeypatch.setattr("slcli.comment_click._fetch_user_display_name", fake_fetch)

        result = _build_user_map(["u1", "u2", "u1", "u2", "u3"])
        assert len(call_log) == 3  # only 3 unique IDs fetched
        assert result["u1"] == "Name of u1"
        assert result["u3"] == "Name of u3"

    def test_build_user_map_skips_failed_lookups(self, monkeypatch: Any) -> None:
        """_build_user_map omits IDs where _fetch_user_display_name returns None."""
        from slcli.comment_click import _build_user_map

        monkeypatch.setattr("slcli.comment_click._fetch_user_display_name", lambda uid: None)

        result = _build_user_map(["u1", "u2"])
        assert result == {}

"""CLI commands for managing SystemLink comments.

Provides CLI commands for listing, creating, updating, and deleting comments
on any SystemLink resource via the nicomments v1 service.

Supported resource types:
  testmonitor:Result  - Test Monitor results
  niapm:Asset         - Assets
  nisysmgmt:System    - Systems
  workorder:workorder - Work Orders
  workitem:workitem    - Work Items
  DataSpace           - Data Spaces
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import click

from .cli_utils import validate_output_format
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import resolve_workspace_filter

# Human-readable display names for known resource types, used in mention notification emails.
_RESOURCE_TYPE_NAMES: Dict[str, str] = {
    "testmonitor:Result": "Test Result",
    "niapm:Asset": "Asset",
    "nisysmgmt:System": "System",
    "workorder:workorder": "Work Order",
    "workitem:workitem": "Work Item",
    "DataSpace": "Data Space",
}


def _get_comment_base_url() -> str:
    """Get the base URL for the Comments API."""
    return f"{get_base_url()}/nicomments/v1"


def _resource_type_name(resource_type: str) -> str:
    """Return the human-readable display name for a resource type.

    Falls back to the raw resource_type string for unknown types.

    Args:
        resource_type: API resource type string (e.g. "testmonitor:Result").

    Returns:
        Human-readable label (e.g. "Test Result").
    """
    return _RESOURCE_TYPE_NAMES.get(resource_type, resource_type)


def _fetch_user_display_name(user_id: str) -> Optional[str]:
    """Fetch a user's display name (First Last) from the niuser service.

    Silently returns None on any failure so callers can fall back to the raw ID.

    Args:
        user_id: The user's unique ID.

    Returns:
        Display name string or None if the lookup fails.
    """
    try:
        url = f"{get_base_url()}/niuser/v1/users/{user_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=False)
        data = resp.json()
        first = data.get("firstName", "")
        last = data.get("lastName", "")
        name = f"{first} {last}".strip()
        return name if name else None
    except Exception:
        return None


def _build_user_map(user_ids: List[str]) -> Dict[str, str]:
    """Build a map of user IDs to display names for a set of IDs.

    Deduplicates IDs before fetching. Silently ignores failed lookups.

    Args:
        user_ids: List of user IDs (may contain duplicates or empty strings).

    Returns:
        Dictionary mapping user ID to "First Last" display name.
    """
    user_map: Dict[str, str] = {}
    seen = set()
    for uid in user_ids:
        if uid and uid not in seen:
            seen.add(uid)
            name = _fetch_user_display_name(uid)
            if name:
                user_map[uid] = name
    return user_map


def _format_user(user_id: Optional[str], user_map: Dict[str, str]) -> str:
    """Return display name for a user ID, falling back to the raw ID.

    Args:
        user_id: The user's unique ID, or None/empty.
        user_map: Mapping of ID to display name.

    Returns:
        Display name or raw ID or empty string.
    """
    if not user_id:
        return ""
    return user_map.get(user_id, user_id)


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len characters, appending '…' if truncated.

    Args:
        text: Text to truncate.
        max_len: Maximum character length including the ellipsis.

    Returns:
        Truncated string.
    """
    if not text:
        return ""
    # Strip newlines for table display
    flat = text.replace("\n", " ").replace("\r", "")
    if len(flat) <= max_len:
        return flat
    return flat[: max_len - 1] + "…"


def _format_datetime(value: Optional[str]) -> str:
    """Format an ISO-8601 timestamp to 'YYYY-MM-DD HH:MM' for table display.

    Args:
        value: ISO-8601 datetime string or None.

    Returns:
        Formatted date string or empty string.
    """
    if not value:
        return ""
    try:
        # Accept "2018-05-09T15:07:42.527921Z" → "2018-05-09 15:07"
        dt_part = value.replace("Z", "").split(".")[0]
        date, time = dt_part.split("T", 1)
        hour_min = time[:5]
        return f"{date} {hour_min}"
    except Exception:
        return value


def _comment_row_formatter(comment: Dict[str, Any], user_map: Dict[str, str]) -> List[str]:
    """Format a single comment into table columns.

    Args:
        comment: Comment data dict from API response.
        user_map: User ID → display name map.

    Returns:
        List of column values: [ID, Message, Author, Created At, Updated At].
    """
    return [
        comment.get("id", ""),
        _truncate(comment.get("message", ""), 55),
        _format_user(comment.get("createdBy"), user_map),
        _format_datetime(comment.get("createdAt")),
        _format_datetime(comment.get("updatedAt")),
    ]


def register_comment_commands(cli: Any) -> None:
    """Register the 'comment' command group and its subcommands."""

    @cli.group()
    def comment() -> None:
        """Manage comments on SystemLink resources.

        Comments can be attached to any resource identified by a resource type
        and resource ID. Known resource types: testmonitor:Result, niapm:Asset,
        nisysmgmt:System, workorder:workorder, workitem:workitem, DataSpace.
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # comment list
    # ─────────────────────────────────────────────────────────────

    @comment.command(name="list")
    @click.option(
        "--resource-type",
        "-r",
        required=True,
        help=(
            "Resource type the comments belong to "
            "(e.g. testmonitor:Result, niapm:Asset, nisysmgmt:System, "
            "workorder:workorder, workitem:workitem, DataSpace)"
        ),
    )
    @click.option(
        "--resource-id",
        "-i",
        required=True,
        help="ID of the resource whose comments to list.",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format.",
    )
    def list_comments(
        resource_type: str,
        resource_id: str,
        format: str = "table",
    ) -> None:
        """List comments for a resource.

        The API returns the most recent 1000 comments ordered by creation time.

        \b
        Examples:
          slcli comment list --resource-type testmonitor:Result --resource-id <id>
          slcli comment list -r niapm:Asset -i <id> --format json
        """
        format_output = validate_output_format(format)

        try:
            # Note: "ResourceType" and "ResourceId" must use this exact PascalCase
            # casing to match the nicomments v1 API query parameter specification.
            params = urlencode({"ResourceType": resource_type, "ResourceId": resource_id})
            url = f"{_get_comment_base_url()}/comments?{params}"
            resp = make_api_request("GET", url)
            data = resp.json()
            comments: List[Dict[str, Any]] = data.get("comments") or []

            if format_output.lower() == "json":
                click.echo(json.dumps(comments, indent=2))
                return

            if not comments:
                click.echo("No comments found.")
                return

            # Build user map once for all comments
            user_ids = []
            for c in comments:
                for field in ("createdBy", "updatedBy"):
                    uid = c.get(field)
                    if uid:
                        user_ids.append(uid)
            user_map = _build_user_map(user_ids)

            def _row(c: Dict[str, Any]) -> List[str]:
                return _comment_row_formatter(c, user_map)

            filtered_resp: Any = FilteredResponse({"comments": comments})
            UniversalResponseHandler.handle_list_response(
                resp=filtered_resp,
                data_key="comments",
                item_name="comment",
                format_output=format_output,
                formatter_func=_row,
                headers=["ID", "Message", "Author", "Created At", "Updated At"],
                column_widths=[24, 55, 22, 16, 16],
                empty_message="No comments found.",
                enable_pagination=True,
                page_size=25,
            )

        except Exception as exc:
            handle_api_error(exc)

    # ─────────────────────────────────────────────────────────────
    # comment add
    # ─────────────────────────────────────────────────────────────

    @comment.command(name="add")
    @click.option(
        "--resource-type",
        "-r",
        required=True,
        help=(
            "Resource type to comment on "
            "(e.g. testmonitor:Result, niapm:Asset, nisysmgmt:System, "
            "workorder:workorder, workitem:workitem, DataSpace)"
        ),
    )
    @click.option(
        "--resource-id",
        "-i",
        required=True,
        help="ID of the resource to comment on.",
    )
    @click.option(
        "--workspace",
        "-w",
        required=True,
        help="Workspace name or ID that owns the resource.",
    )
    @click.option(
        "--message",
        "-m",
        required=True,
        help=(
            "Comment message (supports Markdown). "
            "To mention a user, embed a tag in the form <user:USER_ID> in the message "
            "and also pass the same user ID to --mention."
        ),
    )
    @click.option(
        "--resource-name",
        "-n",
        default=None,
        help=(
            "Human-readable name of the resource. Required when using --mention "
            "so the API can include it in mention notification emails."
        ),
    )
    @click.option(
        "--comment-url",
        "-u",
        default=None,
        help=(
            "URL to the comment in the SystemLink web UI. Required when using --mention "
            "so the API can include a link in mention notification emails."
        ),
    )
    @click.option(
        "--mention",
        "mentions",
        multiple=True,
        help=(
            "User ID to register as a mentioned user. Must match a <user:USER_ID> tag "
            "embedded in the --message. Can be specified multiple times."
        ),
    )
    def add_comment(
        resource_type: str,
        resource_id: str,
        workspace: str,
        message: str,
        resource_name: Optional[str],
        comment_url: Optional[str],
        mentions: Tuple[str, ...],
    ) -> None:
        """Add a comment to a resource.

        To mention a user, embed a \\b<user:USER_ID> tag in the message and pass
        the same user ID to --mention. All three of --resource-name, --comment-url,
        and the implicit --resource-type are then also required.

        \b
        Examples:
          slcli comment add -r testmonitor:Result -i <id> -w default -m "Looks good!"
          slcli comment add -r niapm:Asset -i <id> -w "My Workspace" \\
            -n "My Asset" -u "https://<server>/..." \\
            -m "Review needed: <user:f9d5c5c9-e098-4a82-8e55-fede326a4ec3>" \\
            --mention f9d5c5c9-e098-4a82-8e55-fede326a4ec3
        """
        check_readonly_mode("add a comment")

        if mentions and not resource_name:
            click.echo(
                "✗ --resource-name / -n is required when using --mention.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        if mentions and not comment_url:
            click.echo(
                "✗ --comment-url / -u is required when using --mention.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            workspace_map = get_workspace_map()
            workspace_id = resolve_workspace_filter(workspace, workspace_map)

            comment_entry: Dict[str, Any] = {
                "resourceType": resource_type,
                "resourceId": resource_id,
                "workspace": workspace_id,
                "message": message,
            }
            if mentions:
                comment_entry["mentionedUsers"] = list(mentions)
                comment_entry["resourceName"] = resource_name
                comment_entry["resourceTypeName"] = _resource_type_name(resource_type)
                comment_entry["commentUrl"] = comment_url

            payload: Dict[str, Any] = {"comments": [comment_entry]}

            url = f"{_get_comment_base_url()}/comments"
            resp = make_api_request("POST", url, payload=payload)
            resp_data = resp.json()

            # API returns 201 on full success, 200 on partial success
            created = resp_data.get("createdComments") or []
            failed = resp_data.get("failedComments") or []

            if created:
                comment_id = created[0].get("id", "")
                format_success("Comment added", {"ID": comment_id})

            if failed:
                click.echo(
                    f"✗ {len(failed)} comment(s) failed to create.",
                    err=True,
                )
                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    # ─────────────────────────────────────────────────────────────
    # comment update
    # ─────────────────────────────────────────────────────────────

    @comment.command(name="update")
    @click.argument("comment_id")
    @click.option(
        "--message",
        "-m",
        required=True,
        help=(
            "New comment message (supports Markdown). Replaces the existing message. "
            "To mention a user, embed a tag in the form <user:USER_ID> in the message "
            "and also pass the same user ID to --mention."
        ),
    )
    @click.option(
        "--resource-name",
        "-n",
        default=None,
        help=(
            "Human-readable name of the resource. Required when using --mention "
            "so the API can include it in mention notification emails."
        ),
    )
    @click.option(
        "--resource-type",
        "-r",
        default=None,
        help=(
            "Resource type of the comment's resource "
            "(e.g. testmonitor:Result, niapm:Asset, DataSpace). "
            "Required when using --mention so the API can send notification emails."
        ),
    )
    @click.option(
        "--comment-url",
        "-u",
        default=None,
        help=(
            "URL to the comment in the SystemLink web UI. Required when using --mention "
            "so the API can include a link in mention notification emails."
        ),
    )
    @click.option(
        "--mention",
        "mentions",
        multiple=True,
        help=(
            "User ID to register as a mentioned user. Must match a <user:USER_ID> tag "
            "embedded in the --message. Can be specified multiple times. "
            "Replaces the full mentioned-users list."
        ),
    )
    def update_comment(
        comment_id: str,
        message: str,
        resource_name: Optional[str],
        resource_type: Optional[str],
        comment_url: Optional[str],
        mentions: Tuple[str, ...],
    ) -> None:
        """Update the message of an existing comment.

        You can only update your own comments. Mentioning users replaces
        the previous mention list entirely. To mention a user, embed a
        \\b<user:USER_ID> tag in the message and pass the same user ID to --mention.
        Also requires --resource-name, --resource-type, and --comment-url.

        \b
        Examples:
          slcli comment update <comment-id> --message "Updated text"
          slcli comment update <comment-id> \\
            -m "FYI: <user:f9d5c5c9-e098-4a82-8e55-fede326a4ec3>" \\
            -n "My Result" -r testmonitor:Result -u "https://<server>/..." \\
            --mention f9d5c5c9-e098-4a82-8e55-fede326a4ec3
        """
        check_readonly_mode("update this comment")

        if mentions and not resource_name:
            click.echo(
                "✗ --resource-name / -n is required when using --mention.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        if mentions and not resource_type:
            click.echo(
                "✗ --resource-type / -r is required when using --mention.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        if mentions and not comment_url:
            click.echo(
                "✗ --comment-url / -u is required when using --mention.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            payload: Dict[str, Any] = {
                "message": message,
            }
            if mentions:
                payload["mentionedUsers"] = list(mentions)
                payload["resourceName"] = resource_name
                payload["resourceTypeName"] = _resource_type_name(resource_type or "")
                payload["commentUrl"] = comment_url

            url = f"{_get_comment_base_url()}/comments/{comment_id}"
            make_api_request("PATCH", url, payload=payload)
            format_success("Comment updated", {"ID": comment_id})

        except Exception as exc:
            handle_api_error(exc)

    # ─────────────────────────────────────────────────────────────
    # comment delete
    # ─────────────────────────────────────────────────────────────

    @comment.command(name="delete")
    @click.argument("comment_ids", nargs=-1, required=True)
    def delete_comments(
        comment_ids: Tuple[str, ...],
    ) -> None:
        """Delete one or more comments by ID.

        You can delete your own comments. Elevated permissions are required
        to delete others' comments. Accepts up to 1000 IDs per invocation.

        \b
        Examples:
          slcli comment delete <comment-id>
          slcli comment delete <id1> <id2> <id3>
        """
        check_readonly_mode("delete comment(s)")

        if len(comment_ids) > 1000:
            click.echo(
                "✗ Cannot delete more than 1000 comments per request.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            payload: Dict[str, Any] = {"ids": list(comment_ids)}
            url = f"{_get_comment_base_url()}/delete-comments"
            resp = make_api_request("POST", url, payload=payload)

            # 204 = full success (no body), 200 = partial success (body with details)
            if resp.status_code == 204:
                format_success(f"Deleted {len(comment_ids)} comment(s)")
                return

            resp_data = resp.json()
            deleted_ids: List[str] = resp_data.get("deletedCommentIds") or []
            failed_ids: List[str] = resp_data.get("failedCommentIds") or []

            if deleted_ids:
                format_success(f"Deleted {len(deleted_ids)} comment(s)")

            if failed_ids:
                click.echo(
                    f"✗ Failed to delete {len(failed_ids)} comment(s): " + ", ".join(failed_ids),
                    err=True,
                )
                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

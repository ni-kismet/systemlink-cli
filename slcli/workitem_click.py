"""CLI commands for managing SystemLink work items, templates, and workflows."""

import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import click
import requests

from . import workflow_preview
from .cli_utils import validate_output_format
from .platform import require_feature
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    display_api_errors,
    extract_error_type,
    format_success,
    get_base_url,
    get_workspace_id_with_fallback,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    sanitize_filename,
    save_json_file,
)
from .workspace_utils import get_workspace_display_name, resolve_workspace_filter


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _wi_url(path: str) -> str:
    """Return a fully-qualified niworkitem v1 URL."""
    return f"{get_base_url()}/niworkitem/v1{path}"


def _wf_url(path: str) -> str:
    """Return a fully-qualified niworkorder v1 URL with feature flag."""
    return f"{get_base_url()}/niworkorder/v1{path}?ff-userdefinedworkflowsfortestplaninstances=true"


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------


def _query_all_workitems(
    filter_expr: Optional[str] = None,
    substitutions: Optional[List[Any]] = None,
    workspace_filter: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch work items via continuation-token pagination.

    Args:
        filter_expr: Optional LINQ filter expression.
        substitutions: Optional substitution list for the filter expression.
        workspace_filter: Optional workspace ID to restrict results.
        max_items: Maximum number of items to return.  ``None`` means fetch
            all.  Used to guard against buggy continuation tokens that are
            returned even when the requested take has been satisfied.

    Returns:
        List of up to *max_items* matching work items.
    """
    url = _wi_url("/query-workitems")
    all_items: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    while True:
        payload: Dict[str, Any] = {"take": 100}
        combined_filter_parts: List[str] = []
        combined_subs: List[Any] = []

        if filter_expr:
            combined_filter_parts.append(f"({filter_expr})")
            combined_subs.extend(substitutions or [])

        if workspace_filter:
            idx = len(combined_subs)
            combined_filter_parts.append(f"workspace == @{idx}")
            combined_subs.append(workspace_filter)

        if combined_filter_parts:
            payload["filter"] = " && ".join(combined_filter_parts)
        if combined_subs:
            payload["substitutions"] = combined_subs

        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        page = data.get("workItems", [])
        if not page:
            # Empty page — no more real results regardless of token
            break
        all_items.extend(page)

        # Honour the caller's requested limit; guards against a server-side
        # bug where a continuation token is returned even after all matching
        # items have been delivered.
        if max_items is not None and len(all_items) >= max_items:
            break

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    if max_items is not None:
        return all_items[:max_items]
    return all_items


def _query_all_templates(
    filter_expr: Optional[str] = None,
    substitutions: Optional[List[Any]] = None,
    workspace_filter: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch work item templates via continuation-token pagination.

    Args:
        filter_expr: Optional LINQ filter expression.
        substitutions: Optional substitution list for the filter expression.
        workspace_filter: Optional workspace ID to restrict results.
        max_items: Maximum number of items to return.  ``None`` means fetch
            all.  Used to guard against buggy continuation tokens that are
            returned even when the requested take has been satisfied.

    Returns:
        List of up to *max_items* matching templates.
    """
    url = _wi_url("/query-workitem-templates")
    all_items: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    while True:
        payload: Dict[str, Any] = {"take": 100}
        combined_filter_parts: List[str] = []
        combined_subs: List[Any] = []

        if filter_expr:
            combined_filter_parts.append(f"({filter_expr})")
            combined_subs.extend(substitutions or [])

        if workspace_filter:
            idx = len(combined_subs)
            combined_filter_parts.append(f"workspace == @{idx}")
            combined_subs.append(workspace_filter)

        if combined_filter_parts:
            payload["filter"] = " && ".join(combined_filter_parts)
        if combined_subs:
            payload["substitutions"] = combined_subs

        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        page = data.get("workItemTemplates", [])
        if not page:
            break
        all_items.extend(page)

        if max_items is not None and len(all_items) >= max_items:
            break

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    if max_items is not None:
        return all_items[:max_items]
    return all_items


def _query_all_workflows(
    workspace_filter: Optional[str] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Fetch workflows via continuation-token pagination (niworkorder API).

    Args:
        workspace_filter: Optional workspace ID to filter by.
        max_items: Maximum number of workflows to return.  ``None`` means
            fetch all.  Used to guard against buggy continuation tokens that
            are returned even when the requested take has been satisfied.

    Returns:
        List of up to *max_items* workflows.
    """
    url = _wf_url("/query-workflows")
    all_workflows: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    while True:
        payload: Dict[str, Union[int, str]] = {"take": 100}
        if workspace_filter:
            payload["filter"] = f'WORKSPACE == "{workspace_filter}"'
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        page = data.get("workflows", [])
        if not page:
            break
        all_workflows.extend(page)

        if max_items is not None and len(all_workflows) >= max_items:
            break

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    if max_items is not None:
        return all_workflows[:max_items]
    return all_workflows


# ---------------------------------------------------------------------------
# Error-handling helpers
# ---------------------------------------------------------------------------


def _fetch_workitems_page(
    filter_expr: Optional[str],
    substitutions: Optional[List[Any]],
    workspace_filter: Optional[str],
    take: int,
    continuation_token: Optional[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of work items from the server.

    Guards against a known service bug where a continuation token is returned
    even after all matching items have been delivered: if the page is smaller
    than *take* the returned token (if any) is discarded.

    Returns:
        Tuple of (items, next_continuation_token).
    """
    url = _wi_url("/query-workitems")
    payload: Dict[str, Any] = {"take": take}
    combined_filter_parts: List[str] = []
    combined_subs: List[Any] = []

    if filter_expr:
        combined_filter_parts.append(f"({filter_expr})")
        combined_subs.extend(substitutions or [])

    if workspace_filter:
        idx = len(combined_subs)
        combined_filter_parts.append(f"workspace == @{idx}")
        combined_subs.append(workspace_filter)

    if combined_filter_parts:
        payload["filter"] = " && ".join(combined_filter_parts)
    if combined_subs:
        payload["substitutions"] = combined_subs

    if continuation_token:
        payload["continuationToken"] = continuation_token

    resp = make_api_request("POST", url, payload)
    data = resp.json()
    items = data.get("workItems", [])

    # Only trust the continuation token when a full page was returned.
    # Fewer items than requested means the server has nothing left, even if
    # it (incorrectly) still emits a token.
    next_token: Optional[str] = data.get("continuationToken") if len(items) >= take else None
    return items, next_token


def _fetch_templates_page(
    filter_expr: Optional[str],
    substitutions: Optional[List[Any]],
    workspace_filter: Optional[str],
    take: int,
    continuation_token: Optional[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of work item templates from the server.

    See :func:`_fetch_workitems_page` for the stale-token guard rationale.

    Returns:
        Tuple of (items, next_continuation_token).
    """
    url = _wi_url("/query-workitem-templates")
    payload: Dict[str, Any] = {"take": take}
    combined_filter_parts: List[str] = []
    combined_subs: List[Any] = []

    if filter_expr:
        combined_filter_parts.append(f"({filter_expr})")
        combined_subs.extend(substitutions or [])

    if workspace_filter:
        idx = len(combined_subs)
        combined_filter_parts.append(f"workspace == @{idx}")
        combined_subs.append(workspace_filter)

    if combined_filter_parts:
        payload["filter"] = " && ".join(combined_filter_parts)
    if combined_subs:
        payload["substitutions"] = combined_subs

    if continuation_token:
        payload["continuationToken"] = continuation_token

    resp = make_api_request("POST", url, payload)
    data = resp.json()
    items = data.get("workItemTemplates", [])

    next_token: Optional[str] = data.get("continuationToken") if len(items) >= take else None
    return items, next_token


def _fetch_workflows_page(
    workspace_filter: Optional[str],
    take: int,
    continuation_token: Optional[str],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of workflows from the server (niworkorder API).

    See :func:`_fetch_workitems_page` for the stale-token guard rationale.

    Returns:
        Tuple of (items, next_continuation_token).
    """
    url = _wf_url("/query-workflows")
    payload: Dict[str, Union[int, str]] = {"take": take}
    if workspace_filter:
        payload["filter"] = f'WORKSPACE == "{workspace_filter}"'
    if continuation_token:
        payload["continuationToken"] = continuation_token

    resp = make_api_request("POST", url, payload)
    data = resp.json()
    items = data.get("workflows", [])

    next_token: Optional[str] = data.get("continuationToken") if len(items) >= take else None
    return items, next_token


def _handle_workflow_error_response(response_data: Dict[str, Any], operation_name: str) -> None:
    """Display detailed workflow error responses.

    Args:
        response_data: JSON response data containing error information.
        operation_name: Description of the failed operation.
    """
    display_api_errors(operation_name, response_data, detailed=True)


def _handle_workflow_delete_response(response_data: Dict[str, Any], workflow_id: str) -> None:
    """Handle workflow delete response, supporting partial success.

    Args:
        response_data: JSON response data from the delete operation.
        workflow_id: ID of the workflow that was requested to be deleted.
    """
    if not response_data or response_data == {}:
        click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
        return

    if "ids" in response_data:
        deleted_ids = response_data.get("ids", [])
        if workflow_id in deleted_ids:
            click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
            return
        click.echo(f"✗ Unexpected response for workflow {workflow_id}:", err=True)
        click.echo(f"  Successfully deleted: {', '.join(deleted_ids)}", err=True)
        sys.exit(1)

    deleted_ids = response_data.get("deletedWorkflowIds", [])
    failed_ids = response_data.get("failedWorkflowIds", [])

    if workflow_id in deleted_ids:
        click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
        return

    if workflow_id in failed_ids:
        click.echo(f"✗ Failed to delete workflow {workflow_id}:", err=True)
        error = response_data.get("error", {})
        if error:
            click.echo(f"  {error.get('message', 'Unknown error')}", err=True)
            for inner_error in error.get("innerErrors", []):
                if inner_error.get("resourceId", "") == workflow_id:
                    msg = inner_error.get("message", "Unknown error")
                    name = inner_error.get("name", "")
                    if name:
                        click.echo(f"    - {extract_error_type(name)}: {msg}", err=True)
                    else:
                        click.echo(f"    - {msg}", err=True)
        sys.exit(1)

    click.echo(f"✗ Unexpected response for workflow {workflow_id}:", err=True)
    if deleted_ids:
        click.echo(f"  Successfully deleted: {', '.join(deleted_ids)}", err=True)
    if failed_ids:
        click.echo(f"  Failed to delete: {', '.join(failed_ids)}", err=True)
    if failed_ids or not response_data:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main registration function
# ---------------------------------------------------------------------------


def register_workitem_commands(cli: Any) -> None:
    """Register the 'workitem' command group and all subcommands."""

    @cli.group()
    def workitem() -> None:
        """Manage work items, templates, and workflows."""

    # -----------------------------------------------------------------------
    # workitem list
    # -----------------------------------------------------------------------
    @workitem.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of work items to return (table) or fetch (json)",
    )
    @click.option(
        "--filter",
        "filter_expr",
        default=None,
        help="Dynamic LINQ filter expression (e.g. 'state == \"NEW\"')",
    )
    @click.option(
        "--state",
        "-s",
        default=None,
        help=(
            "Filter by state: NEW, DEFINED, REVIEWED, SCHEDULED, "
            "IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED"
        ),
    )
    @click.option(
        "--workspace",
        "-w",
        default=None,
        help="Filter by workspace name or ID",
    )
    def list_workitems(
        format: str,
        take: int,
        filter_expr: Optional[str],
        state: Optional[str],
        workspace: Optional[str],
    ) -> None:
        """List work items."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Build final filter, combining --filter and --state
            final_filter: Optional[str] = None
            subs: List[Any] = []
            parts: List[str] = []

            if state:
                parts.append(f"state == @{len(subs)}")
                subs.append(state.upper())

            if filter_expr:
                # Offset substitution indices from user-provided filter
                import re

                def _offset(m: Any) -> str:
                    return f"@{int(m.group(1)) + len(subs)}"

                user_filter = re.sub(r"@(\d+)", _offset, filter_expr)
                parts.append(f"({user_filter})")

            if parts:
                final_filter = " && ".join(parts)

            if format_output == "json":
                items = _query_all_workitems(
                    final_filter, subs or None, workspace_id, max_items=take
                )
                click.echo(json.dumps(items, indent=2))
                return

            def _fmt(item: Dict[str, Any]) -> list:
                ws_name = get_workspace_display_name(item.get("workspace", ""), workspace_map)
                assigned = item.get("assignedTo", "") or ""
                # Shorten UUID to 8 chars
                if len(assigned) > 8:
                    assigned = assigned[:8] + "…"
                return [
                    item.get("id", ""),
                    (item.get("name", "") or "")[:35],
                    item.get("type", "") or "",
                    item.get("state", "") or "",
                    assigned,
                    ws_name[:20],
                ]

            # Table: server-side pagination — fetch exactly `take` items per request
            cont: Optional[str] = None
            displayed = 0
            while True:
                page, cont = _fetch_workitems_page(
                    final_filter, subs or None, workspace_id, take, cont
                )
                if not page:
                    if displayed == 0:
                        click.echo("No work items found.")
                    break
                displayed += len(page)
                resp: Any = FilteredResponse({"workItems": page})
                UniversalResponseHandler.handle_list_response(
                    resp=resp,
                    data_key="workItems",
                    item_name="work item",
                    format_output=format_output,
                    formatter_func=_fmt,
                    headers=["ID", "Name", "Type", "State", "Assigned To", "Workspace"],
                    column_widths=[12, 36, 16, 18, 10, 21],
                    empty_message="No work items found.",
                    enable_pagination=False,
                )
                if not cont:
                    break
                click.echo(f"\nShowing {displayed} work item(s). More may be available.")
                if not click.confirm(f"Show next {take} results?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem get
    # -----------------------------------------------------------------------
    @workitem.command(name="get")
    @click.argument("work_item_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_workitem(work_item_id: str, format: str) -> None:
        """Get details for a work item by ID."""
        format_output = validate_output_format(format)

        try:
            url = _wi_url(f"/workitems/{work_item_id}")
            resp = make_api_request("GET", url)
            item: Dict[str, Any] = resp.json()

            if not item:
                click.echo(f"✗ Work item '{work_item_id}' not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            if format_output == "json":
                click.echo(json.dumps(item, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(item.get("workspace", ""), workspace_map)

            click.echo("Work Item Details:")
            click.echo("=" * 50)
            click.echo(f"ID:           {item.get('id', 'N/A')}")
            click.echo(f"Name:         {item.get('name', 'N/A')}")
            click.echo(f"Type:         {item.get('type', 'N/A')}")
            click.echo(f"State:        {item.get('state', 'N/A')}")
            click.echo(f"Substate:     {item.get('substate', 'N/A')}")
            click.echo(f"Description:  {item.get('description', 'N/A')}")
            click.echo(f"Assigned To:  {item.get('assignedTo', 'N/A')}")
            click.echo(f"Requested By: {item.get('requestedBy', 'N/A')}")
            click.echo(f"Part Number:  {item.get('partNumber', 'N/A')}")
            click.echo(f"Test Program: {item.get('testProgram', 'N/A')}")
            click.echo(f"Workspace:    {ws_name}")
            click.echo(f"Workflow ID:  {item.get('workflowId', 'N/A')}")
            click.echo(f"Created At:   {item.get('createdAt', 'N/A')}")
            click.echo(f"Updated At:   {item.get('updatedAt', 'N/A')}")

            if item.get("properties"):
                click.echo("Properties:")
                for k, v in item["properties"].items():
                    click.echo(f"  {k}: {v}")

        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem create
    # -----------------------------------------------------------------------
    @workitem.command(name="create")
    @click.option("--name", "-n", default=None, help="Work item name")
    @click.option("--type", "wi_type", default=None, help="Work item type (e.g. testplan)")
    @click.option(
        "--state",
        "-s",
        default=None,
        help="Initial state (e.g. NEW, DEFINED)",
    )
    @click.option("--description", "-d", default=None, help="Work item description")
    @click.option("--assigned-to", default=None, help="User ID to assign the work item to")
    @click.option(
        "--workflow-id",
        default=None,
        help="ID of the workflow to associate with this work item",
    )
    @click.option("--workspace", "-w", default=None, help="Workspace name or ID")
    @click.option(
        "--part-number",
        default=None,
        help="Part number to associate with this work item",
    )
    @click.option(
        "--file",
        "-F",
        "input_file",
        default=None,
        help=(
            "JSON file with full CreateWorkItemRequest body "
            "(field options override values in file)"
        ),
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def create_workitem(
        name: Optional[str],
        wi_type: Optional[str],
        state: Optional[str],
        description: Optional[str],
        assigned_to: Optional[str],
        workflow_id: Optional[str],
        workspace: Optional[str],
        part_number: Optional[str],
        input_file: Optional[str],
        format: str,
    ) -> None:
        """Create a new work item."""
        from .utils import check_readonly_mode

        check_readonly_mode("create a work item")

        try:
            # Load from file if provided, then overlay CLI options
            wi_data: Dict[str, Any] = {}
            if input_file:
                wi_data = load_json_file(input_file)

            if name is not None:
                wi_data["name"] = name
            if wi_type is not None:
                wi_data["type"] = wi_type
            if state is not None:
                wi_data["state"] = state
            if description is not None:
                wi_data["description"] = description
            if assigned_to is not None:
                wi_data["assignedTo"] = assigned_to
            if workflow_id is not None:
                wi_data["workflowId"] = workflow_id
            if workspace is not None:
                ws_id = get_workspace_id_with_fallback(workspace)
                wi_data["workspace"] = ws_id
            if part_number is not None:
                wi_data["partNumber"] = part_number

            url = _wi_url("/workitems")
            payload = {"workItems": [wi_data]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            if resp.status_code in (200, 201):
                created = data.get("createdWorkItems", [])
                if created:
                    item = created[0]
                    if format == "json":
                        click.echo(json.dumps(item, indent=2))
                    else:
                        format_success(
                            "Work item created",
                            {"id": item.get("id", ""), "name": item.get("name", "")},
                        )
                else:
                    # Partial success - check failedWorkItems
                    failed = data.get("failedWorkItems", [])
                    if failed:
                        click.echo("✗ Failed to create work item.", err=True)
                        display_api_errors("Work item creation failed", data, detailed=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
                    click.echo("✓ Work item created.")
            else:
                display_api_errors("Work item creation failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem update
    # -----------------------------------------------------------------------
    @workitem.command(name="update")
    @click.argument("work_item_id")
    @click.option("--name", "-n", default=None, help="New name")
    @click.option("--state", "-s", default=None, help="New state")
    @click.option("--description", "-d", default=None, help="New description")
    @click.option("--assigned-to", default=None, help="User ID to reassign to")
    @click.option(
        "--file",
        "-F",
        "input_file",
        default=None,
        help=(
            "JSON file with UpdateWorkItemRequest fields " "(field options override values in file)"
        ),
    )
    def update_workitem(
        work_item_id: str,
        name: Optional[str],
        state: Optional[str],
        description: Optional[str],
        assigned_to: Optional[str],
        input_file: Optional[str],
    ) -> None:
        """Update a work item by ID."""
        from .utils import check_readonly_mode

        check_readonly_mode("update a work item")

        try:
            wi_data: Dict[str, Any] = {"id": work_item_id}
            if input_file:
                file_data = load_json_file(input_file)
                wi_data.update(file_data)
                wi_data["id"] = work_item_id  # ID always from arg

            if name is not None:
                wi_data["name"] = name
            if state is not None:
                wi_data["state"] = state
            if description is not None:
                wi_data["description"] = description
            if assigned_to is not None:
                wi_data["assignedTo"] = assigned_to

            url = _wi_url("/update-workitems")
            payload = {"workItems": [wi_data]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            if resp.status_code == 200:
                updated = data.get("updatedWorkItems", [])
                if updated:
                    click.echo(f"✓ Work item {work_item_id} updated successfully.")
                else:
                    failed = data.get("failedWorkItems", [])
                    if failed:
                        click.echo(f"✗ Failed to update work item {work_item_id}.", err=True)
                        display_api_errors("Work item update failed", data, detailed=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                display_api_errors("Work item update failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem delete
    # -----------------------------------------------------------------------
    @workitem.command(name="delete")
    @click.argument("work_item_ids", nargs=-1, required=True)
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    def delete_workitems(work_item_ids: tuple, yes: bool) -> None:
        """Delete one or more work items by ID."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete work items")

        ids_list = list(work_item_ids)
        if not yes:
            id_str = ", ".join(ids_list)
            if not click.confirm(f"Delete work item(s) {id_str}?"):
                click.echo("Aborted.")
                return

        try:
            url = _wi_url("/delete-workitems")
            payload = {"ids": ids_list}
            resp = make_api_request("POST", url, payload, handle_errors=False)

            if resp.status_code == 204:
                click.echo(f"✓ Work item(s) deleted successfully.")
                return

            data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 200:
                deleted = data.get("deletedWorkItemIds", [])
                failed = data.get("failedWorkItemIds", [])
                if deleted:
                    click.echo(f"✓ Deleted: {', '.join(deleted)}")
                if failed:
                    click.echo(f"✗ Failed to delete: {', '.join(failed)}", err=True)
                    display_api_errors("Work item deletion failed", data, detailed=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                display_api_errors("Work item deletion failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem execute
    # -----------------------------------------------------------------------
    @workitem.command(name="execute")
    @click.argument("work_item_id")
    @click.option(
        "--action",
        "-a",
        required=True,
        help="Action to execute (e.g. START, END, COMPLETE)",
    )
    def execute_workitem(work_item_id: str, action: str) -> None:
        """Execute an action on a work item (e.g. START, END)."""
        from .utils import check_readonly_mode

        check_readonly_mode("execute an action on a work item")

        try:
            url = _wi_url(f"/workitems/{work_item_id}/execute")
            payload = {"action": action.upper()}
            resp = make_api_request("POST", url, payload, handle_errors=False)

            if resp.status_code in (200, 202):
                data = resp.json() if resp.text.strip() else {}
                result = data.get("result", {})
                if result:
                    click.echo(f"✓ Action '{action.upper()}' executed on work item {work_item_id}.")
                    if isinstance(result, dict) and result.get("type"):
                        click.echo(f"  Execution type: {result['type']}")
                else:
                    click.echo(f"✓ Action '{action.upper()}' executed on work item {work_item_id}.")
            else:
                data = resp.json() if resp.text.strip() else {}
                display_api_errors("Work item execution failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # -----------------------------------------------------------------------
    # workitem schedule
    # -----------------------------------------------------------------------
    @workitem.command(name="schedule")
    @click.argument("work_item_id")
    @click.option(
        "--start",
        default=None,
        help="Planned start date/time (ISO-8601, e.g. 2026-03-01T09:00:00Z)",
    )
    @click.option(
        "--end",
        default=None,
        help="Planned end date/time (ISO-8601)",
    )
    @click.option(
        "--duration",
        type=int,
        default=None,
        help="Planned duration in seconds",
    )
    @click.option("--assigned-to", default=None, help="User ID to assign")
    def schedule_workitem(
        work_item_id: str,
        start: Optional[str],
        end: Optional[str],
        duration: Optional[int],
        assigned_to: Optional[str],
    ) -> None:
        """Schedule a work item (set planned start/end time)."""
        from .utils import check_readonly_mode

        check_readonly_mode("schedule a work item")

        if not any([start, end, duration, assigned_to]):
            click.echo(
                "✗ Provide at least one of --start, --end, --duration, or --assigned-to.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            schedule: Dict[str, Any] = {}
            if start:
                schedule["plannedStartDateTime"] = start
            if end:
                schedule["plannedEndDateTime"] = end
            if duration is not None:
                schedule["plannedDurationInSeconds"] = duration

            wi_req: Dict[str, Any] = {"id": work_item_id}
            if schedule:
                wi_req["schedule"] = schedule
            if assigned_to:
                wi_req["assignedTo"] = assigned_to

            url = _wi_url("/schedule-workitems")
            payload = {"workItems": [wi_req]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 200:
                scheduled = data.get("scheduledWorkItems", [])
                if scheduled:
                    click.echo(f"✓ Work item {work_item_id} scheduled successfully.")
                else:
                    failed = data.get("failedWorkItems", [])
                    if failed:
                        click.echo(f"✗ Failed to schedule work item {work_item_id}.", err=True)
                        display_api_errors("Work item scheduling failed", data, detailed=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                display_api_errors("Work item scheduling failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # =======================================================================
    # workitem template subgroup
    # =======================================================================

    @workitem.group(name="template")
    def template_group() -> None:
        """Manage work item templates."""

    @template_group.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of templates to display per page (table) or fetch (json)",
    )
    @click.option(
        "--filter",
        "filter_expr",
        default=None,
        help="Dynamic LINQ filter expression",
    )
    @click.option("--workspace", "-w", default=None, help="Filter by workspace name or ID")
    def list_templates(
        format: str,
        take: int,
        filter_expr: Optional[str],
        workspace: Optional[str],
    ) -> None:
        """List work item templates."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            if format_output == "json":
                items = _query_all_templates(filter_expr, None, workspace_id, max_items=take)
                click.echo(json.dumps(items, indent=2))
                return

            # Table: server-side pagination
            def _fmt(item: Dict[str, Any]) -> list:
                ws_name = get_workspace_display_name(item.get("workspace", ""), workspace_map)
                return [
                    item.get("id", ""),
                    (item.get("name", "") or "")[:40],
                    item.get("type", "") or "",
                    item.get("templateGroup", "") or "",
                    ws_name[:20],
                ]

            cont: Optional[str] = None
            displayed = 0
            while True:
                page, cont = _fetch_templates_page(filter_expr, None, workspace_id, take, cont)
                if not page:
                    if displayed == 0:
                        click.echo("No templates found.")
                    break
                displayed += len(page)
                resp: Any = FilteredResponse({"workItemTemplates": page})
                UniversalResponseHandler.handle_list_response(
                    resp=resp,
                    data_key="workItemTemplates",
                    item_name="template",
                    format_output=format_output,
                    formatter_func=_fmt,
                    headers=["ID", "Name", "Type", "Template Group", "Workspace"],
                    column_widths=[12, 41, 16, 20, 21],
                    empty_message="No templates found.",
                    enable_pagination=False,
                )
                if not cont:
                    break
                click.echo(f"\nShowing {displayed} template(s). More may be available.")
                if not click.confirm(f"Show next {take} results?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="get")
    @click.argument("template_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_template(template_id: str, format: str) -> None:
        """Get details for a work item template by ID."""
        format_output = validate_output_format(format)

        try:
            url = _wi_url("/query-workitem-templates")
            payload = {
                "filter": f"id == @0",
                "substitutions": [template_id],
                "take": 1,
            }
            resp = make_api_request("POST", url, payload)
            data = resp.json()
            items = data.get("workItemTemplates", [])

            if not items:
                click.echo(f"✗ Template '{template_id}' not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            item = items[0]

            if format_output == "json":
                click.echo(json.dumps(item, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(item.get("workspace", ""), workspace_map)

            click.echo("Work Item Template Details:")
            click.echo("=" * 50)
            click.echo(f"ID:             {item.get('id', 'N/A')}")
            click.echo(f"Name:           {item.get('name', 'N/A')}")
            click.echo(f"Type:           {item.get('type', 'N/A')}")
            click.echo(f"Template Group: {item.get('templateGroup', 'N/A')}")
            click.echo(f"Summary:        {item.get('summary', 'N/A')}")
            click.echo(f"Description:    {item.get('description', 'N/A')}")
            click.echo(f"Test Program:   {item.get('testProgram', 'N/A')}")
            click.echo(f"Workspace:      {ws_name}")
            click.echo(f"Created At:     {item.get('createdAt', 'N/A')}")
            click.echo(f"Updated At:     {item.get('updatedAt', 'N/A')}")

            if item.get("partNumbers"):
                click.echo(f"Part Numbers:   {', '.join(item['partNumbers'])}")
            if item.get("productFamilies"):
                click.echo(f"Product Families: {', '.join(item['productFamilies'])}")
            if item.get("properties"):
                click.echo("Properties:")
                for k, v in item["properties"].items():
                    click.echo(f"  {k}: {v}")

        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="create")
    @click.option("--name", "-n", required=False, default=None, help="Template name")
    @click.option("--type", "wi_type", default=None, help="Work item type (e.g. testplan)")
    @click.option("--template-group", default=None, help="Template group label")
    @click.option("--description", "-d", default=None, help="Template description")
    @click.option("--summary", default=None, help="Template summary")
    @click.option("--workspace", "-w", default=None, help="Workspace name or ID")
    @click.option(
        "--file",
        "-F",
        "input_file",
        default=None,
        help="JSON file with full CreateWorkItemTemplateRequest body",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def create_template(
        name: Optional[str],
        wi_type: Optional[str],
        template_group: Optional[str],
        description: Optional[str],
        summary: Optional[str],
        workspace: Optional[str],
        input_file: Optional[str],
        format: str,
    ) -> None:
        """Create a new work item template."""
        from .utils import check_readonly_mode

        check_readonly_mode("create a work item template")

        if not input_file and not (name and wi_type and template_group):
            click.echo(
                "✗ Provide --file or all of --name, --type, and --template-group.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            tmpl_data: Dict[str, Any] = {}
            if input_file:
                tmpl_data = load_json_file(input_file)

            if name is not None:
                tmpl_data["name"] = name
            if wi_type is not None:
                tmpl_data["type"] = wi_type
            if template_group is not None:
                tmpl_data["templateGroup"] = template_group
            if description is not None:
                tmpl_data["description"] = description
            if summary is not None:
                tmpl_data["summary"] = summary
            if workspace is not None:
                ws_id = get_workspace_id_with_fallback(workspace)
                tmpl_data["workspace"] = ws_id

            url = _wi_url("/workitem-templates")
            payload = {"workItemTemplates": [tmpl_data]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            if resp.status_code in (200, 201):
                created = data.get("createdWorkItemTemplates", [])
                if created:
                    item = created[0]
                    if format == "json":
                        click.echo(json.dumps(item, indent=2))
                    else:
                        format_success(
                            "Template created",
                            {"id": item.get("id", ""), "name": item.get("name", "")},
                        )
                else:
                    failed = data.get("failedWorkItemTemplates", [])
                    if failed:
                        click.echo("✗ Failed to create template.", err=True)
                        display_api_errors("Template creation failed", data, detailed=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
                    click.echo("✓ Template created.")
            else:
                display_api_errors("Template creation failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="update")
    @click.argument("template_id")
    @click.option("--name", "-n", default=None, help="New name")
    @click.option("--description", "-d", default=None, help="New description")
    @click.option("--summary", default=None, help="New summary")
    @click.option("--template-group", default=None, help="New template group")
    @click.option(
        "--file",
        "-F",
        "input_file",
        default=None,
        help="JSON file with UpdateWorkItemTemplateRequest fields",
    )
    def update_template(
        template_id: str,
        name: Optional[str],
        description: Optional[str],
        summary: Optional[str],
        template_group: Optional[str],
        input_file: Optional[str],
    ) -> None:
        """Update a work item template by ID."""
        from .utils import check_readonly_mode

        check_readonly_mode("update a work item template")

        try:
            tmpl_data: Dict[str, Any] = {"id": template_id}
            if input_file:
                file_data = load_json_file(input_file)
                tmpl_data.update(file_data)
                tmpl_data["id"] = template_id

            if name is not None:
                tmpl_data["name"] = name
            if description is not None:
                tmpl_data["description"] = description
            if summary is not None:
                tmpl_data["summary"] = summary
            if template_group is not None:
                tmpl_data["templateGroup"] = template_group

            url = _wi_url("/update-workitem-templates")
            payload = {"workItemTemplates": [tmpl_data]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            if resp.status_code == 200:
                updated = data.get("updatedWorkItemTemplates", [])
                if updated:
                    click.echo(f"✓ Template {template_id} updated successfully.")
                else:
                    failed = data.get("failedWorkItemTemplates", [])
                    if failed:
                        click.echo(f"✗ Failed to update template {template_id}.", err=True)
                        display_api_errors("Template update failed", data, detailed=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                display_api_errors("Template update failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="delete")
    @click.argument("template_ids", nargs=-1, required=True)
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    def delete_templates(template_ids: tuple, yes: bool) -> None:
        """Delete one or more work item templates by ID."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete work item templates")

        ids_list = list(template_ids)
        if not yes:
            if not click.confirm(f"Delete template(s) {', '.join(ids_list)}?"):
                click.echo("Aborted.")
                return

        try:
            url = _wi_url("/delete-workitem-templates")
            payload = {"ids": ids_list}
            resp = make_api_request("POST", url, payload, handle_errors=False)

            if resp.status_code == 204:
                click.echo("✓ Template(s) deleted successfully.")
                return

            data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 200:
                deleted = data.get("deletedWorkItemTemplateIds", [])
                failed = data.get("failedWorkItemTemplateIds", [])
                if deleted:
                    click.echo(f"✓ Deleted: {', '.join(deleted)}")
                if failed:
                    click.echo(f"✗ Failed to delete: {', '.join(failed)}", err=True)
                    display_api_errors("Template deletion failed", data, detailed=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                display_api_errors("Template deletion failed", data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # =======================================================================
    # workitem workflow subgroup  (refactored from workflows_click.py)
    # =======================================================================

    @workitem.group(name="workflow")
    @click.pass_context
    def workflow_group(ctx: click.Context) -> None:
        """Manage workflows (create, list, import/export, update, delete, preview)."""
        # Check for platform feature availability
        # Only check if a subcommand is being invoked (not just --help)
        if ctx.invoked_subcommand is not None:
            require_feature("workflows")

    @workflow_group.command(name="init")
    @click.option("--name", "-n", help="Workflow name (will prompt if not provided)")
    @click.option("--description", "-d", help="Workflow description (will prompt if omitted)")
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (default: 'Default')",
    )
    @click.option("--output", "-o", help="Output file path (default: <name>-workflow.json)")
    def init_workflow(
        name: Optional[str],
        description: Optional[str],
        workspace: str,
        output: Optional[str],
    ) -> None:
        """Create a workflow JSON skeleton."""
        if not name:
            name = click.prompt("Workflow name", type=str)
        if not description:
            description = click.prompt("Workflow description", type=str, default="")

        if not output:
            assert name is not None
            safe_name = sanitize_filename(name, "workflow")
            output = f"{safe_name}-workflow.json"

        try:
            workspace_id = get_workspace_id_with_fallback(workspace)
        except Exception as exc:
            click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        workflow_data = {
            "name": name,
            "description": description,
            "workspace": workspace_id,
            "actions": [
                {
                    "name": "START",
                    "displayText": "Start",
                    "privilegeSpecificity": ["ExecuteTest"],
                    "executionAction": {"type": "MANUAL", "action": "START"},
                },
                {
                    "name": "COMPLETE",
                    "displayText": "Complete",
                    "privilegeSpecificity": ["Close"],
                    "executionAction": {"type": "MANUAL", "action": "COMPLETE"},
                },
                {
                    "name": "RUN_NOTEBOOK",
                    "displayText": "Run Notebook",
                    "iconClass": None,
                    "i18n": [],
                    "privilegeSpecificity": ["ExecuteTest"],
                    "executionAction": {
                        "action": "RUN_NOTEBOOK",
                        "type": "NOTEBOOK",
                        "notebookId": "00000000-0000-0000-0000-000000000000",
                        "parameters": {
                            "partNumber": "<partNumber>",
                            "dut": "<dutId>",
                            "operator": "<assignedTo>",
                            "testProgram": "<testProgram>",
                            "location": "<properties.region>-<properties.facility>-<properties.lab>",
                        },
                    },
                },
                {
                    "name": "PLAN_SCHEDULE",
                    "displayText": "Schedule Test Plan",
                    "iconClass": "SCHEDULE",
                    "i18n": [],
                    "privilegeSpecificity": [],
                    "executionAction": {"action": "PLAN_SCHEDULE", "type": "SCHEDULE"},
                },
                {
                    "name": "RUN_JOB",
                    "displayText": "Run Job",
                    "iconClass": "DEPLOY",
                    "i18n": [],
                    "privilegeSpecificity": [],
                    "executionAction": {
                        "action": "RUN_JOB",
                        "type": "JOB",
                        "jobs": [
                            {
                                "functions": ["state.apply"],
                                "arguments": [["<properties.startTestStateId>"]],
                                "metadata": {},
                            }
                        ],
                    },
                },
            ],
            "states": [
                {
                    "name": "NEW",
                    "dashboardAvailable": False,
                    "defaultSubstate": "NEW",
                    "substates": [
                        {
                            "name": "NEW",
                            "displayText": "New",
                            "availableActions": [
                                {
                                    "action": "PLAN_SCHEDULE",
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
                    "dashboardAvailable": True,
                    "defaultSubstate": "SCHEDULED",
                    "substates": [
                        {
                            "name": "SCHEDULED",
                            "displayText": "Scheduled",
                            "availableActions": [
                                {
                                    "action": "START",
                                    "nextState": "IN_PROGRESS",
                                    "nextSubstate": "IN_PROGRESS",
                                    "showInUI": True,
                                },
                                {
                                    "action": "RUN_NOTEBOOK",
                                    "nextState": "IN_PROGRESS",
                                    "nextSubstate": "IN_PROGRESS",
                                    "showInUI": True,
                                },
                            ],
                        }
                    ],
                },
                {
                    "name": "IN_PROGRESS",
                    "dashboardAvailable": True,
                    "defaultSubstate": "IN_PROGRESS",
                    "substates": [
                        {
                            "name": "IN_PROGRESS",
                            "displayText": "In progress",
                            "availableActions": [
                                {
                                    "action": "COMPLETE",
                                    "nextState": "PENDING_APPROVAL",
                                    "nextSubstate": "PENDING_APPROVAL",
                                    "showInUI": True,
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "PENDING_APPROVAL",
                    "dashboardAvailable": True,
                    "defaultSubstate": "PENDING_APPROVAL",
                    "substates": [
                        {
                            "name": "PENDING_APPROVAL",
                            "displayText": "Pending approval",
                            "availableActions": [
                                {
                                    "action": "RUN_JOB",
                                    "nextState": "CLOSED",
                                    "nextSubstate": "CLOSED",
                                    "showInUI": True,
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "CLOSED",
                    "dashboardAvailable": False,
                    "defaultSubstate": "CLOSED",
                    "substates": [
                        {"name": "CLOSED", "displayText": "Closed", "availableActions": []}
                    ],
                },
                {
                    "name": "CANCELED",
                    "dashboardAvailable": False,
                    "defaultSubstate": "CANCELED",
                    "substates": [
                        {
                            "name": "CANCELED",
                            "displayText": "Canceled",
                            "availableActions": [],
                        }
                    ],
                },
            ],
        }

        try:
            if os.path.exists(output):
                if not click.confirm(f"File {output} already exists. Overwrite?"):
                    click.echo("Workflow initialization cancelled.")
                    return

            with open(output, "w", encoding="utf-8") as fh:
                json.dump(workflow_data, fh, indent=2, ensure_ascii=False)

            click.echo(f"✓ Workflow initialized: {output}")
            click.echo("Edit the file to customize your workflow:")
            click.echo("  - name and description are recommended")
            click.echo("  - Define states, substates, and actions as needed")
            click.echo(f"  - Workspace is set to: {workspace} (ID: {workspace_id})")
            click.echo("  - Use 'slcli workitem workflow import' to upload when ready")

        except Exception as exc:
            click.echo(f"✗ Error creating workflow file: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

    @workflow_group.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of workflows to display per page",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_workflows(
        workspace: Optional[str],
        take: int,
        format: str,
    ) -> None:
        """List workflows."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            if format_output == "json":
                all_workflows = _query_all_workflows(workspace_id, max_items=take)
                click.echo(json.dumps(all_workflows, indent=2))
                return

            # Table: server-side pagination
            def _wf_fmt(wf: Dict[str, Any]) -> list:
                ws_name = get_workspace_display_name(wf.get("workspace", ""), workspace_map)
                return [
                    wf.get("name", "Unknown"),
                    ws_name,
                    wf.get("id", ""),
                    (wf.get("description", "") or "")[:30],
                ]

            cont: Optional[str] = None
            displayed = 0
            while True:
                page, cont = _fetch_workflows_page(workspace_id, take, cont)
                if not page:
                    if displayed == 0:
                        click.echo("No workflows found.")
                    break
                displayed += len(page)
                resp: Any = FilteredResponse({"workflows": page})
                UniversalResponseHandler.handle_list_response(
                    resp=resp,
                    data_key="workflows",
                    item_name="workflow",
                    format_output=format_output,
                    formatter_func=_wf_fmt,
                    headers=["Name", "Workspace", "ID", "Description"],
                    column_widths=[40, 30, 36, 32],
                    empty_message="No workflows found.",
                    enable_pagination=False,
                )
                if not cont:
                    break
                click.echo(f"\nShowing {displayed} workflow(s). More may be available.")
                if not click.confirm(f"Show next {take} results?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="get")
    @click.option("--id", "-i", "workflow_id", help="Workflow ID")
    @click.option("--name", "-n", "workflow_name", help="Workflow name")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_workflow(
        workflow_id: Optional[str],
        workflow_name: Optional[str],
        format: str,
    ) -> None:
        """Show workflow details by ID or name."""
        if not workflow_id and not workflow_name:
            click.echo("✗ Must provide either --id or --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        if workflow_id and workflow_name:
            click.echo("✗ Cannot specify both --id and --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        format_output = validate_output_format(format)

        try:
            if workflow_name:
                query_url = _wf_url("/query-workflows")
                query_resp = make_api_request(
                    "POST",
                    query_url,
                    {"take": 1000, "filter": f'NAME == "{workflow_name}"'},
                )
                workflows = query_resp.json().get("workflows", [])
                matching = [w for w in workflows if w.get("name") == workflow_name]
                if not matching:
                    click.echo(f"✗ Workflow '{workflow_name}' not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
                workflow_id = matching[0].get("id", "")

            url = _wf_url(f"/workflows/{workflow_id}")
            resp = make_api_request("GET", url)
            wfl = resp.json()

            if not wfl:
                click.echo(f"✗ Workflow '{workflow_id}' not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            if format_output == "json":
                click.echo(json.dumps(wfl, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(wfl.get("workspace", ""), workspace_map)
            click.echo("Workflow Details:")
            click.echo("=" * 50)
            click.echo(f"Name:         {wfl.get('name', 'N/A')}")
            click.echo(f"ID:           {wfl.get('id', 'N/A')}")
            click.echo(f"Workspace:    {ws_name}")
            click.echo(f"Description:  {wfl.get('description', 'N/A')}")

        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="export")
    @click.option("--id", "-i", "workflow_id", help="Workflow ID to export")
    @click.option("--name", "-n", "workflow_name", help="Workflow name to export")
    @click.option("--output", "-o", help="Output JSON file (default: <name>.json)")
    def export_workflow(
        workflow_id: Optional[str],
        workflow_name: Optional[str],
        output: Optional[str],
    ) -> None:
        """Export a workflow to a JSON file."""
        if not workflow_id and not workflow_name:
            click.echo("✗ Must provide either --id or --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        if workflow_id and workflow_name:
            click.echo("✗ Cannot specify both --id and --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        if workflow_name:
            query_url = _wf_url("/query-workflows")
            query_resp = make_api_request(
                "POST",
                query_url,
                {"take": 1000, "filter": f'NAME == "{workflow_name}"'},
            )
            workflows = query_resp.json().get("workflows", [])
            matching = [w for w in workflows if w.get("name") == workflow_name]
            if not matching:
                click.echo(f"✗ Workflow '{workflow_name}' not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)
            workflow_id = matching[0].get("id", "")

        url = _wf_url(f"/workflows/{workflow_id}")
        try:
            resp = make_api_request("GET", url)
            data = resp.json()

            if not data:
                click.echo(f"✗ Workflow '{workflow_id}' not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            if not output:
                wf_name = data.get("name", f"workflow-{workflow_id}")
                safe = sanitize_filename(wf_name, f"workflow-{workflow_id}")
                output = f"{safe}.json"

            save_json_file(data, output)
            click.echo(f"✓ Workflow exported to {output}")
        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="import")
    @click.option("--file", "input_file", required=True, help="Input JSON file")
    @click.option(
        "--workspace",
        "-w",
        help="Override workspace name or ID (uses value from file if not specified)",
    )
    def import_workflow(input_file: str, workspace: Optional[str]) -> None:
        """Import a workflow from JSON.

        Workspace can be specified via --workspace or in the JSON file.
        The command line takes precedence over the file.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("import a workflow")

        url = _wf_url("/workflows")
        allowed_fields = {"name", "description", "actions", "states", "workspace"}

        try:
            data = load_json_file(input_file)
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

            if workspace:
                try:
                    ws_id = get_workspace_id_with_fallback(workspace)
                    filtered_data["workspace"] = ws_id
                except Exception as exc:
                    click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
            elif "workspace" not in filtered_data or not filtered_data["workspace"]:
                click.echo(
                    "✗ Workspace required. Use --workspace or include 'workspace' in JSON.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            elif filtered_data["workspace"] and not filtered_data["workspace"].startswith("//"):
                try:
                    ws_id = get_workspace_id_with_fallback(filtered_data["workspace"])
                    filtered_data["workspace"] = ws_id
                except Exception as exc:
                    click.echo(
                        f"✗ Error resolving workspace '{filtered_data['workspace']}': {exc}",
                        err=True,
                    )
                    sys.exit(ExitCodes.NOT_FOUND)

            try:
                resp = make_api_request("POST", url, filtered_data, handle_errors=False)
                if resp.status_code == 201:
                    response_data = resp.json() if resp.text.strip() else {}
                    wf_id = response_data.get("id", "")
                    if wf_id:
                        click.echo(f"✓ Workflow imported successfully with ID: {wf_id}")
                    else:
                        click.echo("✓ Workflow imported successfully.")
                else:
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_error_response(response_data, "Workflow import failed")
            except requests.exceptions.HTTPError as http_exc:
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_error_response(response_data, "Workflow import failed")
                    except Exception:
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)

        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="delete")
    @click.option("--id", "-i", "workflow_id", required=True, help="Workflow ID to delete")
    @click.confirmation_option(prompt="Are you sure you want to delete this workflow?")
    def delete_workflow(workflow_id: str) -> None:
        """Delete a workflow by ID."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete a workflow")

        url = _wf_url("/delete-workflows")
        payload = {"ids": [workflow_id]}
        try:
            try:
                resp = make_api_request("POST", url, payload, handle_errors=False)
                if resp.status_code in (200, 204):
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_delete_response(response_data, workflow_id)
                else:
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_delete_response(response_data, workflow_id)
            except requests.exceptions.HTTPError as http_exc:
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_delete_response(response_data, workflow_id)
                    except Exception:
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)
        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="update")
    @click.option("--id", "-i", "workflow_id", required=True, help="Workflow ID to update")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="JSON file with updated workflow data",
    )
    @click.option("--workspace", "-w", help="Override workspace name or ID")
    def update_workflow(workflow_id: str, input_file: str, workspace: Optional[str]) -> None:
        """Update a workflow from JSON."""
        from .utils import check_readonly_mode

        check_readonly_mode("update a workflow")

        url = _wf_url(f"/workflows/{workflow_id}")
        allowed_fields = {"name", "description", "actions", "states", "workspace"}
        try:
            data = load_json_file(input_file)
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

            if workspace:
                try:
                    ws_id = get_workspace_id_with_fallback(workspace)
                    filtered_data["workspace"] = ws_id
                except Exception as exc:
                    click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
            elif (
                "workspace" in filtered_data
                and filtered_data["workspace"]
                and not filtered_data["workspace"].startswith("//")
            ):
                try:
                    ws_id = get_workspace_id_with_fallback(filtered_data["workspace"])
                    filtered_data["workspace"] = ws_id
                except Exception as exc:
                    click.echo(
                        f"✗ Error resolving workspace '{filtered_data['workspace']}': {exc}",
                        err=True,
                    )
                    sys.exit(ExitCodes.NOT_FOUND)

            try:
                resp = make_api_request("PUT", url, filtered_data, handle_errors=False)
                if resp.status_code == 200:
                    click.echo(f"✓ Workflow {workflow_id} updated successfully.")
                else:
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_error_response(response_data, "Workflow update failed")
            except requests.exceptions.HTTPError as http_exc:
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_error_response(response_data, "Workflow update failed")
                    except Exception:
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)

        except Exception as exc:
            handle_api_error(exc)

    @workflow_group.command(name="preview")
    @click.option("--id", "-i", "workflow_id", help="Workflow ID to preview")
    @click.option(
        "--file",
        "-f",
        "input_file",
        help="Local JSON file to preview (use '-' for stdin)",
    )
    @click.option("--output", "-o", help="Output file path (default: open in browser)")
    @click.option(
        "--format",
        type=click.Choice(["html", "mmd"]),
        default="html",
        show_default=True,
        help="Output format",
    )
    @click.option("--no-emoji", is_flag=True, default=False, help="Disable emoji in action labels")
    @click.option("--no-legend", is_flag=True, default=False, help="Disable legend in HTML output")
    @click.option(
        "--no-open",
        is_flag=True,
        default=False,
        help="Do not auto-open browser when no --output provided",
    )
    def preview_workflow(
        workflow_id: Optional[str],
        input_file: Optional[str],
        output: Optional[str],
        format: str,
        no_emoji: bool,
        no_legend: bool,
        no_open: bool,
    ) -> None:
        """Preview a workflow as an HTML diagram or Mermaid file."""
        if bool(workflow_id) == bool(input_file):
            click.echo(
                "✗ Must specify exactly one of --id or --file (use --file - for stdin)",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            workflow_data: Dict[str, Any]
            if workflow_id:
                url = _wf_url(f"/workflows/{workflow_id}")
                resp = make_api_request("GET", url)
                workflow_data = resp.json()
                if not workflow_data:
                    click.echo(f"✗ Workflow with ID {workflow_id} not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
            else:
                if input_file == "-":
                    try:
                        workflow_data = json.loads(sys.stdin.read())
                    except json.JSONDecodeError as exc:
                        click.echo(f"✗ Invalid JSON from stdin: {exc}", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                else:
                    assert input_file is not None
                    workflow_data = load_json_file(input_file)

            mermaid_code = workflow_preview.generate_mermaid_diagram(
                workflow_data, enable_emoji=not no_emoji
            )

            if format == "mmd":
                if not output:
                    output = f"workflow-{workflow_data.get('name', 'preview')}.mmd"
                with open(output, "w", encoding="utf-8") as fh:
                    fh.write(mermaid_code)
                click.echo(f"✓ Mermaid diagram saved to {output}")
            else:
                html_content = workflow_preview.generate_html_with_mermaid(
                    workflow_data, mermaid_code, include_legend=not no_legend
                )
                if output:
                    with open(output, "w", encoding="utf-8") as fh:
                        fh.write(html_content)
                    click.echo(f"✓ HTML preview saved to {output}")
                elif not no_open:
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".html", delete=False, encoding="utf-8"
                    ) as fh:
                        fh.write(html_content)
                        temp_file = fh.name
                    webbrowser.open(f"file://{Path(temp_file).absolute()}")
                    click.echo("✓ Opening workflow preview in browser...")
                else:
                    click.echo(html_content)

        except Exception as exc:
            handle_api_error(exc)

"""CLI commands for managing SystemLink workspaces."""

import json
import sys
from typing import Any, Dict, Optional, Tuple

import click

from .cli_utils import validate_output_format
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)


def _fetch_workspaces_page(
    name_filter: Optional[str] = None, take: int = 25, skip: int = 0
) -> Tuple[list, int, Optional[str]]:
    """Fetch a single page of workspaces with optional server-side filtering.

    Args:
        name_filter: Optional filter pattern for workspace name (uses *TEXT* format
                     for case-insensitive substring matching)
        take: Number of items to fetch (max 100)
        skip: Number of items to skip

    Returns:
        Tuple of (workspaces_list, total_count, error_message).
        Error message is None if successful.
    """
    try:
        url = f"{get_base_url()}/niuser/v1/workspaces"
        page_size = min(take, 100)  # API max take is 100

        query_params = [f"take={page_size}", f"skip={skip}"]
        if name_filter:
            # Use *TEXT* pattern for case-insensitive substring matching
            query_params.append(f"name=*{name_filter}*")

        paginated_url = url + "?" + "&".join(query_params)

        resp = make_api_request("GET", paginated_url, payload=None)
        data = resp.json()

        workspaces = data.get("workspaces", [])
        total_count = data.get("totalCount", 0)

        return workspaces, total_count, None
    except Exception as exc:
        return [], 0, f"Failed to fetch workspaces: {str(exc)}"


def register_workspace_commands(cli: Any) -> None:
    """Register the 'workspace' command group and its subcommands."""

    @cli.group()
    def workspace() -> None:
        """Manage workspaces."""
        pass

    @workspace.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--include-disabled",
        is_flag=True,
        help="Include disabled workspaces in the results",
    )
    @click.option(
        "--filter",
        "name_filter",
        help="Filter by workspace name (case-insensitive substring match)",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of workspaces to return from API",
    )
    def list_workspaces(
        format: str = "table",
        include_disabled: bool = False,
        name_filter: Optional[str] = None,
        take: int = 25,
    ) -> None:
        """List workspaces with optional filtering.

        The --filter option performs server-side case-insensitive substring
        matching on workspace names. The --take option limits the number of
        results shown per page (max 100).
        """
        format_output = validate_output_format(format)

        try:
            # For JSON format, respect --take and output without interactive pagination
            if format_output.lower() == "json":
                all_workspaces = []
                skip = 0
                remaining = take if take and take > 0 else 25
                while remaining > 0:
                    page_take = min(remaining, 100)
                    workspaces, total_count, error = _fetch_workspaces_page(
                        name_filter, take=page_take, skip=skip
                    )
                    if error:
                        click.echo(f"✗ {error}", err=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)

                    # Filter by enabled status if needed
                    if not include_disabled:
                        workspaces = [ws for ws in workspaces if ws.get("enabled", True)]

                    all_workspaces.extend(workspaces)

                    # Stop when we've collected the requested amount or reached total
                    if len(all_workspaces) >= take or skip + page_take >= total_count:
                        break

                    skip += page_take
                    remaining = take - len(all_workspaces)

                # Trim in case we over-collected due to page boundaries
                if take:
                    all_workspaces = all_workspaces[:take]
                click.echo(json.dumps(all_workspaces, indent=2))
                return

            # For table format, implement interactive lazy loading
            skip = 0
            total_count_from_api = 0
            shown_count = 0

            def workspace_formatter(workspace: dict) -> list:
                enabled = "✓" if workspace.get("enabled", True) else "✗"
                default = "✓" if workspace.get("default", False) else ""
                return [workspace.get("name", "Unknown"), workspace.get("id", ""), enabled, default]

            while True:
                # Fetch next page
                workspaces, total_count_from_api, error = _fetch_workspaces_page(
                    name_filter, take=take, skip=skip
                )

                if error:
                    click.echo(f"✗ {error}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

                # Filter by enabled status if needed
                if not include_disabled:
                    workspaces = [ws for ws in workspaces if ws.get("enabled", True)]

                if not workspaces and skip == 0:
                    click.echo("No workspaces found.")
                    return

                if not workspaces:
                    # No more results on this page
                    break

                # Display the page
                from .table_utils import output_formatted_list

                output_formatted_list(
                    workspaces,
                    format_output,
                    ["Name", "ID", "Enabled", "Default"],
                    [30, 36, 8, 8],
                    workspace_formatter,
                    "",  # Empty message not needed here
                    "workspace(s)",
                )

                shown_count += len(workspaces)
                skip += take

                # Check if there are potentially more results from the API
                # We check skip against total_count to see if the next page exists
                if skip >= total_count_from_api:
                    break

                # Ask user if they want to see more; if non-interactive, stop
                click.echo(f"\nShowing {shown_count} workspace(s) so far. More may be available.")

                try:
                    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
                except Exception:
                    is_tty = False

                if not is_tty:
                    break
                if not click.confirm("Show next page?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    @workspace.command(name="disable")
    @click.option(
        "--id",
        "-i",
        required=True,
        help="ID of the workspace to disable",
    )
    @click.confirmation_option(prompt="Are you sure you want to disable this workspace?")
    def disable_workspace(id: str) -> None:
        """Disable a workspace."""
        try:
            # Get workspace info before disabling for confirmation
            # Fetch all workspaces to find the target
            all_workspaces = []
            skip = 0
            while True:
                workspaces, total_count, error = _fetch_workspaces_page(take=100, skip=skip)
                if error:
                    click.echo(f"✗ {error}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

                all_workspaces.extend(workspaces)

                if skip + 100 >= total_count:
                    break
                skip += 100

            # Find the workspace to get its details
            workspace_to_disable = None
            for ws in all_workspaces:
                if ws.get("id") == id:
                    workspace_to_disable = ws
                    break

            if not workspace_to_disable:
                click.echo(f"✗ Workspace with ID '{id}' not found", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            workspace_name = workspace_to_disable.get("name", id)

            # Check if workspace is already disabled
            if not workspace_to_disable.get("enabled", True):
                click.echo(f"✗ Workspace '{workspace_name}' is already disabled", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

            # Update the workspace to disable it
            update_url = f"{get_base_url()}/niuser/v1/workspaces/{id}"
            update_payload = {"name": workspace_name, "enabled": False}

            make_api_request("PUT", update_url, update_payload)

            format_success(
                f"Workspace '{workspace_name}' disabled successfully",
                {"id": id, "name": workspace_name, "enabled": False},
            )

        except Exception as exc:
            handle_api_error(exc)

    @workspace.command(name="get")
    @click.option(
        "--workspace",
        "-w",
        required=True,
        help="Workspace name or ID",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_workspace(workspace: str, format: str) -> None:
        """Show workspace details and contents."""
        try:
            # Get workspace info - fetch all pages until we find the workspace
            all_workspaces = []
            skip = 0
            while True:
                workspaces, total_count, error = _fetch_workspaces_page(take=100, skip=skip)
                if error:
                    click.echo(f"✗ {error}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

                all_workspaces.extend(workspaces)

                if skip + 100 >= total_count:
                    break
                skip += 100

            # Find the workspace by ID or name
            target_workspace = None
            target_workspace = next(
                (
                    ws
                    for ws in all_workspaces
                    if ws.get("id") == workspace or ws.get("name") == workspace
                ),
                None,
            )

            if not target_workspace:
                click.echo(f"✗ Workspace '{workspace}' not found", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            workspace_id = target_workspace.get("id")
            workspace_name = target_workspace.get("name")

            # Get workspace contents with error handling
            templates, templates_error = _get_workspace_templates(workspace_id)
            workflows, workflows_error = _get_workspace_workflows(workspace_id)
            notebooks, notebooks_error = _get_workspace_notebooks(workspace_id)

            # Prepare error information
            access_errors = {}
            if templates_error:
                access_errors["templates"] = templates_error
            if workflows_error:
                access_errors["workflows"] = workflows_error
            if notebooks_error:
                access_errors["notebooks"] = notebooks_error

            workspace_info = {
                "workspace": {
                    "id": workspace_id,
                    "name": workspace_name,
                    "enabled": target_workspace.get("enabled", True),
                    "default": target_workspace.get("default", False),
                },
                "contents": {
                    "templates": templates,
                    "workflows": workflows,
                    "notebooks": notebooks,
                },
                "summary": {
                    "total_templates": len(templates),
                    "total_workflows": len(workflows),
                    "total_notebooks": len(notebooks),
                },
            }

            # Add access errors to JSON output if any exist
            if access_errors:
                workspace_info["access_errors"] = access_errors

            if format == "json":
                click.echo(json.dumps(workspace_info, indent=2))
                return

            # Table format
            click.echo(f"Workspace Information: {workspace_name}")
            click.echo("=" * 50)
            click.echo(f"ID: {workspace_id}")
            click.echo(f"Name: {workspace_name}")
            click.echo(f"Enabled: {'✓' if target_workspace.get('enabled', True) else '✗'}")
            click.echo(f"Default: {'✓' if target_workspace.get('default', False) else '✗'}")

            # Templates section
            click.echo(f"\nTest Plan Templates ({len(templates)})")
            click.echo("-" * 30)
            if templates_error:
                click.echo(f"✗ {templates_error}")
            elif templates:
                click.echo("┌" + "─" * 42 + "┬" + "─" * 38 + "┐")
                click.echo(f"│ {'Name':<40} │ {'ID':<36} │")
                click.echo("├" + "─" * 42 + "┼" + "─" * 38 + "┤")
                for template in templates:
                    name = template.get("name", "")[:40]
                    template_id = template.get("id", "")[:36]
                    click.echo(f"│ {name:<40} │ {template_id:<36} │")
                click.echo("└" + "─" * 42 + "┴" + "─" * 38 + "┘")
            else:
                click.echo("No test plan templates found.")

            # Workflows section
            click.echo(f"\nWorkflows ({len(workflows)})")
            click.echo("-" * 30)
            if workflows_error:
                click.echo(f"✗ {workflows_error}")
            elif workflows:
                click.echo("┌" + "─" * 42 + "┬" + "─" * 38 + "┐")
                click.echo(f"│ {'Name':<40} │ {'ID':<36} │")
                click.echo("├" + "─" * 42 + "┼" + "─" * 38 + "┤")
                for workflow in workflows:
                    name = workflow.get("name", "")[:40]
                    workflow_id = workflow.get("id", "")[:36]
                    click.echo(f"│ {name:<40} │ {workflow_id:<36} │")
                click.echo("└" + "─" * 42 + "┴" + "─" * 38 + "┘")
            else:
                click.echo("No workflows found.")

            # Notebooks section
            click.echo(f"\nNotebooks ({len(notebooks)})")
            click.echo("-" * 30)
            if notebooks_error:
                click.echo(f"✗ {notebooks_error}")
            elif notebooks:
                click.echo("┌" + "─" * 42 + "┬" + "─" * 38 + "┐")
                click.echo(f"│ {'Name':<40} │ {'ID':<36} │")
                click.echo("├" + "─" * 42 + "┼" + "─" * 38 + "┤")
                for notebook in notebooks:
                    name = notebook.get("name", "")[:40]
                    notebook_id = notebook.get("id", "")[:36]
                    click.echo(f"│ {name:<40} │ {notebook_id:<36} │")
                click.echo("└" + "─" * 42 + "┴" + "─" * 38 + "┘")
            else:
                click.echo("No notebooks found.")

        except Exception as exc:
            handle_api_error(exc)


def _get_workspace_map() -> Dict[str, str]:
    """Get a mapping of workspace IDs to names."""
    try:
        url = f"{get_base_url()}/niuser/v1/workspaces"
        resp = make_api_request("GET", url)
        data = resp.json()
        workspaces = data.get("workspaces", [])
        return {ws.get("id"): ws.get("name") for ws in workspaces if ws.get("id")}
    except Exception:
        return {}


def _get_workspace_templates(workspace_id: str) -> Tuple[list, Optional[str]]:
    """Get test plan templates in a workspace using continuation token pagination.

    Returns:
        Tuple of (templates_list, error_message). If error_message is not None,
        it indicates an access or permission issue.
    """
    try:
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        all_templates = []
        continuation_token = None

        while True:
            payload = {
                "take": 100,  # Use smaller page size for efficient pagination
                "projection": ["ID", "NAME"],
                "filter": f'workspace == "{workspace_id}"',
            }

            if continuation_token:
                payload["continuationToken"] = continuation_token

            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            templates = data.get("testPlanTemplates", [])
            all_templates.extend(templates)

            # Check if there are more pages
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break

        return all_templates, None
    except Exception as exc:
        error_msg = str(exc).lower()
        if "401" in error_msg or "unauthorized" in error_msg or "permission" in error_msg:
            return [], "Access denied (insufficient permissions)"
        elif "403" in error_msg or "forbidden" in error_msg:
            return [], "Access forbidden"
        elif "404" in error_msg or "not found" in error_msg:
            return [], "Service not available"
        else:
            return [], f"Unable to retrieve templates: {str(exc)}"


def _get_workspace_workflows(workspace_id: str) -> Tuple[list, Optional[str]]:
    """Get workflows in a workspace using continuation token pagination.

    Returns:
        Tuple of (workflows_list, error_message). If error_message is not None,
        it indicates an access or permission issue.
    """
    try:
        url = f"{get_base_url()}/niworkorder/v1/query-workflows?ff-userdefinedworkflowsfortestplaninstances=true"
        all_workflows = []
        continuation_token = None

        while True:
            payload = {
                "take": 100,  # Use smaller page size for efficient pagination
                "projection": ["ID", "NAME", "WORKSPACE"],
            }

            if continuation_token:
                payload["continuationToken"] = continuation_token

            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()

            workflows = data.get("workflows", [])
            all_workflows.extend(workflows)

            # Check if there are more pages
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break

        # Filter workflows by workspace since the API doesn't support workspace filtering
        workspace_workflows = [wf for wf in all_workflows if wf.get("workspace") == workspace_id]
        return workspace_workflows, None
    except Exception as exc:
        error_msg = str(exc).lower()
        if "401" in error_msg or "unauthorized" in error_msg or "permission" in error_msg:
            return [], "Access denied (insufficient permissions)"
        elif "403" in error_msg or "forbidden" in error_msg:
            return [], "Access forbidden"
        elif "404" in error_msg or "not found" in error_msg:
            return [], "Service not available"
        else:
            return [], f"Unable to retrieve workflows: {str(exc)}"


def _get_workspace_notebooks(workspace_id: str) -> Tuple[list, Optional[str]]:
    """Get notebooks in a workspace.

    Returns:
        Tuple of (notebooks_list, error_message). If error_message is not None,
        it indicates an access or permission issue.
    """
    try:
        url = f"{get_base_url()}/ninotebook/v1/notebook/query"
        payload = {"take": 1000, "filter": f'workspace = "{workspace_id}"'}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        notebooks = data.get("notebooks", [])
        # Convert to consistent format
        return [{"id": nb.get("id"), "name": nb.get("name")} for nb in notebooks], None
    except Exception as exc:
        error_msg = str(exc).lower()
        if "401" in error_msg or "unauthorized" in error_msg or "permission" in error_msg:
            return [], "Access denied (insufficient permissions)"
        elif "403" in error_msg or "forbidden" in error_msg:
            return [], "Access forbidden"
        elif "404" in error_msg or "not found" in error_msg:
            return [], "Service not available"
        else:
            return [], f"Unable to retrieve notebooks: {str(exc)}"

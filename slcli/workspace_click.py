"""CLI commands for managing SystemLink workspaces."""

import json
import sys
from typing import Any, Dict, Optional, Tuple

import click

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)


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
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of workspaces to return",
    )
    def list_workspaces(
        format: str = "table",
        include_disabled: bool = False,
        workspace: Optional[str] = None,
        take: int = 25,
    ) -> None:
        """List workspaces."""
        format_output = validate_output_format(format)

        url = f"{get_base_url()}/niuser/v1/workspaces"

        try:
            # Build URL with query parameters
            query_params = []

            # For JSON format, respect the take parameter exactly
            # For table format, use take if specified, otherwise fetch larger dataset
            # for local pagination
            if format_output.lower() == "json":
                api_take = take
            else:
                # For table format, use take if specified, otherwise fetch larger amount
                # for pagination
                api_take = (
                    take if take != 25 else 1000
                )  # 25 is the default, so fetch more for pagination

            query_params.append(f"take={api_take}")
            if workspace:
                query_params.append(f"name={workspace}")

            if query_params:
                url += "?" + "&".join(query_params)

            resp = make_api_request("GET", url, payload=None)

            # Filter workspaces by enabled status if needed
            if not include_disabled:
                data = resp.json()
                workspaces = data.get("workspaces", []) if isinstance(data, dict) else []
                filtered_workspaces = [ws for ws in workspaces if ws.get("enabled", True)]

                # Create a new response with filtered data
                filtered_resp: Any = FilteredResponse(
                    {"workspaces": filtered_workspaces}
                )  # Type annotation to avoid type checker issues
                resp = filtered_resp

            def workspace_formatter(workspace: dict) -> list:
                enabled = "✓" if workspace.get("enabled", True) else "✗"
                default = "✓" if workspace.get("default", False) else ""
                return [workspace.get("name", "Unknown"), workspace.get("id", ""), enabled, default]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="workspaces",
                item_name="workspace",
                format_output=format_output,
                formatter_func=workspace_formatter,
                headers=["Name", "ID", "Enabled", "Default"],
                column_widths=[30, 36, 8, 8],
                empty_message="No workspaces found.",
                enable_pagination=True,
                page_size=take,
            )

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
            workspace_info_url = f"{get_base_url()}/niuser/v1/workspaces?take=1000"
            resp = make_api_request("GET", workspace_info_url)
            data = resp.json()
            workspaces = data.get("workspaces", [])

            # Find the workspace to get its details
            workspace_to_disable = None
            for ws in workspaces:
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
            # Get workspace info
            workspace_info_url = f"{get_base_url()}/niuser/v1/workspaces?take=1000"
            resp = make_api_request("GET", workspace_info_url)
            data = resp.json()
            workspaces = data.get("workspaces", [])

            # Find the workspace by ID or name
            target_workspace = None
            target_workspace = next(
                (
                    ws
                    for ws in workspaces
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

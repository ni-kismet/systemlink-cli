"""CLI commands for managing SystemLink workspaces."""

import json
import sys
from typing import Optional

import click

from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)


def register_workspace_commands(cli):
    """Register the 'workspace' command group and its subcommands."""

    @cli.group()
    def workspace():
        """Manage workspaces (list, disable, info)."""
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
        "--name",
        "-n",
        help="Filter workspaces by name",
    )
    def list_workspaces(
        format: str = "table", include_disabled: bool = False, name: Optional[str] = None
    ):
        """List workspaces."""
        url = f"{get_base_url()}/niuser/v1/workspaces"

        try:
            # Build URL with query parameters
            query_params = []
            query_params.append("take=1000")
            if name:
                query_params.append(f"name={name}")

            if query_params:
                url += "?" + "&".join(query_params)

            resp = make_api_request("GET", url, payload=None)
            data = resp.json()
            workspaces = data.get("workspaces", []) if isinstance(data, dict) else []

            # Filter workspaces by enabled status if needed
            if not include_disabled:
                workspaces = [ws for ws in workspaces if ws.get("enabled", True)]

            if format == "json":
                click.echo(json.dumps(workspaces, indent=2))
                sys.exit(ExitCodes.SUCCESS)

            # Table format
            if not workspaces:
                click.echo("No workspaces found.")
                sys.exit(ExitCodes.SUCCESS)

            # Display table
            click.echo("┌" + "─" * 38 + "┬" + "─" * 32 + "┬" + "─" * 10 + "┬" + "─" * 10 + "┐")
            click.echo(f"│ {'ID':<36} │ {'Name':<30} │ {'Enabled':<8} │ {'Default':<8} │")
            click.echo("├" + "─" * 38 + "┼" + "─" * 32 + "┼" + "─" * 10 + "┼" + "─" * 10 + "┤")

            for workspace in workspaces:
                ws_id = workspace.get("id", "")[:36]
                ws_name = workspace.get("name", "")[:30]
                enabled = "✓" if workspace.get("enabled", True) else "✗"
                default = "✓" if workspace.get("default", False) else ""

                click.echo(f"│ {ws_id:<36} │ {ws_name:<30} │ {enabled:<8} │ {default:<8} │")

            click.echo("└" + "─" * 38 + "┴" + "─" * 32 + "┴" + "─" * 10 + "┴" + "─" * 10 + "┘")
            click.echo(f"\nTotal: {len(workspaces)} workspace(s)")

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
    def disable_workspace(id: str):
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

    @workspace.command(name="info")
    @click.option(
        "--id",
        "-i",
        help="ID of the workspace to get info for",
    )
    @click.option(
        "--name",
        "-n",
        help="Name of the workspace to get info for",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def info_workspace(id: Optional[str] = None, name: Optional[str] = None, format: str = "table"):
        """Get detailed information about a workspace and its contents."""
        if not id and not name:
            click.echo("✗ Must provide either --id or --name", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            # Get workspace info
            workspace_info_url = f"{get_base_url()}/niuser/v1/workspaces?take=1000"
            resp = make_api_request("GET", workspace_info_url)
            data = resp.json()
            workspaces = data.get("workspaces", [])

            # Find the workspace
            target_workspace = None
            if id:
                target_workspace = next((ws for ws in workspaces if ws.get("id") == id), None)
            elif name:
                target_workspace = next((ws for ws in workspaces if ws.get("name") == name), None)

            if not target_workspace:
                identifier = id if id else name
                click.echo(f"✗ Workspace '{identifier}' not found", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            workspace_id = target_workspace.get("id")
            workspace_name = target_workspace.get("name")

            # Get workspace contents
            templates = _get_workspace_templates(workspace_id)
            workflows = _get_workspace_workflows(workspace_id)
            notebooks = _get_workspace_notebooks(workspace_id)

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
            if templates:
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
            if workflows:
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
            if notebooks:
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


def _get_workspace_map():
    """Get a mapping of workspace IDs to names."""
    try:
        url = f"{get_base_url()}/niuser/v1/workspaces"
        resp = make_api_request("GET", url)
        data = resp.json()
        workspaces = data.get("workspaces", [])
        return {ws.get("id"): ws.get("name") for ws in workspaces if ws.get("id")}
    except Exception:
        return {}


def _get_workspace_templates(workspace_id: str) -> list:
    """Get test plan templates in a workspace."""
    try:
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        payload = {
            "take": 1000,
            "projection": ["ID", "NAME"],
            "filter": f'workspace == "{workspace_id}"',
        }
        resp = make_api_request("POST", url, payload)
        data = resp.json()
        return data.get("testPlanTemplates", [])
    except Exception:
        return []


def _get_workspace_workflows(workspace_id: str) -> list:
    """Get workflows in a workspace."""
    try:
        url = f"{get_base_url()}/niworkorder/v1/query-workflows?ff-userdefinedworkflowsfortestplaninstances=true"
        payload = {
            "take": 1000,
            "projection": ["ID", "NAME", "WORKSPACE"],
        }
        resp = make_api_request("POST", url, payload)
        data = resp.json()
        workflows = data.get("workflows", [])
        # Filter workflows by workspace since the API doesn't support filter parameter
        workspace_workflows = [wf for wf in workflows if wf.get("workspace") == workspace_id]
        return workspace_workflows
    except Exception:
        return []


def _get_workspace_notebooks(workspace_id: str) -> list:
    """Get notebooks in a workspace."""
    try:
        url = f"{get_base_url()}/ninotebook/v1/notebook/query"
        payload = {"take": 1000, "filter": f'workspace = "{workspace_id}"'}
        resp = make_api_request("POST", url, payload)
        data = resp.json()
        notebooks = data.get("notebooks", [])  # Changed from "notebook" to "notebooks"
        # Convert to consistent format
        return [{"id": nb.get("id"), "name": nb.get("name")} for nb in notebooks]
    except Exception:
        # Notebook API might not be available or endpoint might be different
        # Return empty list to allow the command to continue
        return []

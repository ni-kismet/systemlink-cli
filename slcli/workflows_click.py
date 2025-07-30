"""CLI commands for managing SystemLink workflows."""

import json
import os
from typing import Optional

import click
import requests

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import (
    display_api_errors,
    extract_error_type,
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


def _query_all_workflows(
    workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None
):
    """Query all workflows using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all workflows, optionally filtered by workspace
    """
    url = f"{get_base_url()}/niworkorder/v1/query-workflows?ff-userdefinedworkflowsfortestplaninstances=true"
    all_workflows = []
    continuation_token = None

    while True:
        # Build payload for the request
        payload = {
            "take": 100,  # Use smaller page size for efficient pagination
        }

        # Add workspace filter if specified
        if workspace_filter:
            payload["filter"] = f'WORKSPACE == "{workspace_filter}"'

        # Add continuation token if we have one
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        # Extract workflows from this page
        workflows = data.get("workflows", [])
        all_workflows.extend(workflows)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_workflows


def register_workflows_commands(cli):
    """Register the 'workflow' command group and its subcommands."""

    @cli.group()
    def workflow():
        """Manage workflows."""
        pass

    @workflow.command(name="init")
    @click.option(
        "--name",
        "-n",
        help="Workflow name (will prompt if not provided)",
    )
    @click.option(
        "--description",
        "-d",
        help="Workflow description (will prompt if not provided)",
    )
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (default: 'Default')",
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (default: <name>-workflow.json)",
    )
    def init_workflow(name, description, workspace, output):
        """Initialize a new workflow JSON file.

        Creates a workflow JSON file with the required schema structure.
        Name and description are recommended fields. Workspace is required
        and defaults to 'Default' if not specified.
        """
        # Prompt for required fields if not provided
        if not name:
            name = click.prompt("Workflow name", type=str)
        if not description:
            description = click.prompt("Workflow description", type=str, default="")

        # Generate output filename if not provided
        if not output:
            safe_name = sanitize_filename(name, "workflow")
            output = f"{safe_name}-workflow.json"

        # Resolve workspace name to ID
        try:
            workspace_id = get_workspace_id_with_fallback(workspace)
        except Exception as exc:
            click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
            raise click.ClickException(f"Error resolving workspace '{workspace}': {exc}")

        # Create workflow structure based on the correct API schema
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
            ],
            "states": [
                {
                    "name": "NEW",
                    "dashboardAvailable": False,
                    "defaultSubstate": "NEW",
                    "substates": [{"name": "NEW", "displayText": "New", "availableActions": []}],
                },
                {
                    "name": "DEFINED",
                    "dashboardAvailable": False,
                    "defaultSubstate": "DEFINED",
                    "substates": [
                        {"name": "DEFINED", "displayText": "Defined", "availableActions": []}
                    ],
                },
                {
                    "name": "REVIEWED",
                    "dashboardAvailable": False,
                    "defaultSubstate": "REVIEWED",
                    "substates": [
                        {"name": "REVIEWED", "displayText": "Reviewed", "availableActions": []}
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
                                }
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
                                    "action": "START",
                                    "nextState": "IN_PROGRESS",
                                    "nextSubstate": "IN_PROGRESS",
                                    "showInUI": True,
                                },
                                {
                                    "action": "COMPLETE",
                                    "nextState": "PENDING_APPROVAL",
                                    "nextSubstate": "PENDING_APPROVAL",
                                    "showInUI": True,
                                },
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
                            "availableActions": [],
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
                        {"name": "CANCELED", "displayText": "Canceled", "availableActions": []}
                    ],
                },
            ],
        }

        try:
            # Check if file already exists
            if os.path.exists(output):
                if not click.confirm(f"File {output} already exists. Overwrite?"):
                    click.echo("Workflow initialization cancelled.")
                    return

            # Save the workflow file
            with open(output, "w", encoding="utf-8") as f:
                json.dump(workflow_data, f, indent=2, ensure_ascii=False)

            click.echo(f"✓ Workflow initialized: {output}")
            click.echo("Edit the file to customize your workflow:")
            click.echo("  - name and description are recommended")
            click.echo("  - Define states, substates, and actions as needed")
            click.echo(f"  - Workspace is set to: {workspace} (ID: {workspace_id})")
            click.echo("  - Use 'slcli workflows import' to upload the workflow when ready")

        except Exception as exc:
            click.echo(f"✗ Error creating workflow file: {exc}", err=True)
            raise click.ClickException(f"Error creating workflow file: {exc}")

    @workflow.command(name="list")
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
        help="Maximum number of workflows to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--status",
        "-s",
        help="Filter by workflow status",
    )
    def list_workflows(
        format: str = "table",
        workspace: Optional[str] = None,
        take: int = 25,
        status: Optional[str] = None,
    ):
        """List available workflows."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()

            # Resolve workspace filter to ID if specified
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Use continuation token pagination to get all workflows
            all_workflows = _query_all_workflows(workspace_id, workspace_map)

            # Create a mock response with all data
            resp = FilteredResponse({"workflows": all_workflows})

            # Use universal response handler with workflow formatter
            def workflow_formatter(workflow: dict) -> list:
                ws_guid = workflow.get("workspace", "")
                ws_name = get_workspace_display_name(ws_guid, workspace_map)
                return [
                    workflow.get("name", "Unknown"),
                    ws_name,
                    workflow.get("id", ""),
                    workflow.get("description", "N/A")[:30],  # Truncate description
                ]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="workflows",
                item_name="workflow",
                format_output=format_output,
                formatter_func=workflow_formatter,
                headers=["Name", "Workspace", "ID", "Description"],
                column_widths=[40, 30, 36, 32],
                empty_message="No workflows found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @workflow.command(name="export")
    @click.option(
        "--id",
        "-i",
        "workflow_id",
        required=True,
        help="Workflow ID to export",
    )
    @click.option("--output", "-o", help="Output JSON file (default: <workflow-name>.json)")
    def export_workflow(workflow_id, output):
        """Download/export a workflow as a local JSON file."""
        url = f"{get_base_url()}/niworkorder/v1/workflows/{workflow_id}?ff-userdefinedworkflowsfortestplaninstances=true"
        try:
            resp = make_api_request("GET", url)
            data = resp.json()

            if not data:
                click.echo(f"✗ Workflow with ID {workflow_id} not found.", err=True)
                raise click.ClickException(f"Workflow with ID {workflow_id} not found.")

            # Generate output filename if not provided
            if not output:
                workflow_name = data.get("name", f"workflow-{workflow_id}")
                safe_name = sanitize_filename(workflow_name, f"workflow-{workflow_id}")
                output = f"{safe_name}.json"

            save_json_file(data, output)
            click.echo(f"✓ Workflow exported to {output}")
        except Exception as exc:
            if "not found" not in str(exc).lower():
                handle_api_error(exc)
            else:
                click.echo(f"✗ Error: {exc}", err=True)
                raise click.ClickException(str(exc))

    @workflow.command(name="import")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Override workspace name or ID (uses value from file if not specified)",
    )
    def import_workflow(input_file, workspace):
        """Upload/import a workflow from a local JSON file.

        Workspace can be specified via --workspace flag or included in the JSON file.
        Command line workspace takes precedence over file contents.
        """
        url = f"{get_base_url()}/niworkorder/v1/workflows?ff-userdefinedworkflowsfortestplaninstances=true"
        allowed_fields = {
            "name",
            "description",
            "actions",
            "states",
            "workspace",
        }
        try:
            data = load_json_file(input_file)

            # Filter allowed fields
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

            # Handle workspace resolution
            if workspace:
                # Override workspace from command line
                try:
                    workspace_id = get_workspace_id_with_fallback(workspace)
                    filtered_data["workspace"] = workspace_id
                except Exception as exc:
                    click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
                    raise click.ClickException(f"Error resolving workspace '{workspace}': {exc}")
            elif "workspace" not in filtered_data or not filtered_data["workspace"]:
                # No workspace specified and none in file - require one
                click.echo(
                    "✗ Workspace is required. Specify --workspace or include 'workspace' in the JSON file.",
                    err=True,
                )
                raise click.ClickException(
                    "Workspace is required. Specify --workspace or include 'workspace' in the JSON file."
                )
            elif filtered_data["workspace"] and not filtered_data["workspace"].startswith("//"):
                # Workspace in file - validate/resolve it if it looks like a name
                try:
                    workspace_id = get_workspace_id_with_fallback(filtered_data["workspace"])
                    filtered_data["workspace"] = workspace_id
                except Exception as exc:
                    click.echo(
                        f"✗ Error resolving workspace from file '{filtered_data['workspace']}': {exc}",
                        err=True,
                    )
                    raise click.ClickException(
                        f"Error resolving workspace from file '{filtered_data['workspace']}': {exc}"
                    )

            try:
                resp = make_api_request("POST", url, filtered_data, handle_errors=False)
                # Check for successful creation
                if resp.status_code == 201:
                    response_data = resp.json() if resp.text.strip() else {}
                    workflow_id = response_data.get("id", "")
                    if workflow_id:
                        click.echo(f"✓ Workflow imported successfully with ID: {workflow_id}")
                    else:
                        click.echo("✓ Workflow imported successfully.")
                else:
                    # Handle error responses - parse detailed error structure
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_error_response(response_data, "Workflow import failed")
            except requests.exceptions.HTTPError as http_exc:
                # Extract response data from the HTTP error for detailed parsing
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_error_response(response_data, "Workflow import failed")
                    except Exception:
                        # Fallback to generic error handling if JSON parsing fails
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)

        except Exception as exc:
            handle_api_error(exc)

    @workflow.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "workflow_id",
        required=True,
        help="Workflow ID to delete",
    )
    def delete_workflow(workflow_id):
        """Delete a workflow by ID."""
        url = f"{get_base_url()}/niworkorder/v1/delete-workflows?ff-userdefinedworkflowsfortestplaninstances=true"
        payload = {"ids": [workflow_id]}
        try:
            try:
                resp = make_api_request("POST", url, payload, handle_errors=False)
                if resp.status_code in (200, 204):
                    # Parse the response to check for partial failures
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_delete_response(response_data, workflow_id)
                else:
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_delete_response(response_data, workflow_id)
            except requests.exceptions.HTTPError as http_exc:
                # Extract response data from the HTTP error for detailed parsing
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_delete_response(response_data, workflow_id)
                    except Exception:
                        # Fallback to generic error handling if JSON parsing fails
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)
        except Exception as exc:
            handle_api_error(exc)

    @workflow.command(name="update")
    @click.option(
        "--id",
        "-i",
        "workflow_id",
        required=True,
        help="Workflow ID to update",
    )
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with updated workflow data",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Override workspace name or ID (uses value from file if not specified)",
    )
    def update_workflow(workflow_id, input_file, workspace):
        """Update a workflow from a local JSON file.

        Workspace can be specified via --workspace flag or included in the JSON file.
        Command line workspace takes precedence over file contents.
        """
        url = f"{get_base_url()}/niworkorder/v1/workflows/{workflow_id}?ff-userdefinedworkflowsfortestplaninstances=true"
        allowed_fields = {
            "name",
            "description",
            "actions",
            "states",
            "workspace",
        }
        try:
            data = load_json_file(input_file)

            # Filter allowed fields
            filtered_data = {k: v for k, v in data.items() if k in allowed_fields}

            # Handle workspace resolution
            if workspace:
                # Override workspace from command line
                try:
                    workspace_id = get_workspace_id_with_fallback(workspace)
                    filtered_data["workspace"] = workspace_id
                except Exception as exc:
                    click.echo(f"✗ Error resolving workspace '{workspace}': {exc}", err=True)
                    raise click.ClickException(f"Error resolving workspace '{workspace}': {exc}")
            elif (
                "workspace" in filtered_data
                and filtered_data["workspace"]
                and not filtered_data["workspace"].startswith("//")
            ):
                # Workspace in file - validate/resolve it if it looks like a name
                try:
                    workspace_id = get_workspace_id_with_fallback(filtered_data["workspace"])
                    filtered_data["workspace"] = workspace_id
                except Exception as exc:
                    click.echo(
                        f"✗ Error resolving workspace from file '{filtered_data['workspace']}': {exc}",
                        err=True,
                    )
                    raise click.ClickException(
                        f"Error resolving workspace from file '{filtered_data['workspace']}': {exc}"
                    )

            try:
                resp = make_api_request("PUT", url, filtered_data, handle_errors=False)
                # Check for successful update
                if resp.status_code == 200:
                    click.echo(f"✓ Workflow {workflow_id} updated successfully.")
                else:
                    # Handle error responses
                    response_data = resp.json() if resp.text.strip() else {}
                    _handle_workflow_error_response(response_data, "Workflow update failed")
            except requests.exceptions.HTTPError as http_exc:
                # Extract response data from the HTTP error for detailed parsing
                if hasattr(http_exc, "response") and http_exc.response is not None:
                    try:
                        response_data = (
                            http_exc.response.json() if http_exc.response.text.strip() else {}
                        )
                        _handle_workflow_error_response(response_data, "Workflow update failed")
                    except Exception:
                        # Fallback to generic error handling if JSON parsing fails
                        handle_api_error(http_exc)
                else:
                    handle_api_error(http_exc)

        except Exception as exc:
            handle_api_error(exc)


def _handle_workflow_error_response(response_data, operation_name):
    """Parse and display detailed workflow error responses.

    Args:
        response_data: The JSON response data containing error information
        operation_name: The name of the operation that failed (e.g., "Workflow import failed")
    """
    display_api_errors(operation_name, response_data, detailed=True)


def _handle_workflow_delete_response(response_data, workflow_id):
    """Parse and display workflow delete response, handling both success and failures.

    Args:
        response_data: The JSON response data from delete operation
        workflow_id: The ID of the workflow that was requested to be deleted
    """
    import sys

    # Handle successful deletion response: empty JSON {} with 204 status
    if not response_data or response_data == {}:
        click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
        return

    # Handle successful deletion response format: {"ids": ["1023"]}
    if "ids" in response_data:
        deleted_ids = response_data.get("ids", [])
        if workflow_id in deleted_ids:
            click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
            return
        else:
            # Workflow ID not in the successful deletion list - unexpected
            click.echo(f"✗ Unexpected response for workflow {workflow_id}:", err=True)
            click.echo(f"  Successfully deleted: {', '.join(deleted_ids)}", err=True)
            sys.exit(1)
        deleted_ids = response_data.get("ids", [])
        if workflow_id in deleted_ids:
            click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
            return
        else:
            # Workflow ID not in the successful deletion list - unexpected
            click.echo(f"✗ Unexpected response for workflow {workflow_id}:", err=True)
            click.echo(f"  Successfully deleted: {', '.join(deleted_ids)}", err=True)
            sys.exit(1)

    # Handle error response format with deletedWorkflowIds and failedWorkflowIds
    deleted_ids = response_data.get("deletedWorkflowIds", [])
    failed_ids = response_data.get("failedWorkflowIds", [])

    # Check if our specific workflow was deleted successfully
    if workflow_id in deleted_ids:
        click.echo(f"✓ Workflow {workflow_id} deleted successfully.")
        return

    # Check if our specific workflow failed to delete
    if workflow_id in failed_ids:
        click.echo(f"✗ Failed to delete workflow {workflow_id}:", err=True)

        # Parse error details for failed workflows
        error = response_data.get("error", {})
        if error:
            main_message = error.get("message", "Unknown error")
            click.echo(f"  {main_message}", err=True)

            # Parse inner errors for detailed failure reasons
            inner_errors = error.get("innerErrors", [])
            for inner_error in inner_errors:
                resource_id = inner_error.get("resourceId", "")
                if resource_id == workflow_id:
                    error_message = inner_error.get("message", "Unknown error")
                    error_name = inner_error.get("name", "")

                    # Extract more readable error type
                    if error_name:
                        error_type = extract_error_type(error_name)
                        click.echo(f"    - {error_type}: {error_message}", err=True)
                    else:
                        click.echo(f"    - {error_message}", err=True)

        sys.exit(1)

    # If workflow ID is not in either list, something unexpected happened
    click.echo(f"✗ Unexpected response for workflow {workflow_id}:", err=True)
    if deleted_ids:
        click.echo(f"  Successfully deleted: {', '.join(deleted_ids)}", err=True)
    if failed_ids:
        click.echo(f"  Failed to delete: {', '.join(failed_ids)}", err=True)

    # If there were any failures or unexpected responses, exit with error code
    if failed_ids or not response_data:
        sys.exit(1)

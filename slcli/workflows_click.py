"""CLI commands for managing SystemLink workflows."""

import json
import os
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Dict, Optional, Union

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
        payload: Dict[str, Union[int, str]] = {
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

        # Create workflow structure matching the workflow-template.json reference
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
                        "notebookId": "df2140b3-f184-4327-af07-6048d073449d",
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
                        {
                            "name": "REVIEWED",
                            "displayText": "Reviewed",
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

    @workflow.command(name="preview")
    @click.option(
        "--id",
        "-i",
        "workflow_id",
        help="Workflow ID to preview",
    )
    @click.option(
        "--file",
        "-f",
        "input_file",
        help="Local JSON file to preview",
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (default: open in browser)",
    )
    @click.option(
        "--format",
        type=click.Choice(["html", "mmd", "svg"]),
        default="html",
        show_default=True,
        help="Output format",
    )
    def preview_workflow(workflow_id, input_file, output, format):
        """Generate a Mermaid diagram preview of workflow states and transitions."""
        # Validate that exactly one of --id or --file is provided
        if not workflow_id and not input_file:
            click.echo("✗ Error: Must specify either --id or --file", err=True)
            sys.exit(1)
        if workflow_id and input_file:
            click.echo("✗ Error: Cannot specify both --id and --file", err=True)
            sys.exit(1)

        try:
            # Load workflow data
            if workflow_id:
                # Fetch workflow by ID
                url = f"{get_base_url()}/niworkorder/v1/workflows/{workflow_id}?ff-userdefinedworkflowsfortestplaninstances=true"
                resp = make_api_request("GET", url)
                workflow_data = resp.json()

                if not workflow_data:
                    click.echo(f"✗ Workflow with ID {workflow_id} not found.", err=True)
                    sys.exit(1)
            else:
                # Load from local file
                workflow_data = load_json_file(input_file)

            # Generate Mermaid diagram
            mermaid_code = _generate_mermaid_diagram(workflow_data)

            if format == "mmd":
                # Save as .mmd file
                if not output:
                    output = f"workflow-{workflow_data.get('name', 'preview')}.mmd"
                with open(output, "w", encoding="utf-8") as f:
                    f.write(mermaid_code)
                click.echo(f"✓ Mermaid diagram saved to {output}")
            elif format == "svg":
                # Note: SVG generation would require Mermaid CLI to be installed
                click.echo(
                    "✗ SVG format requires Mermaid CLI. Use 'npm install -g @mermaid-js/mermaid-cli' first.",
                    err=True,
                )
                sys.exit(1)
            else:
                # Generate HTML and open in browser
                html_content = _generate_html_with_mermaid(workflow_data, mermaid_code)

                if output:
                    # Save to specified file
                    with open(output, "w", encoding="utf-8") as f:
                        f.write(html_content)
                    click.echo(f"✓ HTML preview saved to {output}")
                else:
                    # Create temporary file and open in browser
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".html", delete=False, encoding="utf-8"
                    ) as f:
                        f.write(html_content)
                        temp_file = f.name

                    # Open in default browser
                    webbrowser.open(f"file://{Path(temp_file).absolute()}")
                    click.echo(f"✓ Opening workflow preview in browser...")

        except Exception as exc:
            handle_api_error(exc)


def _sanitize_mermaid_label(label: str) -> str:
    """Sanitize label text for Mermaid diagram compatibility."""
    if not label:
        return label

    # Replace problematic characters for Mermaid syntax
    sanitized = label.replace("[", "(")
    sanitized = sanitized.replace("]", ")")
    sanitized = sanitized.replace("🔗", "")
    # Keep 📓 notebook emoji now that we add a legend; it's safe in labels
    sanitized = sanitized.replace("/", "-")
    sanitized = sanitized.replace("\\", "-")
    sanitized = sanitized.replace('"', "'")
    sanitized = sanitized.replace("`", "'")
    sanitized = sanitized.replace(":", " ")
    sanitized = sanitized.replace(";", ",")
    sanitized = sanitized.replace("|", " ")
    sanitized = sanitized.replace("&", "and")

    # Remove any remaining problematic characters and clean up whitespace
    sanitized = " ".join(sanitized.split())  # Normalize whitespace

    return sanitized


def _generate_mermaid_diagram(workflow_data: Dict) -> str:
    """Generate Mermaid state diagram from workflow data."""
    states = workflow_data.get("states", [])
    actions = workflow_data.get("actions", [])

    # Emoji mapping for action types (kept simple & widely supported)
    type_emojis: Dict[str, str] = {
        "MANUAL": "🧑",
        "NOTEBOOK": "📓",
        "SCHEDULE": "📅",
        "JOB": "🛠️",
    }

    # Create action lookup for display text and type, handling potential whitespace issues
    action_lookup = {}
    for action in actions:
        action_name = action["name"]
        action_display = action.get("displayText", action_name)
        execution_action = action.get("executionAction", {})
        action_type = execution_action.get("type", "")

        # Collect additional action metadata
        privileges = action.get("privilegeSpecificity", [])
        icon_class = action.get("iconClass")
        notebook_id = execution_action.get("notebookId")

        # Create action info with all metadata
        action_info = {
            "display": action_display,
            "type": action_type,
            "privileges": privileges,
            "icon": icon_class,
            "notebook_id": notebook_id,
        }

        # Store both trimmed and untrimmed versions to handle inconsistencies
        action_lookup[action_name] = action_info
        action_lookup[action_name.strip()] = action_info

    lines = ["stateDiagram-v2", ""]

    # Add states and their substates
    for state in states:
        state_name = state["name"]
        substates = state.get("substates", [])

        if not substates:
            # Simple state with no substates
            lines.append(f"    {state_name}")
        else:
            # State with substates
            for substate in substates:
                substate_name = substate["name"]
                substate_display = substate.get("displayText")

                # Build metadata for the state
                metadata_parts = []

                # Add dashboard availability
                if state.get("dashboardAvailable"):
                    metadata_parts.append("Dashboard")

                # Add action count (visible + hidden)
                available_actions = substate.get("availableActions", [])
                visible_actions = len([a for a in available_actions if a.get("showInUI", True)])
                hidden_actions = len([a for a in available_actions if not a.get("showInUI", True)])
                total_actions = len(available_actions)

                if total_actions > 0:
                    if hidden_actions > 0:
                        metadata_parts.append(f"{visible_actions}+{hidden_actions} actions")
                    else:
                        metadata_parts.append(
                            f"{visible_actions} action{'s' if visible_actions != 1 else ''}"
                        )

                # Create display text
                if substate_display:
                    display_text = substate_display
                else:
                    # Use state name formatted nicely (convert SNAKE_CASE to Title Case)
                    display_text = state_name.replace("_", " ").title()

                # Add metadata if any (restore multiline formatting with explicit \n sequences)
                if metadata_parts:
                    full_display = f"{display_text}\\n({', '.join(metadata_parts)})"
                else:
                    full_display = display_text

                # Add substate definition (restore multiline variant)
                if substate_name == state_name:
                    # Default substate uses the state name
                    lines.append(f"    {state_name} : {full_display}")
                else:
                    # Named substate with parent state on first line
                    lines.append(
                        f"    {state_name}_{substate_name} : {state_name}\\n{full_display}"
                    )

                # Add transitions from this substate
                available_actions = substate.get("availableActions", [])
                for action in available_actions:
                    action_name = action.get("action", "")
                    next_state = action.get("nextState", "")
                    next_substate = action.get("nextSubstate", "")
                    show_in_ui = action.get("showInUI", True)

                    if next_state:
                        # Handle potential whitespace issues in action names
                        action_info = action_lookup.get(
                            action_name, action_lookup.get(action_name.strip(), {})
                        )

                        if isinstance(action_info, dict):
                            action_display = action_info.get("display", action_name)
                            action_type = action_info.get("type", "")
                            privileges = action_info.get("privileges", [])
                            icon = action_info.get("icon")
                            notebook_id = action_info.get("notebook_id")

                            # Build enhanced action label with multiline formatting
                            # Collect label segments; each becomes a separate Mermaid line
                            emoji = type_emojis.get(action_type, "")
                            label_segments: list[str] = (
                                [emoji, action_display] if emoji else [action_display]
                            )

                            # Add action type as separate line
                            if action_type:
                                label_segments.append(f"({action_type})")

                            # Add privileges if any (keep grouped)
                            if privileges:
                                priv_str = ", ".join(privileges)
                                label_segments.append(f"({priv_str})")

                            # Add notebook info for NOTEBOOK actions
                            if action_type == "NOTEBOOK" and notebook_id:
                                short_id = notebook_id[:8] + "..."
                                label_segments.append(f"NB {short_id}")

                            # Add icon indicator
                            if icon:
                                # Use lightning emoji to indicate icon class succinctly
                                label_segments.append(f"⚡️ {icon}")

                            # Sanitize each segment; join using explicit \n escapes so Mermaid
                            # renders them as multi-line label content.
                            sanitized_segments = [
                                _sanitize_mermaid_label(seg) for seg in label_segments if seg
                            ]
                            full_action_label = "\\n".join(sanitized_segments)
                        else:
                            # Fallback for backwards compatibility
                            full_action_label = action_info if action_info else action_name

                        # Determine source and target node names
                        source_node = (
                            state_name
                            if substate_name == state_name
                            else f"{state_name}_{substate_name}"
                        )

                        if next_substate and next_substate == next_state:
                            target_node = next_state
                        elif next_substate:
                            target_node = f"{next_state}_{next_substate}"
                        else:
                            target_node = next_state

                        # Add transition (use only supported arrow syntax for stateDiagram)
                        if show_in_ui:
                            lines.append(
                                f"    {source_node} --> {target_node} : {full_action_label}"
                            )
                        else:
                            # Use same arrow; append hidden marker in lowercase for clarity
                            # Append hidden marker as additional multiline segment
                            hidden_label = f"{full_action_label}\\nhidden"
                            lines.append(f"    {source_node} --> {target_node} : {hidden_label}")

    # Legend now omitted from Mermaid source (added only in HTML export)
    lines.append("")
    return "\n".join(lines)


def _generate_html_with_mermaid(workflow_data: Dict, mermaid_code: str) -> str:
    """Generate HTML page with embedded Mermaid diagram."""
    workflow_name = workflow_data.get("name", "Workflow")
    workflow_description = workflow_data.get("description", "")

    html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Workflow Preview: {workflow_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            margin-bottom: 20px;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }}
        .workflow-title {{
            color: #333;
            margin: 0;
        }}
        .workflow-description {{
            color: #666;
            margin: 5px 0 0 0;
        }}
        .diagram-container {{
            text-align: center;
            margin: 20px 0;
        }}
        .metadata {{
            margin-top: 20px;
            font-size: 0.9em;
            color: #666;
        }}
        .legend-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0 0 0;
        }}
        .legend-table td {{
            padding: 4px 8px;
            border-bottom: 1px solid #eee;
            vertical-align: top;
        }}
        .legend-table td:first-child {{
            font-family: monospace;
            font-weight: bold;
            width: 120px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="workflow-title">{workflow_name}</h1>
            {f'<p class="workflow-description">{workflow_description}</p>' if workflow_description else ''}
        </div>
        
        <div class="diagram-container">
            <div class="mermaid">
{mermaid_code}
            </div>
        </div>
    <div class="legend" style="text-align:left; max-width:400px; margin:0 0 20px 0; background:#fafafa; border:1px solid #ddd; padding:12px; border-radius:6px; font-size:0.9em;">
            <strong>Legend</strong>
            <table class="legend-table">
                <tr><td>🧑</td><td>Manual action</td></tr>
                <tr><td>📓</td><td>Notebook action</td></tr>
                <tr><td>📅</td><td>Schedule action</td></tr>
                <tr><td>🛠️</td><td>Job action</td></tr>
                <tr><td>(priv1, priv2)</td><td>Privileges required</td></tr>
                <tr><td>NB abcdef..</td><td>Truncated Notebook ID</td></tr>
                <tr><td>⚡️ NAME</td><td>UI icon class</td></tr>
                <tr><td>hidden</td><td>Hidden (not shown in UI)</td></tr>
            </table>
        </div>
        
        <div class="metadata">
            <h3>Workflow Details</h3>
            <p><strong>States:</strong> {len(workflow_data.get('states', []))}</p>
            <p><strong>Actions:</strong> {len(workflow_data.get('actions', []))}</p>
            {f'<p><strong>Workspace:</strong> {workflow_data.get("workspace", "N/A")}</p>' if workflow_data.get("workspace") else ''}
        </div>
    </div>
    
    <script>
        mermaid.initialize({{ 
            startOnLoad: true,
            theme: 'default',
            fontFamily: 'Arial, sans-serif'
        }});
    </script>
</body>
</html>"""

    return html_template


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

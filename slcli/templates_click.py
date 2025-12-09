"""CLI commands for managing SystemLink test plan templates."""

import json
import os
import sys
from typing import Any, Dict, List, Optional

import click

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import (
    ExitCodes,
    extract_error_type,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    sanitize_filename,
)
from .workspace_utils import get_workspace_display_name, resolve_workspace_filter


def _query_all_templates(
    workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """Query all test plan templates using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all templates, optionally filtered by workspace
    """
    url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
    all_templates = []
    continuation_token = None

    while True:
        # Build payload for the request
        payload = {
            "take": 100,  # Use smaller page size for efficient pagination
            "orderBy": "TEMPLATE_GROUP",
            "descending": False,
            "projection": ["ID", "NAME", "WORKSPACE", "TEMPLATE_GROUP"],
        }

        # Add workspace filter if specified
        if workspace_filter:
            payload["filter"] = f'WORKSPACE == "{workspace_filter}"'

        # Add continuation token if we have one
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        # Extract templates from this page
        templates = data.get("testPlanTemplates", [])
        all_templates.extend(templates)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_templates


def register_templates_commands(cli: Any) -> None:
    """Register the 'template' command group and its subcommands."""

    @cli.group()
    def template() -> None:
        """Manage test plan templates."""
        pass

    @template.command(name="init")
    @click.option(
        "--name",
        "-n",
        help="Template name (will prompt if not provided)",
    )
    @click.option(
        "--template-group",
        "-g",
        help="Template group (will prompt if not provided)",
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (default: <name>-template.json)",
    )
    def init_template(
        name: Optional[str], template_group: Optional[str], output: Optional[str]
    ) -> None:
        """Initialize a new test plan template JSON file.

        Creates a template JSON file with the required schema structure.
        Name and Template Group are mandatory, all other fields are optional.
        """
        # Prompt for required fields if not provided
        if not name:
            name = click.prompt("Template name", type=str)
        if not template_group:
            template_group = click.prompt("Template group", type=str)

        # At this point, name and template_group are guaranteed to be strings
        assert name is not None
        assert template_group is not None

        # Generate output filename if not provided
        if not output:
            safe_name = sanitize_filename(name, "template")
            output = f"{safe_name}-template.json"

        # Create template structure based on the schema
        template_data = {
            "testPlanTemplates": [
                {
                    # Required fields
                    "name": name,
                    "templateGroup": template_group,
                    # Optional fields - customize as needed
                    "productFamilies": ["// Add product families like: cRIO, BTS, PXI, etc."],
                    "partNumbers": ["// Add specific part numbers like: 156502A-11L, ADC-1688"],
                    "summary": "// Brief summary of what this template does",
                    "description": "// Detailed description of the test template and its purpose",
                    "testProgram": "// Name of the test program to execute",
                    "estimatedDurationInSeconds": 3600,
                    "systemFilter": '// Filter expression for system selection, e.g., properties.data[\\"Lab\\"] = \\"Battery Pack Lab\\"',
                    "executionActions": [
                        {
                            "type": "JOB",
                            "action": "START",
                            "jobs": [
                                {
                                    "functions": ["state.apply"],
                                    "arguments": [["<properties.startTestStateId>"]],
                                }
                            ],
                        },
                        {
                            "type": "NOTEBOOK",
                            "action": "PAUSE",
                            "notebookId": "// UUID of notebook to pause",
                            "parameters": {"operation": "pause"},
                        },
                        {
                            "type": "NOTEBOOK",
                            "action": "RESUME",
                            "notebookId": "// UUID of notebook to resume",
                            "parameters": {"operation": "resume"},
                        },
                        {"type": "MANUAL", "action": "ABORT"},
                        {
                            "type": "NOTEBOOK",
                            "action": "END",
                            "notebookId": "// UUID of final notebook to execute",
                            "parameters": {
                                "partNumber": "<partNumber>",
                                "dut": "<dutId>",
                                "operator": "<assignedTo>",
                                "testProgram": "<testProgram>",
                                "location": "<properties.region>-<properties.facility>-<properties.lab>",
                            },
                        },
                    ],
                    "fileIds": ["// Array of file UUIDs associated with this template"],
                    "workspace": "// UUID of the workspace where this template belongs",
                    "properties": {
                        "region": "// Example: Austin",
                        "facility": "// Example: Building A",
                        "lab": "// Example: Battery Pack Lab",
                        "startTestStateId": "// UUID for initial test state",
                    },
                    "workflowId": "// Optional: UUID of associated workflow",
                }
            ]
        }

        try:
            # Check if file already exists
            if os.path.exists(output):
                if not click.confirm(f"File {output} already exists. Overwrite?"):
                    click.echo("Template initialization cancelled.")
                    return

            # Save the template file
            with open(output, "w", encoding="utf-8") as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)

            click.echo(f"✓ Template initialized: {output}")
            click.echo("Edit the file to customize your template:")
            click.echo("  - name and templateGroup are required")
            click.echo(
                "  - All other fields are optional (remove unused fields or set appropriate values)"
            )
            click.echo("  - Use 'slcli templates import' to upload the template when ready")
            click.echo(
                "  - See TestPlanTemplate.json for a complete example with execution actions"
            )

        except Exception as exc:
            click.echo(f"✗ Error creating template file: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

    @template.command(name="list")
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
        help="Maximum number of templates to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_templates(
        workspace: Optional[str] = None, take: int = 25, format: str = "table"
    ) -> None:
        """List available user-defined test plan templates."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()

            # Resolve workspace filter to ID if specified
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Use continuation token pagination to get all templates
            all_templates = _query_all_templates(workspace_id, workspace_map)

            # Create a mock response with all data
            resp: Any = FilteredResponse({"testPlanTemplates": all_templates})

            # Use universal response handler with template formatter
            def template_formatter(template: dict) -> list:
                ws_guid = template.get("workspace", "")
                ws_name = get_workspace_display_name(ws_guid, workspace_map)
                return [
                    template.get("name", "Unknown"),
                    ws_name,
                    template.get("id", ""),
                    template.get("templateGroup", "N/A"),
                ]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="testPlanTemplates",
                item_name="template",
                format_output=format_output,
                formatter_func=template_formatter,
                headers=["Name", "Workspace", "Template ID", "Group"],
                column_widths=[40, 30, 36, 25],
                empty_message="No test plan templates found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @template.command(name="export")
    @click.option(
        "--id",
        "-i",
        "template_id",
        required=True,
        help="Test plan template ID to export",
    )
    @click.option("--output", "-o", help="Output JSON file (default: <template-name>.json)")
    def export_template(template_id: str, output: Optional[str] = None) -> None:
        """Download/export a test plan template as a local JSON file."""
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        payload = {"take": 1, "filter": f'ID == "{template_id}"'}

        try:
            resp = make_api_request("POST", url, payload)
            data = resp.json()
            items = data.get("testPlanTemplates", []) if isinstance(data, dict) else []

            if not items:
                click.echo(f"✗ Test plan template with ID {template_id} not found.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            template_data = items[0]

            # Generate output filename if not provided
            if not output:
                template_name = template_data.get("name", f"template-{template_id}")
                safe_name = sanitize_filename(template_name, f"template-{template_id}")
                output = f"{safe_name}.json"

            # Use universal export handler
            UniversalResponseHandler.handle_export_response(
                resp=resp,
                item_name="template",
                output_file=output,
                success_message_template="✓ Template exported to {output_file}",
            )

        except Exception as exc:
            handle_api_error(exc)

    @template.command(name="import")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file",
    )
    def import_template(input_file: str) -> None:
        """Upload/import a test plan template from a local JSON file."""
        url = f"{get_base_url()}/niworkorder/v1/testplan-templates"
        allowed_fields = {
            "name",
            "templateGroup",
            "productFamilies",
            "partNumbers",
            "summary",
            "description",
            "testProgram",
            "estimatedDurationInSeconds",
            "systemFilter",
            "executionActions",
            "fileIds",
            "workspace",
            "properties",
            "dashboard",
            "workflowId",
        }
        try:
            data: Any = load_json_file(input_file)
            if isinstance(data, dict) and "testPlanTemplates" in data:
                data = data["testPlanTemplates"]
            elif isinstance(data, dict):
                data = [data]
            # At this point, data should be a list of dicts
            templates_data: List[Dict[str, Any]] = data if isinstance(data, list) else []
            filtered = []
            for entry in templates_data:
                if isinstance(entry, dict):
                    filtered.append({k: v for k, v in entry.items() if k in allowed_fields})
            payload = {"testPlanTemplates": filtered}

            resp = make_api_request("POST", url, payload)

            # Check response body for partial failures, even if HTTP status is 200
            response_data = resp.json() if resp.text.strip() else {}
            failed_templates = response_data.get("failedTestPlanTemplates", [])

            if failed_templates:
                # Handle partial or complete failures
                click.echo("✗ Template import failed:", err=True)

                # Extract detailed error information from the response
                main_error = response_data.get("error", {})
                inner_errors = main_error.get("innerErrors", [])

                # Create a mapping of resource IDs to error details
                error_details = {}
                for inner_error in inner_errors:
                    resource_id = inner_error.get("resourceId", "Unknown")
                    error_name = inner_error.get("name", "")
                    error_message = inner_error.get("message", "Unknown error")
                    resource_type = inner_error.get("resourceType", "")

                    error_details[resource_id] = {
                        "name": error_name,
                        "message": error_message,
                        "type": resource_type,
                    }

                # Report errors for each failed template
                for failed_template in failed_templates:
                    template_name = failed_template.get("name", "Unknown")

                    # Try to find matching error details
                    error_info = error_details.get(template_name, {})
                    error_name = error_info.get("name", "")
                    error_message = error_info.get("message", "Unknown error")

                    # Format the error output
                    if error_name:
                        error_type = extract_error_type(error_name)
                        click.echo(f"  - {template_name}: {error_type} - {error_message}", err=True)
                    else:
                        click.echo(f"  - {template_name}: {error_message}", err=True)

                # Show general error information if available
                if main_error.get("message") and len(failed_templates) > 1:
                    click.echo(f"\nGeneral error: {main_error.get('message')}", err=True)

                sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                click.echo("✓ Test plan template imported successfully.")

        except Exception as exc:
            handle_api_error(exc)

    @template.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "template_id",
        required=True,
        help="Test plan template ID to delete",
    )
    @click.confirmation_option(prompt="Are you sure you want to delete this template?")
    def delete_template(template_id: str) -> None:
        """Delete a test plan template by ID."""
        url = f"{get_base_url()}/niworkorder/v1/delete-testplan-templates"
        payload = {"ids": [template_id]}
        try:
            resp = make_api_request("POST", url, payload)
            if resp.status_code in (200, 204):
                click.echo(f"✓ Test plan template {template_id} deleted successfully.")
            else:
                click.echo(
                    f"✗ Failed to delete test plan template {template_id}: {resp.text}", err=True
                )
                sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

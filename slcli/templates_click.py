"""CLI commands for managing SystemLink test plan templates."""

import json
import os
from typing import Optional

import click

from .utils import (
    get_base_url,
    handle_api_error,
    output_list_data,
    make_api_request,
    get_workspace_map,
    load_json_file,
    save_json_file,
    sanitize_filename,
    extract_error_type,
)


def register_templates_commands(cli):
    """Register the 'template' command group and its subcommands."""

    @cli.group()
    def template():
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
    def init_template(name, template_group, output):
        """Initialize a new test plan template JSON file.

        Creates a template JSON file with the required schema structure.
        Name and Template Group are mandatory, all other fields are optional.
        """
        # Prompt for required fields if not provided
        if not name:
            name = click.prompt("Template name", type=str)
        if not template_group:
            template_group = click.prompt("Template group", type=str)

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
            raise click.ClickException(f"Error creating template file: {exc}")

    @template.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        help="Output format: table or json",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name",
    )
    def list_templates(format: str = "table", workspace: Optional[str] = None):
        """List available user-defined test plan templates.

        Args:
            format (str, optional): Output format (table or json).
            workspace (str, optional): Filter by workspace name.
        """
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        payload = {
            "take": 1000,
            "orderBy": "TEMPLATE_GROUP",
            "descending": False,
            "projection": ["ID", "NAME", "WORKSPACE"],
        }
        try:
            workspace_map = get_workspace_map()
            resp = make_api_request("POST", url, payload)
            data = resp.json()
            items = data.get("testPlanTemplates", []) if isinstance(data, dict) else []

            # Convert items to consistent format for output
            template_data = []
            for item in items:
                ws_guid = item.get("workspace", "")
                ws_name = workspace_map.get(ws_guid, ws_guid)
                template_info = {
                    "id": item.get("id", ""),
                    "name": item.get("name", ""),
                    "workspace": ws_name,
                }
                template_data.append(template_info)

            # Filter by workspace if specified
            if workspace:
                # Filter by workspace name (case-insensitive partial match)
                filtered_data = []
                for template in template_data:
                    ws_name = template["workspace"]
                    # Match by name (case-insensitive partial match)
                    if workspace.lower() in ws_name.lower():
                        filtered_data.append(template)
                template_data = filtered_data

            # Use shared output function
            def template_table_row(template):
                short_name = template["name"][:40] + ("…" if len(template["name"]) > 40 else "")
                return [template["workspace"], short_name, template["id"]]

            output_list_data(
                template_data,
                format,
                ["Workspace", "Name", "Template ID"],
                template_table_row,
                "No test plan templates found.",
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
    def export_template(template_id, output):
        """Download/export a test plan template as a local JSON file."""
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        payload = {"take": 1, "filter": f'ID == "{template_id}"'}
        try:
            resp = make_api_request("POST", url, payload)
            data = resp.json()
            items = data.get("testPlanTemplates", []) if isinstance(data, dict) else []
            if not items:
                click.echo(f"✗ Test plan template with ID {template_id} not found.", err=True)
                raise click.ClickException(f"Test plan template with ID {template_id} not found.")

            template_data = items[0]

            # Generate output filename if not provided
            if not output:
                template_name = template_data.get("name", f"template-{template_id}")
                safe_name = sanitize_filename(template_name, f"template-{template_id}")
                output = f"{safe_name}.json"

            save_json_file(template_data, output)
            click.echo(f"✓ Test plan template exported to {output}")
        except Exception as exc:
            if "not found" not in str(exc).lower():
                handle_api_error(exc)
            else:
                click.echo(f"✗ Error: {exc}", err=True)
                raise click.ClickException(str(exc))

    @template.command(name="import")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file",
    )
    def import_template(input_file):
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
            data = load_json_file(input_file)
            if isinstance(data, dict) and "testPlanTemplates" in data:
                data = data["testPlanTemplates"]
            elif isinstance(data, dict):
                data = [data]
            filtered = []
            for entry in data:
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

                raise click.ClickException("Template import failed. See errors above.")
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
    def delete_template(template_id):
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
                raise click.ClickException(
                    f"Failed to delete test plan template {template_id}: {resp.text}"
                )
        except Exception as exc:
            handle_api_error(exc)

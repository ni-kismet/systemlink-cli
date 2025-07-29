"""CLI commands for managing SystemLink Dynamic Form Fields."""

import http.server
import json
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

import click

from .utils import (
    ExitCodes,
    filter_by_workspace,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    output_formatted_list,
    resolve_workspace_filter,
    sanitize_filename,
    save_json_file,
)


def register_dff_commands(cli):
    """Register the 'dff' command group and its subcommands."""

    @cli.group()
    def dff():
        """Manage dynamic form fields (configurations, groups, fields, tables)."""
        pass

    # Configuration commands
    @dff.group()
    def config():
        """Manage dynamic form field configurations."""
        pass

    @config.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=1000,
        show_default=True,
        help="Maximum number of configurations to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_configurations(
        workspace: Optional[str] = None, take: int = 1000, format: str = "table"
    ):
        """List dynamic form field configurations."""
        url = f"{get_base_url()}/nidynamicformfields/v1/configurations"

        try:
            params = {"Take": take}

            # Build URL with query parameters
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()
            configurations = data.get("configurations", [])

            # Filter by workspace if specified
            if workspace:
                workspace_map = get_workspace_map()
                configurations = filter_by_workspace(configurations, workspace, workspace_map)

            def format_config_row(config):
                workspace_map = get_workspace_map()
                workspace_id = config.get("workspace", "")
                workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
                name = config.get("name", "")
                config_id = config.get("id", "")
                return [workspace_name, name, config_id]

            output_formatted_list(
                configurations,
                format,
                ["Workspace", "Name", "Configuration ID"],
                [36, 40, 36],
                format_config_row,
                "No dynamic form field configurations found.",
                "configuration(s)",
            )

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="get")
    @click.option(
        "--id",
        "-i",
        "config_id",
        required=True,
        help="Configuration ID to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="json",
        show_default=True,
        help="Output format: table or json",
    )
    def get_configuration(config_id: str, format: str = "json"):
        """Get a specific dynamic form field configuration by ID."""
        url = f"{get_base_url()}/nidynamicformfields/v1/resolved-configuration"

        try:
            params = {"configurationId": config_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            # Table format - show basic info
            configuration = data.get("configuration", {})
            workspace_map = get_workspace_map()
            workspace_id = configuration.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id)

            click.echo("Configuration Details")
            click.echo("=" * 50)
            click.echo(f"ID: {configuration.get('id', '')}")
            click.echo(f"Name: {configuration.get('name', '')}")
            click.echo(f"Workspace: {workspace_name}")
            click.echo(f"Resource Type: {configuration.get('resourceType', '')}")

            groups = data.get("groups", [])
            fields = data.get("fields", [])
            click.echo(f"Groups: {len(groups)}")
            click.echo(f"Fields: {len(fields)}")

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="create")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with configuration data",
    )
    def create_configuration(input_file: str):
        """Create dynamic form field configurations from a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/configurations"

        try:
            data = load_json_file(input_file)

            # Ensure data is in the expected format
            if isinstance(data, dict) and "configurations" not in data:
                # Wrap single configuration
                data = {"configurations": [data]}
            elif isinstance(data, list):
                # Wrap list of configurations
                data = {"configurations": data}

            resp = make_api_request("POST", url, data)

            # Check for partial success response
            response_data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 201:
                # Full success
                click.echo("✓ Dynamic form field configurations created successfully.")
                created_configs = response_data.get("configurations", [])
                for config in created_configs:
                    click.echo(f"  - {config.get('name', 'Unknown')}: {config.get('id', '')}")
            elif resp.status_code == 200:
                # Partial success
                click.echo("⚠ Some configurations were created, but some failed:", err=True)

                # Show successful creations
                successful = response_data.get("created", [])
                if successful:
                    click.echo("Created:")
                    for config in successful:
                        click.echo(f"  ✓ {config.get('name', 'Unknown')}: {config.get('id', '')}")

                # Show failures
                failed = response_data.get("failed", [])
                if failed:
                    click.echo("Failed:")
                    for failure in failed:
                        name = failure.get("name", "Unknown")
                        error = failure.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        click.echo(f"  ✗ {name}: {error_msg}", err=True)

                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="update")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with updated configuration data",
    )
    def update_configuration(input_file: str):
        """Update dynamic form field configurations from a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/update-configurations"

        try:
            data = load_json_file(input_file)

            # Ensure data is in the expected format
            if isinstance(data, dict) and "configurations" not in data:
                data = {"configurations": [data]}
            elif isinstance(data, list):
                data = {"configurations": data}

            resp = make_api_request("POST", url, data)
            response_data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 200:
                # Check if it's a partial success response
                updated_configs = response_data.get("configurations", [])
                failed_updates = response_data.get("failed", [])

                if failed_updates:
                    click.echo("⚠ Some configurations were updated, but some failed:", err=True)

                    if updated_configs:
                        click.echo("Updated:")
                        for config in updated_configs:
                            click.echo(
                                f"  ✓ {config.get('name', 'Unknown')}: {config.get('id', '')}"
                            )

                    click.echo("Failed:")
                    for failure in failed_updates:
                        name = failure.get("name", "Unknown")
                        error = failure.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        click.echo(f"  ✗ {name}: {error_msg}", err=True)

                    sys.exit(ExitCodes.GENERAL_ERROR)
                else:
                    click.echo("✓ Dynamic form field configurations updated successfully.")
                    for config in updated_configs:
                        click.echo(f"  - {config.get('name', 'Unknown')}: {config.get('id', '')}")

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "config_ids",
        multiple=True,
        help="Configuration ID(s) to delete (can be specified multiple times)",
    )
    @click.option(
        "--file",
        "-f",
        "input_file",
        help="JSON file containing IDs to delete",
    )
    @click.confirmation_option(prompt="Are you sure you want to delete these configurations?")
    def delete_configuration(config_ids: tuple, input_file: Optional[str] = None):
        """Delete dynamic form field configurations."""
        if not config_ids and not input_file:
            click.echo("✗ Must provide either --id or --file", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        url = f"{get_base_url()}/nidynamicformfields/v1/delete"

        try:
            ids_to_delete = list(config_ids)

            if input_file:
                file_data = load_json_file(input_file)
                if isinstance(file_data, dict):
                    ids_to_delete.extend(file_data.get("configurationIds", []))
                elif isinstance(file_data, list):
                    ids_to_delete.extend(file_data)

            if not ids_to_delete:
                click.echo("✗ No configuration IDs found to delete", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            payload = {"configurationIds": ids_to_delete}
            resp = make_api_request("POST", url, payload)

            if resp.status_code in (200, 204):
                click.echo(f"✓ {len(ids_to_delete)} configuration(s) deleted successfully.")
            else:
                # Handle partial success if needed
                response_data = resp.json() if resp.text.strip() else {}
                failed_deletes = response_data.get("failed", [])

                if failed_deletes:
                    click.echo("⚠ Some configurations were deleted, but some failed:", err=True)
                    for failure in failed_deletes:
                        config_id = failure.get("id", "Unknown")
                        error = failure.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        click.echo(f"  ✗ {config_id}: {error_msg}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="export")
    @click.option(
        "--id",
        "-i",
        "config_id",
        required=True,
        help="Configuration ID to export",
    )
    @click.option("--output", "-o", help="Output JSON file (default: <config-name>.json)")
    def export_configuration(config_id: str, output: Optional[str] = None):
        """Export a dynamic form field configuration to a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/resolved-configuration"

        try:
            params = {"configurationId": config_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            # Generate output filename if not provided
            if not output:
                config_name = data.get("configuration", {}).get("name", f"config-{config_id}")
                safe_name = sanitize_filename(config_name, f"config-{config_id}")
                output = f"{safe_name}.json"

            save_json_file(data, output)
            click.echo(f"✓ Configuration exported to {output}")

        except Exception as exc:
            handle_api_error(exc)

    @config.command(name="init")
    @click.option(
        "--name",
        "-n",
        help="Configuration name (will prompt if not provided)",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Workspace name or ID (will prompt if not provided)",
    )
    @click.option(
        "--resource-type",
        "-r",
        help="Resource type (will prompt if not provided)",
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (default: <name>-config.json)",
    )
    def init_configuration(
        name: Optional[str] = None,
        workspace: Optional[str] = None,
        resource_type: Optional[str] = None,
        output: Optional[str] = None,
    ):
        """Create a template configuration file for dynamic form fields."""
        try:
            # Prompt for required fields if not provided
            if not name:
                name = click.prompt("Configuration name")

            if not workspace:
                workspace = click.prompt("Workspace name or ID")

            if not resource_type:
                resource_type = click.prompt("Resource type")

            # Generate output filename if not provided
            if not output:
                safe_name = sanitize_filename(name or "config", "config")
                output = f"{safe_name}-config.json"

            # Try to resolve workspace name to ID
            try:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace or "", workspace_map)
            except Exception:
                workspace_id = workspace or ""

            # Create template configuration
            template_config = {
                "configurations": [
                    {
                        "name": name,
                        "workspace": workspace_id,
                        "resourceType": resource_type,
                        "groupKeys": ["// Array of group keys, e.g., ['group1', 'group2']"],
                        "properties": {"// Add custom properties here": "value"},
                    }
                ],
                "groups": [
                    {
                        "key": "group1",
                        "workspace": workspace_id,
                        "name": "Example Group",
                        "displayText": "Example Group Display Name",
                        "fieldKeys": ["field1", "field2"],
                        "properties": {},
                    }
                ],
                "fields": [
                    {
                        "key": "field1",
                        "workspace": workspace_id,
                        "name": "Example Field",
                        "displayText": "Example Field Display Name",
                        "fieldType": "STRING",
                        "required": False,
                        "validation": {"// Add validation rules": "as needed"},
                        "properties": {},
                    }
                ],
            }

            save_json_file(template_config, output)
            click.echo(f"✓ Configuration template created: {output}")
            click.echo("Edit the file to customize:")
            click.echo("  - Add/modify groups and fields")
            click.echo("  - Set validation rules")
            click.echo("  - Configure field types and properties")

        except Exception as exc:
            click.echo(f"✗ Error creating configuration template: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

    # Groups commands
    @dff.group()
    def groups():
        """Manage dynamic form field groups."""
        pass

    @groups.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=1000,
        show_default=True,
        help="Maximum number of groups to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_groups(workspace: Optional[str] = None, take: int = 1000, format: str = "table"):
        """List dynamic form field groups."""
        url = f"{get_base_url()}/nidynamicformfields/v1/groups"

        try:
            params = {"Take": take}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()
            groups = data.get("groups", [])

            # Filter by workspace if specified
            if workspace:
                workspace_map = get_workspace_map()
                groups = filter_by_workspace(groups, workspace, workspace_map)

            def format_group_row(group):
                workspace_map = get_workspace_map()
                workspace_id = group.get("workspace", "")
                workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
                name = group.get("displayText", group.get("name", ""))
                key = group.get("key", "")
                return [workspace_name, name, key]

            output_formatted_list(
                groups,
                format,
                ["Workspace", "Name", "Key"],
                [23, 32, 39],
                format_group_row,
                "No dynamic form field groups found.",
                "group(s)",
            )

        except Exception as exc:
            handle_api_error(exc)

    # Fields commands
    @dff.group()
    def fields():
        """Manage dynamic form field definitions."""
        pass

    @fields.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=1000,
        show_default=True,
        help="Maximum number of fields to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_fields(workspace: Optional[str] = None, take: int = 1000, format: str = "table"):
        """List dynamic form fields."""
        url = f"{get_base_url()}/nidynamicformfields/v1/fields"

        try:
            params = {"Take": take}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()
            fields = data.get("fields", [])

            # Filter by workspace if specified
            if workspace:
                workspace_map = get_workspace_map()
                fields = filter_by_workspace(fields, workspace, workspace_map)

            def format_field_row(field):
                workspace_map = get_workspace_map()
                workspace_id = field.get("workspace", "")
                workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
                name = field.get("displayText", field.get("name", ""))
                key = field.get("key", "")
                return [workspace_name, name, key]

            output_formatted_list(
                fields,
                format,
                ["Workspace", "Name", "Key"],
                [23, 32, 39],
                format_field_row,
                "No dynamic form fields found.",
                "field(s)",
            )

        except Exception as exc:
            handle_api_error(exc)

    # Table properties commands
    @dff.group()
    def tables():
        """Manage table properties."""
        pass

    @tables.command(name="query")
    @click.option(
        "--workspace",
        "-w",
        required=True,
        help="Workspace name or ID to query tables for",
    )
    @click.option(
        "--resource-id",
        "-i",
        required=True,
        help="Resource ID to filter by",
    )
    @click.option(
        "--resource-type",
        "-r",
        required=True,
        help="Resource type to filter by",
    )
    @click.option(
        "--keys",
        "-k",
        multiple=True,
        help="Table keys to filter by (can be specified multiple times)",
    )
    @click.option(
        "--take",
        default=1000,
        show_default=True,
        help="Maximum number of table properties to return",
    )
    @click.option(
        "--continuation-token",
        "-c",
        help="Continuation token for pagination",
    )
    @click.option(
        "--return-count",
        is_flag=True,
        help="Return the total count of accessible table properties",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def query_tables(
        workspace: str,
        resource_id: str,
        resource_type: str,
        keys: tuple = (),
        take: int = 1000,
        continuation_token: Optional[str] = None,
        return_count: bool = False,
        format: str = "table",
    ):
        """Query table properties."""
        url = f"{get_base_url()}/nidynamicformfields/v1/query-tables"

        try:
            # Try to resolve workspace name to ID
            try:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace, workspace_map)
            except Exception:
                workspace_id = workspace

            # Build payload according to the correct API schema
            payload = {
                "workspace": workspace_id,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "take": take,
                "returnCount": return_count,
            }

            # Add optional parameters if provided
            if keys:
                payload["keys"] = list(keys)

            if continuation_token:
                payload["continuationToken"] = continuation_token

            resp = make_api_request("POST", url, payload)
            data = resp.json()
            tables = data.get("tables", [])

            def format_table_row(table):
                workspace_map = get_workspace_map()
                workspace_id = table.get("workspace", "")
                workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
                resource_type = table.get("resourceType", "")
                resource_id = table.get("resourceId", "")
                table_id = table.get("id", "")
                return [workspace_name, resource_type, resource_id, table_id]

            output_formatted_list(
                tables,
                format,
                ["Workspace", "Resource Type", "Resource ID", "Table ID"],
                [36, 30, 18, 36],
                format_table_row,
                "No table properties found.",
                "table(s)",
            )

        except Exception as exc:
            handle_api_error(exc)

    @tables.command(name="get")
    @click.option(
        "--id",
        "-i",
        "table_id",
        required=True,
        help="Table property ID to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="json",
        show_default=True,
        help="Output format: table or json",
    )
    def get_table(table_id: str, format: str = "json"):
        """Get a specific table property by ID."""
        url = f"{get_base_url()}/nidynamicformfields/v1/table"

        try:
            params = {"tablePropertyId": table_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            # Table format - show basic info
            table_property = data.get("tableProperty", {})
            workspace_map = get_workspace_map()
            workspace_id = table_property.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id)

            click.echo("Table Property Details")
            click.echo("=" * 50)
            click.echo(f"ID: {table_property.get('id', '')}")
            click.echo(f"Workspace: {workspace_name}")
            click.echo(f"Resource Type: {table_property.get('resourceType', '')}")
            click.echo(f"Resource ID: {table_property.get('resourceId', '')}")

            # Show data frame info if available
            data_frame = table_property.get("dataFrame", {})
            if data_frame:
                columns = data_frame.get("columns", [])
                data_rows = data_frame.get("data", [])
                click.echo(f"Columns: {len(columns)}")
                click.echo(f"Rows: {len(data_rows)}")

        except Exception as exc:
            handle_api_error(exc)

    # Editor command (future stub)
    @dff.command(name="edit")
    @click.option(
        "--file",
        "-f",
        help="JSON file to edit (will create new if not exists)",
    )
    @click.option(
        "--port",
        "-p",
        default=8080,
        show_default=True,
        help="Port for local HTTP server",
    )
    @click.option(
        "--output-dir",
        "-o",
        default="dff-editor",
        show_default=True,
        help="Directory to create editor files in",
    )
    def edit_configuration(
        file: Optional[str] = None, port: int = 8080, output_dir: str = "dff-editor"
    ):
        """Launch a local web editor for dynamic form field configurations.

        This command will create a standalone HTML editor in the specified directory
        and start a local HTTP server for editing dynamic form field configurations.
        """
        try:
            # Create the editor directory
            editor_path = Path(output_dir)
            editor_path.mkdir(exist_ok=True)

            # Load existing file content if specified
            initial_content = ""
            if file and Path(file).exists():
                try:
                    existing_data = load_json_file(file)
                    initial_content = json.dumps(existing_data, indent=2)
                except Exception:
                    initial_content = (
                        '{\n  "configurations": [],\n  "groups": [],\n  "fields": []\n}'
                    )
            else:
                initial_content = """{
  "configurations": [
    {
      "name": "Example Configuration",
      "workspace": "your-workspace-id",
      "resourceType": "your-resource-type",
      "groupKeys": ["group1"],
      "properties": {}
    }
  ],
  "groups": [
    {
      "key": "group1",
      "workspace": "your-workspace-id",
      "name": "Example Group",
      "displayText": "Example Group",
      "fieldKeys": ["field1"],
      "properties": {}
    }
  ],
  "fields": [
    {
      "key": "field1",
      "workspace": "your-workspace-id",
      "name": "Example Field",
      "displayText": "Example Field",
      "fieldType": "STRING",
      "required": false,
      "validation": {},
      "properties": {}
    }
  ]
}"""

            # Get the HTML template from the standalone file or use bundled template
            template_path = Path(__file__).parent.parent / "dff-editor" / "index.html"

            if template_path.exists():
                # Use the standalone HTML file as template
                html_template = template_path.read_text()

                # Replace the placeholder content with initial content
                # Look for the textarea content between the tags
                import re

                textarea_pattern = r"(<textarea[^>]*>)(.*?)(</textarea>)"
                match = re.search(textarea_pattern, html_template, re.DOTALL)

                if match:
                    html_content = html_template.replace(match.group(2), initial_content)
                else:
                    # Fallback if textarea pattern not found
                    html_content = html_template

                # Update the file info section based on whether we're editing a file
                if file:
                    html_content = html_content.replace(
                        '<div class="file-info"><strong>Mode:</strong> New Configuration</div>',
                        f'<div class="file-info"><strong>Editing:</strong> {file}</div>',
                    )

            else:
                # Fallback: Create the editor using a basic template
                click.echo("⚠ Standalone template not found, using basic fallback", err=True)
                html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dynamic Form Fields Editor</title>
    <style>
        body {{ font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        textarea {{ width: 100%; height: 400px; font-family: monospace; }}
        button {{ padding: 10px 20px; margin: 5px; background: #007acc; color: white; border: none; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>Dynamic Form Fields Editor</h1>
    <p>Basic fallback editor. For the full experience, ensure the standalone HTML template exists.</p>
    {"<p><strong>Editing:</strong> " + file + "</p>" if file else "<p><strong>Mode:</strong> New Configuration</p>"}
    <textarea id="jsonEditor">{initial_content}</textarea>
    <div>
        <button onclick="downloadJson()">Download JSON</button>
    </div>
    <script>
        function downloadJson() {{
            const content = document.getElementById('jsonEditor').value;
            const blob = new Blob([content], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'dff-configuration.json';
            a.click();
            URL.revokeObjectURL(url);
        }}
    </script>
</body>
</html>"""

            # Write the HTML file
            html_file = editor_path / "index.html"
            html_file.write_text(html_content)

            # Create a README file
            readme_content = f"""# Dynamic Form Fields Editor

This directory contains a standalone web editor for SystemLink Dynamic Form Fields configurations.

## Files

- `index.html` - The main editor interface
- `README.md` - This file

## Usage

1. Start the editor server:
   ```
   slcli dff edit --output-dir {output_dir} --port {port}
   ```

2. Open your browser to: http://localhost:{port}

3. Edit your configuration in the JSON editor

4. Use the tools to validate, format, and download your configuration

## Future Enhancements

This editor is currently a basic JSON editor. Future versions will include:

- Visual form builder
- Field type validation
- Real-time preview
- Schema validation
- Direct save to file
- Integration with SystemLink API

## Configuration Structure

Dynamic Form Fields configurations consist of:

- **Configurations**: Top-level configuration objects that define how forms are structured
- **Groups**: Logical groupings of fields within a configuration
- **Fields**: Individual form fields with types, validation rules, and properties

See the example configuration in the editor for a sample structure.
"""

            readme_file = editor_path / "README.md"
            readme_file.write_text(readme_content)

            # Start HTTP server
            class Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, directory=str(editor_path), **kwargs)

                def log_message(self, format, *args):
                    # Suppress server logs
                    pass

            try:
                with socketserver.TCPServer(("", port), Handler) as httpd:
                    server_url = f"http://localhost:{port}"

                    # Start server in background thread
                    server_thread = threading.Thread(target=httpd.serve_forever)
                    server_thread.daemon = True
                    server_thread.start()

                    click.echo(f"✓ Created editor files in: {editor_path.absolute()}")
                    click.echo(f"✓ Starting Dynamic Form Fields editor at {server_url}")
                    click.echo("✓ Opening in your default browser...")

                    # Open browser
                    webbrowser.open(server_url)

                    click.echo(f"\nEditor files created in: {editor_path.absolute()}")
                    click.echo("- index.html (main editor)")
                    click.echo("- README.md (documentation)")
                    click.echo("\nPress Ctrl+C to stop the editor server")

                    try:
                        # Keep the server running
                        while True:
                            threading.Event().wait(1)
                    except KeyboardInterrupt:
                        click.echo("\n✓ Editor server stopped")
                        click.echo(f"✓ Editor files remain in: {editor_path.absolute()}")
                        httpd.shutdown()

            except OSError as e:
                if "Address already in use" in str(e):
                    click.echo(
                        f"✗ Port {port} is already in use. Try a different port with --port",
                        err=True,
                    )
                    sys.exit(ExitCodes.GENERAL_ERROR)
                else:
                    raise

        except Exception as exc:
            click.echo(f"✗ Error starting editor: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

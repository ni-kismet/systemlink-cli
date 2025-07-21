"""CLI commands for managing SystemLink test plan templates."""

import click

from .utils import (
    get_base_url,
    handle_api_error,
    output_list_data,
    make_api_request,
    get_workspace_map,
    load_json_file,
    save_json_file,
)


def register_templates_commands(cli):
    """Register the 'templates' command group and its subcommands."""

    @cli.group()
    def templates():
        """Manage test plan templates."""
        pass

    @templates.command(name="list")
    @click.option(
        "--output",
        "-o",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        help="Output format: table or json",
    )
    def list_templates(output: str = "table"):
        """List available user-defined test plan templates.

        Args:
            output (str, optional): Output format (table or json).
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

            # Use shared output function
            def template_table_row(template):
                short_name = template["name"][:40] + ("…" if len(template["name"]) > 40 else "")
                return [template["workspace"], short_name, template["id"]]

            output_list_data(
                template_data,
                output,
                ["Workspace", "Name", "Template ID"],
                template_table_row,
                "No test plan templates found.",
            )
        except Exception as exc:
            handle_api_error(exc)

    @templates.command(name="export")
    @click.option(
        "--id",
        "template_id",
        required=True,
        help="Test plan template ID to export",
    )
    @click.option("--output", required=True, help="Output JSON file")
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
            save_json_file(items[0], output)
            click.echo(f"✓ Test plan template exported to {output}")
        except Exception as exc:
            if "not found" not in str(exc).lower():
                handle_api_error(exc)
            else:
                click.echo(f"✗ Error: {exc}", err=True)
                raise click.ClickException(str(exc))

    @templates.command(name="import")
    @click.option(
        "--file",
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
            make_api_request("POST", url, payload)
            click.echo("✓ Test plan template imported successfully.")
        except Exception as exc:
            handle_api_error(exc)

    @templates.command(name="delete")
    @click.option(
        "--id",
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

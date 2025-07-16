"""CLI commands for managing SystemLink test plan templates."""

import json

import click
import requests

from .utils import get_base_url, get_headers, get_ssl_verify


def register_templates_commands(cli):
    """Register the 'templates' command group and its subcommands."""

    @cli.group()
    def templates():
        """Manage test plan templates."""
        pass

    @templates.command(name="list")
    def list_templates():
        """List available user-defined test plan templates."""
        url = f"{get_base_url()}/niworkorder/v1/query-testplan-templates"
        payload = {
            "take": 1000,
            "orderBy": "TEMPLATE_GROUP",
            "descending": False,
            "projection": ["ID", "NAME", "WORKSPACE"],
        }
        ssl_verify = get_ssl_verify()
        try:
            from .utils import get_workspace_map

            workspace_map = get_workspace_map()
            resp = requests.post(
                url,
                headers=get_headers(),
                json=payload,
                verify=ssl_verify,
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("testPlanTemplates", []) if isinstance(data, dict) else []
            if not items:
                click.echo("No test plan templates found.")
                return
            click.echo(f"{'ID':<12} {'Workspace':<20} {'Name':<30}")
            for item in items:
                ws_guid = item.get("workspace", "")
                ws_name = workspace_map.get(ws_guid, ws_guid)
                click.echo(f"{item.get('id', ''):<12} {ws_name:<20} " f"{item.get('name', ''):<30}")
        except requests.RequestException as exc:
            click.echo(f"Error: {exc}")
            raise click.ClickException(str(exc))

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
        ssl_verify = get_ssl_verify()
        try:
            resp = requests.post(url, headers=get_headers(), json=payload, verify=ssl_verify)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("testPlanTemplates", []) if isinstance(data, dict) else []
            if not items:
                click.echo(f"Test plan template with ID {template_id} not found.")
                raise click.ClickException(f"Test plan template with ID {template_id} not found.")
            with open(output, "w") as file_obj:
                json.dump(items[0], file_obj, indent=2)
            click.echo(f"Test plan template exported to {output}")
        except Exception as exc:
            click.echo(f"Error: {exc}")
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
        ssl_verify = get_ssl_verify()
        try:
            with open(input_file, "r") as file_obj:
                data = json.load(file_obj)
            if isinstance(data, dict) and "testPlanTemplates" in data:
                data = data["testPlanTemplates"]
            elif isinstance(data, dict):
                data = [data]
            filtered = []
            for entry in data:
                filtered.append({k: v for k, v in entry.items() if k in allowed_fields})
            payload = {"testPlanTemplates": filtered}
            resp = requests.post(url, headers=get_headers(), json=payload, verify=ssl_verify)
            resp.raise_for_status()
            click.echo("Test plan template imported successfully.")
        except Exception as exc:
            click.echo(f"Error: {exc}")
            raise click.ClickException(str(exc))

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
        ssl_verify = get_ssl_verify()
        try:
            resp = requests.post(url, headers=get_headers(), json=payload, verify=ssl_verify)
            if resp.status_code in (200, 204):
                click.echo(f"Test plan template {template_id} deleted successfully.")
            else:
                click.echo(f"Failed to delete test plan template {template_id}: " f"{resp.text}")
                raise click.ClickException(
                    f"Failed to delete test plan template {template_id}: " f"{resp.text}"
                )
        except Exception as exc:
            click.echo(f"Error: {exc}")
            raise click.ClickException(str(exc))

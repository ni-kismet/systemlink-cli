"""CLI commands for managing SystemLink-hosted Grafana dashboards."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import click

from .cli_utils import validate_output_format
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_web_url,
    handle_api_error,
    load_json_file,
    make_api_request,
    save_json_file,
)


def _dashboard_api_base() -> str:
    """Return the SystemLink-hosted Grafana API base URL."""
    return f"{get_web_url()}/dashboardhost/api"


def _list_dashboards(search_text: str, take: int) -> List[Dict[str, Any]]:
    """List dashboards from the Grafana search API."""
    query = quote_plus(search_text)
    url = f"{_dashboard_api_base()}/search?type=dash-db&query={query}&limit={take}"
    resp = make_api_request("GET", url, payload=None)
    data = resp.json()
    if isinstance(data, list):
        return [item for item in data if item.get("type") == "dash-db"]
    return []


def _export_dashboard(uid: str) -> Dict[str, Any]:
    """Get dashboard JSON from Grafana by UID."""
    url = f"{_dashboard_api_base()}/dashboards/uid/{uid}"
    resp = make_api_request("GET", url, payload=None)
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected dashboard response format.")
    return data


def _normalize_import_payload(file_data: Dict[str, Any], overwrite: bool) -> Dict[str, Any]:
    """Convert file data into Grafana dashboard import payload format."""
    if "dashboard" in file_data and isinstance(file_data.get("dashboard"), dict):
        payload = dict(file_data)
        payload["overwrite"] = overwrite
        if "message" not in payload:
            payload["message"] = "Imported via slcli"
        return payload

    return {
        "dashboard": file_data,
        "overwrite": overwrite,
        "message": "Imported via slcli",
    }


def register_dashboard_commands(cli: Any) -> None:
    """Register the 'dashboard' command group and its subcommands."""

    @cli.group()
    def dashboard() -> None:
        """Manage SystemLink-hosted dashboards."""
        pass

    @dashboard.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--filter",
        "search_text",
        default="",
        show_default=True,
        help="Search dashboards by title",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of dashboards to return",
    )
    def list_dashboards(format: str = "table", search_text: str = "", take: int = 25) -> None:
        """List dashboards from SystemLink-hosted Grafana."""
        format_output = validate_output_format(format)

        if take <= 0:
            click.echo("✗ --take must be greater than 0", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            dashboards = _list_dashboards(search_text, take)

            if format_output == "json":
                click.echo(json.dumps(dashboards, indent=2))
                return

            if not dashboards:
                click.echo("No dashboards found.")
                return

            from .table_utils import output_formatted_list

            def _row_formatter(item: Dict[str, Any]) -> List[Any]:
                return [
                    item.get("title", ""),
                    item.get("uid", ""),
                    item.get("folderTitle", "General"),
                    item.get("url", ""),
                ]

            output_formatted_list(
                dashboards,
                format_output,
                ["Title", "UID", "Folder", "URL"],
                [36, 24, 20, 50],
                _row_formatter,
                "No dashboards found.",
                "dashboard(s)",
            )
        except Exception as exc:
            handle_api_error(exc)

    @dashboard.command(name="export")
    @click.argument("uid", type=str)
    @click.option(
        "--output",
        "-o",
        type=click.Path(dir_okay=False, path_type=Path),
        help="Output file path (default: <uid>.json)",
    )
    @click.option(
        "--dashboard-only",
        is_flag=True,
        help="Export only the dashboard object (omit Grafana metadata wrapper).",
    )
    def export_dashboard(uid: str, output: Optional[Path], dashboard_only: bool) -> None:
        """Export a dashboard by UID to JSON."""
        try:
            data = _export_dashboard(uid)
            output_path = output or Path(f"{uid}.json")

            if dashboard_only:
                dashboard_obj = data.get("dashboard")
                if not isinstance(dashboard_obj, dict):
                    raise ValueError("Response does not contain a dashboard object.")
                save_json_file(dashboard_obj, str(output_path))
            else:
                save_json_file(data, str(output_path))

            format_success("Dashboard exported", {"uid": uid, "file": str(output_path)})
        except Exception as exc:
            handle_api_error(exc)

    @dashboard.command(name="import")
    @click.option(
        "--file",
        "-i",
        "file_path",
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        help="Dashboard JSON file to import",
    )
    @click.option(
        "--overwrite",
        is_flag=True,
        default=False,
        help="Overwrite existing dashboard with the same UID",
    )
    def import_dashboard(file_path: Path, overwrite: bool) -> None:
        """Import a dashboard JSON file into SystemLink-hosted Grafana."""
        check_readonly_mode("import a dashboard")

        try:
            file_data = load_json_file(str(file_path))
            if not isinstance(file_data, dict):
                click.echo("✗ Dashboard file must contain a JSON object.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            payload = _normalize_import_payload(file_data, overwrite)
            url = f"{_dashboard_api_base()}/dashboards/db"
            resp = make_api_request("POST", url, payload=payload)
            result = resp.json() if resp.content else {}

            imported_uid = payload.get("dashboard", {}).get("uid", "")
            if isinstance(result, dict) and result.get("uid"):
                imported_uid = str(result.get("uid"))

            format_success(
                "Dashboard imported",
                {
                    "uid": imported_uid or "(new)",
                    "status": result.get("status", "ok") if isinstance(result, dict) else "ok",
                },
            )
        except Exception as exc:
            handle_api_error(exc)

"""CLI commands for managing SystemLink states."""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, cast
from urllib.parse import unquote

import click
import questionary
import requests

from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    sanitize_filename,
)
from .workspace_utils import (
    get_effective_workspace,
    get_workspace_display_name,
    resolve_workspace_filter,
)

ARCHITECTURES = ["ARM", "X64", "X86", "ANY"]
DISTRIBUTIONS = ["NI_LINUXRT", "NI_LINUXRT_NXG", "WINDOWS", "ANY"]
DEFAULT_FETCH_BATCH_SIZE = 1000
DETAIL_PREVIEW_LIMIT = 5


def _get_state_service_url() -> str:
    """Return the systems state service base URL."""
    return f"{get_base_url()}/nisystemsstate/v1"


def _response_text(resp: requests.Response) -> str:
    """Return response text when available."""
    text = getattr(resp, "text", None)
    if isinstance(text, str):
        return text

    content = getattr(resp, "content", b"")
    if isinstance(content, bytes):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    return ""


def _response_json(resp: requests.Response) -> Dict[str, Any]:
    """Return parsed JSON for a response, falling back to an empty object."""
    try:
        data = resp.json()
    except Exception:
        return {}

    return data if isinstance(data, dict) else {}


def _exit_with_state_error(
    operation: str,
    status_code: int,
    response_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Exit with a normalized message and exit code for state-service failures."""
    data = response_data or {}
    error = data.get("error", {}) if isinstance(data, dict) else {}

    message = "Unknown error"
    if isinstance(error, dict) and error:
        message = str(error.get("message") or error.get("title") or message)
    elif isinstance(data, dict):
        fallback_message = data.get("message") or data.get("detail") or data.get("title")
        message = str(fallback_message or message)

    click.echo(f"✗ {operation} failed: {message}", err=True)

    inner_errors = error.get("innerErrors", []) if isinstance(error, dict) else []
    if isinstance(inner_errors, list):
        for inner_error in inner_errors:
            if not isinstance(inner_error, dict):
                continue
            inner_message = inner_error.get("message") or inner_error.get("name")
            if inner_message:
                click.echo(f"  - {inner_message}", err=True)

    if status_code == 404:
        sys.exit(ExitCodes.NOT_FOUND)
    if status_code in (400, 409):
        sys.exit(ExitCodes.INVALID_INPUT)
    if status_code in (401, 403):
        sys.exit(ExitCodes.PERMISSION_DENIED)

    sys.exit(ExitCodes.GENERAL_ERROR)


def _handle_http_exception(operation: str, exc: requests.RequestException) -> None:
    """Translate HTTP exceptions into state-service specific CLI errors."""
    response = getattr(exc, "response", None)
    if response is not None:
        _exit_with_state_error(operation, response.status_code, _response_json(response))

    handle_api_error(exc)


def _parse_properties(properties: Sequence[str]) -> Dict[str, str]:
    """Parse repeated KEY=VALUE options into a dictionary."""
    parsed: Dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(f"✗ Invalid property format: {prop}. Use key=value", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        key, value = prop.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            click.echo(f"✗ Invalid property format: {prop}. Use key=value", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        parsed[key] = value
    return parsed


def _load_json_value(value: str, option_name: str) -> Any:
    """Load JSON from an inline string or @file reference."""
    if value.startswith("@"):
        return load_json_file(value[1:])

    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        click.echo(f"✗ Invalid JSON for {option_name}: {exc}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)


def _load_request_payload(request_file: Optional[str], option_name: str) -> Dict[str, Any]:
    """Load a request payload file and ensure it contains an object."""
    if not request_file:
        return {}

    payload = load_json_file(request_file)
    if not isinstance(payload, dict):
        click.echo(f"✗ {option_name} must contain a JSON object.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)
    return payload


def _collect_json_objects(values: Sequence[str], option_name: str) -> List[Dict[str, Any]]:
    """Collect repeated JSON option values into a single flat list of objects."""
    collected: List[Dict[str, Any]] = []
    for value in values:
        parsed = _load_json_value(value, option_name)
        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    click.echo(
                        f"✗ {option_name} entries must be JSON objects or arrays of objects.",
                        err=True,
                    )
                    sys.exit(ExitCodes.INVALID_INPUT)
                collected.append(item)
            continue

        if not isinstance(parsed, dict):
            click.echo(
                f"✗ {option_name} entries must be JSON objects or arrays of objects.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        collected.append(parsed)

    return collected


def _resolve_workspace_id(
    workspace: Optional[str],
    *,
    apply_default: bool = True,
) -> Optional[str]:
    """Resolve a workspace name or ID into a workspace ID."""
    effective = get_effective_workspace(workspace) if apply_default else workspace
    if not effective:
        return None

    try:
        workspace_map = get_workspace_map()
        return resolve_workspace_filter(effective, workspace_map)
    except Exception as exc:
        click.echo(f"✗ Error resolving workspace '{effective}': {exc}", err=True)
        sys.exit(ExitCodes.NOT_FOUND)


def _bool_display(value: Optional[bool], missing: str = "-") -> str:
    """Return a compact bool display value."""
    if value is None:
        return missing
    return "Yes" if value else "No"


def _build_state_payload(
    *,
    request_file: Optional[str],
    name: Optional[str],
    description: Optional[str],
    distribution: Optional[str],
    architecture: Optional[str],
    workspace: Optional[str],
    property_values: Sequence[str],
    feeds: Sequence[str] = (),
    packages: Sequence[str] = (),
    system_image: Optional[str] = None,
    require_core_fields: bool = False,
    apply_default_workspace: bool = True,
) -> Dict[str, Any]:
    """Build a state request payload from CLI options."""
    payload = _load_request_payload(request_file, "--request")

    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if distribution is not None:
        payload["distribution"] = distribution
    if architecture is not None:
        payload["architecture"] = architecture

    request_workspace = payload.get("workspace")
    if workspace is not None:
        workspace_id = _resolve_workspace_id(workspace, apply_default=False)
        if workspace_id is not None:
            payload["workspace"] = workspace_id
    elif request_workspace:
        payload["workspace"] = _resolve_workspace_id(str(request_workspace), apply_default=False)
    elif apply_default_workspace:
        workspace_id = _resolve_workspace_id(workspace, apply_default=True)
        if workspace_id is not None:
            payload["workspace"] = workspace_id

    if property_values:
        payload["properties"] = _parse_properties(property_values)

    if feeds:
        payload["feeds"] = _collect_json_objects(feeds, "--feed")

    if packages:
        payload["packages"] = _collect_json_objects(packages, "--package")

    if system_image is not None:
        parsed_image = _load_json_value(system_image, "--system-image")
        if not isinstance(parsed_image, dict):
            click.echo("✗ --system-image must be a JSON object.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        payload["systemImage"] = parsed_image

    if require_core_fields:
        missing = [
            field for field in ("name", "distribution", "architecture") if not payload.get(field)
        ]
        if missing:
            click.echo(
                f"✗ Missing required state fields: {', '.join(sorted(missing))}",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

    return payload


def _fetch_all_states(
    *,
    workspace: Optional[str],
    architecture: Optional[str],
    distribution: Optional[str],
) -> Dict[str, Any]:
    """Fetch all matching states using API paging."""
    states: List[Dict[str, Any]] = []
    workspace_id = _resolve_workspace_id(workspace, apply_default=True)
    skip = 0
    total_count = 0

    while True:
        params = [f"Skip={skip}", f"Take={DEFAULT_FETCH_BATCH_SIZE}"]
        if workspace_id:
            params.append(f"Workspace={workspace_id}")
        if architecture:
            params.append(f"Architecture={architecture}")
        if distribution:
            params.append(f"Distribution={distribution}")

        url = f"{_get_state_service_url()}/states?{'&'.join(params)}"
        resp = make_api_request("GET", url, payload=None)
        data = resp.json()

        page_states = data.get("states", [])
        total_count = int(data.get("totalCount", len(page_states)))
        states.extend(page_states)

        if len(states) >= total_count or not page_states:
            break

        skip += len(page_states)

    return {"totalCount": total_count, "states": states}


def _fetch_state_history(state_id: str) -> Dict[str, Any]:
    """Fetch the full version history for a state."""
    versions: List[Dict[str, Any]] = []
    skip = 0
    total_count = 0

    while True:
        url = (
            f"{_get_state_service_url()}/states/{state_id}/history"
            f"?skip={skip}&take={DEFAULT_FETCH_BATCH_SIZE}"
        )
        resp = make_api_request("GET", url, payload=None)
        data = resp.json()

        page_versions = data.get("versions", [])
        total_count = int(data.get("totalCount", len(page_versions)))
        versions.extend(page_versions)

        if len(versions) >= total_count or not page_versions:
            break

        skip += len(page_versions)

    return {"totalCount": total_count, "versions": versions}


def _build_state_row_formatter(workspace_map: Dict[str, str]) -> Any:
    """Create a list row formatter for states."""

    def formatter(state: Dict[str, Any]) -> List[str]:
        extra_ops = state.get("containsExtraOperations")
        return [
            str(state.get("name", "")),
            str(state.get("distribution", "")),
            str(state.get("architecture", "")),
            get_workspace_display_name(str(state.get("workspace", "")), workspace_map),
            _bool_display(extra_ops),
            str(state.get("lastUpdatedTimestamp", "")),
            str(state.get("id", "")),
        ]

    return formatter


def _format_preview_items(items: Sequence[Dict[str, Any]], keys: Sequence[str]) -> List[str]:
    """Format a small preview list for detail output."""
    preview_lines: List[str] = []
    for item in items[:DETAIL_PREVIEW_LIMIT]:
        columns = [str(item.get(key, "")) for key in keys if item.get(key) not in (None, "")]
        preview_lines.append("  - " + " | ".join(columns))

    if len(items) > DETAIL_PREVIEW_LIMIT:
        preview_lines.append(f"  - ... {len(items) - DETAIL_PREVIEW_LIMIT} more")

    return preview_lines


def _print_state_detail(state: Dict[str, Any]) -> None:
    """Print a table-style detail view for a state response."""
    workspace_name = get_workspace_display_name(str(state.get("workspace", "")))
    feeds = state.get("feeds") or []
    packages = state.get("packages") or []
    system_image = state.get("systemImage") or {}
    properties = state.get("properties") or {}

    click.echo("State Details")
    click.echo("=" * 50)
    click.echo(f"ID: {state.get('id', '')}")
    click.echo(f"Name: {state.get('name', '')}")
    click.echo(f"Description: {state.get('description', '')}")
    click.echo(f"Distribution: {state.get('distribution', '')}")
    click.echo(f"Architecture: {state.get('architecture', '')}")
    click.echo(f"Workspace: {workspace_name}")
    click.echo(f"Created: {state.get('createdTimestamp', '')}")
    click.echo(f"Updated: {state.get('lastUpdatedTimestamp', '')}")
    click.echo(
        f"Contains Extra Operations: {_bool_display(state.get('containsExtraOperations'), 'No')}"
    )
    click.echo(f"Feeds: {len(feeds)}")
    click.echo(f"Packages: {len(packages)}")

    if isinstance(system_image, dict) and system_image:
        click.echo(
            "System Image: "
            f"{system_image.get('name', '')}"
            f" {system_image.get('version', '')}".rstrip()
        )

    if properties:
        click.echo("Properties:")
        for key in sorted(properties):
            click.echo(f"  {key}: {properties[key]}")

    if isinstance(feeds, list) and feeds:
        click.echo("Feed Preview:")
        for line in _format_preview_items(feeds, ("name", "url")):
            click.echo(line)

    if isinstance(packages, list) and packages:
        click.echo("Package Preview:")
        for line in _format_preview_items(packages, ("name", "version")):
            click.echo(line)


def _build_history_row_formatter() -> Any:
    """Create a list row formatter for state history."""

    def formatter(version: Dict[str, Any]) -> List[str]:
        return [
            str(version.get("version", "")),
            str(version.get("description", "")),
            str(version.get("createdTimestamp", "")),
            str(version.get("userId", "")),
        ]

    return formatter


def _get_download_filename(resp: requests.Response, fallback: str) -> str:
    """Extract a filename from Content-Disposition or use a fallback."""
    headers = getattr(resp, "headers", {})
    header_value = headers.get("Content-Disposition", "") if isinstance(headers, dict) else ""
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", header_value)
    if match:
        server_filename = re.split(r"[\\/]+", unquote(match.group(1)).strip())[-1]
        extension = (
            ".sls" if Path(server_filename).suffix.lower() == ".sls" else Path(fallback).suffix
        )
        safe_stem = sanitize_filename(Path(server_filename).stem, Path(fallback).stem)
        return f"{safe_stem}{extension}"
    return fallback


def _write_binary_response(resp: requests.Response, output_path: Path) -> None:
    """Write binary response content to disk."""
    with output_path.open("wb") as output_file:
        iter_content = getattr(resp, "iter_content", None)
        if callable(iter_content):
            for chunk in cast(Iterable[bytes], iter_content(chunk_size=8192)):
                if chunk:
                    output_file.write(chunk)
            return

        content = getattr(resp, "content", b"")
        output_file.write(content if isinstance(content, bytes) else bytes(content))


def _emit_inline_response(resp: requests.Response) -> None:
    """Write inline response content to stdout."""
    content = getattr(resp, "content", b"")
    if isinstance(content, bytes):
        try:
            click.echo(content.decode("utf-8"), nl=False)
            return
        except UnicodeDecodeError:
            sys.stdout.buffer.write(content)
            return

    click.echo(str(content), nl=False)


def _validate_inline_output_options(output: Optional[str], inline: bool) -> None:
    """Ensure file-download options are not contradictory."""
    if output and inline:
        click.echo("✗ Cannot use --output and --inline together.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)


def register_state_commands(cli: Any) -> None:
    """Register the `state` command group and its subcommands."""

    @cli.group()
    def state() -> None:
        """Manage SystemLink states."""
        pass

    @state.command(name="list")
    @click.option("--workspace", "workspace_name", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--architecture",
        type=click.Choice(ARCHITECTURES),
        help="Filter by architecture compatibility",
    )
    @click.option(
        "--distribution",
        type=click.Choice(DISTRIBUTIONS),
        help="Filter by distribution compatibility",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Number of items per page in table output",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_states(
        workspace_name: Optional[str],
        architecture: Optional[str],
        distribution: Optional[str],
        take: int,
        format_output: str,
    ) -> None:
        """List states."""
        try:
            response_data = _fetch_all_states(
                workspace=workspace_name,
                architecture=architecture,
                distribution=distribution,
            )
            workspace_map = get_workspace_map()
            filtered_resp: Any = FilteredResponse(response_data)
            UniversalResponseHandler.handle_list_response(
                filtered_resp,
                "states",
                "state",
                format_output,
                _build_state_row_formatter(workspace_map),
                ["Name", "Distribution", "Architecture", "Workspace", "Extra Ops", "Updated", "ID"],
                [28, 14, 12, 24, 10, 24, 24],
                "No states found.",
                enable_pagination=True,
                page_size=take,
                total_count=response_data.get("totalCount"),
            )
        except requests.RequestException as exc:
            _handle_http_exception("State list", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="get")
    @click.argument("state_id")
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_state(state_id: str, format_output: str) -> None:
        """Get a state by ID."""
        url = f"{_get_state_service_url()}/states/{state_id}"
        try:
            resp = make_api_request("GET", url, payload=None)
            data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            _print_state_detail(data)
        except requests.RequestException as exc:
            _handle_http_exception("State get", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="create")
    @click.option("--name", required=False, help="State name")
    @click.option("--description", help="State description")
    @click.option(
        "--distribution",
        type=click.Choice(DISTRIBUTIONS),
        help="Supported distribution",
    )
    @click.option(
        "--architecture",
        type=click.Choice(ARCHITECTURES),
        help="Supported architecture",
    )
    @click.option("--workspace", "workspace_name", "-w", help="Workspace name or ID")
    @click.option(
        "--property",
        "property_values",
        multiple=True,
        help="Custom property in key=value format",
    )
    @click.option(
        "--feed",
        "feed_values",
        multiple=True,
        help="Feed JSON object or @file.json (repeatable)",
    )
    @click.option(
        "--package",
        "package_values",
        multiple=True,
        help="Package JSON object or @file.json (repeatable)",
    )
    @click.option(
        "--system-image",
        help="System image JSON object or @file.json",
    )
    @click.option(
        "--request",
        "request_file",
        type=click.Path(exists=True, dir_okay=False),
        help="Raw JSON request file",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def create_state(
        name: Optional[str],
        description: Optional[str],
        distribution: Optional[str],
        architecture: Optional[str],
        workspace_name: Optional[str],
        property_values: Tuple[str, ...],
        feed_values: Tuple[str, ...],
        package_values: Tuple[str, ...],
        system_image: Optional[str],
        request_file: Optional[str],
        format_output: str,
    ) -> None:
        """Create a state from JSON-defined content."""
        check_readonly_mode("create a state")
        payload = _build_state_payload(
            request_file=request_file,
            name=name,
            description=description,
            distribution=distribution,
            architecture=architecture,
            workspace=workspace_name,
            property_values=property_values,
            feeds=feed_values,
            packages=package_values,
            system_image=system_image,
            require_core_fields=True,
        )
        try:
            resp = make_api_request(
                "POST",
                f"{_get_state_service_url()}/states",
                payload=payload,
                handle_errors=False,
            )
            data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            format_success(
                "State created", {"id": data.get("id", ""), "name": data.get("name", "")}
            )
        except requests.RequestException as exc:
            _handle_http_exception("State create", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="update")
    @click.argument("state_id")
    @click.option("--name", help="Updated state name")
    @click.option("--description", help="Updated state description")
    @click.option(
        "--distribution",
        type=click.Choice(DISTRIBUTIONS),
        help="Updated supported distribution",
    )
    @click.option(
        "--architecture",
        type=click.Choice(ARCHITECTURES),
        help="Updated supported architecture",
    )
    @click.option("--workspace", "workspace_name", "-w", help="Workspace name or ID")
    @click.option(
        "--property",
        "property_values",
        multiple=True,
        help="Replace properties with key=value entries",
    )
    @click.option(
        "--request",
        "request_file",
        type=click.Path(exists=True, dir_okay=False),
        help="Raw JSON patch file",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def update_state(
        state_id: str,
        name: Optional[str],
        description: Optional[str],
        distribution: Optional[str],
        architecture: Optional[str],
        workspace_name: Optional[str],
        property_values: Tuple[str, ...],
        request_file: Optional[str],
        format_output: str,
    ) -> None:
        """Update a state."""
        check_readonly_mode("update a state")
        payload = _build_state_payload(
            request_file=request_file,
            name=name,
            description=description,
            distribution=distribution,
            architecture=architecture,
            workspace=workspace_name,
            property_values=property_values,
            apply_default_workspace=False,
        )
        if not payload:
            click.echo("✗ No update fields provided. Specify at least one option.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            resp = make_api_request(
                "PATCH",
                f"{_get_state_service_url()}/states/{state_id}",
                payload=payload,
                handle_errors=False,
            )
            data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            format_success(
                "State updated", {"id": data.get("id", state_id), "name": data.get("name", "")}
            )
        except requests.RequestException as exc:
            _handle_http_exception("State update", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="delete")
    @click.argument("state_id")
    @click.option("--yes", is_flag=True, help="Skip confirmation prompt")
    def delete_state(state_id: str, yes: bool) -> None:
        """Delete a state."""
        check_readonly_mode("delete a state")
        if not yes:
            if not questionary.confirm(
                f"Are you sure you want to delete state '{state_id}'?",
                default=False,
            ).ask():
                raise click.Abort()

        try:
            resp = make_api_request(
                "DELETE",
                f"{_get_state_service_url()}/states/{state_id}",
                payload=None,
                handle_errors=False,
            )
            if resp.status_code != 204:
                _exit_with_state_error("State delete", resp.status_code, _response_json(resp))
            format_success("State deleted", {"id": state_id})
        except requests.RequestException as exc:
            _handle_http_exception("State delete", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="import")
    @click.option("--name", required=True, help="State name")
    @click.option("--description", help="State description")
    @click.option(
        "--distribution",
        required=True,
        type=click.Choice(DISTRIBUTIONS),
        help="Supported distribution",
    )
    @click.option(
        "--architecture",
        required=True,
        type=click.Choice(ARCHITECTURES),
        help="Supported architecture",
    )
    @click.option("--workspace", "workspace_name", "-w", help="Workspace name or ID")
    @click.option(
        "--property",
        "property_values",
        multiple=True,
        help="Custom property in key=value format",
    )
    @click.option(
        "--file",
        "input_file",
        "-i",
        type=click.Path(exists=True, dir_okay=False),
        required=True,
        help="Input .sls file",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def import_state(
        name: str,
        description: Optional[str],
        distribution: str,
        architecture: str,
        workspace_name: Optional[str],
        property_values: Tuple[str, ...],
        input_file: str,
        format_output: str,
    ) -> None:
        """Import a state from an .sls file."""
        check_readonly_mode("import a state")
        workspace_id = _resolve_workspace_id(workspace_name, apply_default=True)
        properties = _parse_properties(property_values) if property_values else {}
        data = {
            "Name": name,
            "Description": description or "",
            "Distribution": distribution,
            "Architecture": architecture,
        }
        if properties:
            data["Properties"] = json.dumps(properties)
        if workspace_id:
            data["Workspace"] = workspace_id

        try:
            with open(input_file, "rb") as file_handle:
                files = {"File": (Path(input_file).name, file_handle, "application/octet-stream")}
                resp = make_api_request(
                    "POST",
                    f"{_get_state_service_url()}/import-state",
                    payload=None,
                    files=files,
                    data=data,
                    handle_errors=False,
                )
            response_data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(response_data, indent=2))
                return
            format_success(
                "State imported",
                {"id": response_data.get("id", ""), "name": response_data.get("name", name)},
            )
        except requests.RequestException as exc:
            _handle_http_exception("State import", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="replace-content")
    @click.argument("state_id")
    @click.option(
        "--file",
        "input_file",
        "-i",
        type=click.Path(exists=True, dir_okay=False),
        required=True,
        help="Replacement .sls file",
    )
    @click.option("--change-description", help="Description of the content change")
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def replace_state_content(
        state_id: str,
        input_file: str,
        change_description: Optional[str],
        format_output: str,
    ) -> None:
        """Replace the .sls content for an existing state."""
        check_readonly_mode("replace state content")
        data = {"Id": state_id}
        if change_description:
            data["ChangeDescription"] = change_description

        try:
            with open(input_file, "rb") as file_handle:
                files = {"File": (Path(input_file).name, file_handle, "application/octet-stream")}
                resp = make_api_request(
                    "POST",
                    f"{_get_state_service_url()}/replace-state-content",
                    payload=None,
                    files=files,
                    data=data,
                    handle_errors=False,
                )
            response_data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(response_data, indent=2))
                return
            format_success(
                "State content replaced",
                {"id": response_data.get("id", state_id), "name": response_data.get("name", "")},
            )
        except requests.RequestException as exc:
            _handle_http_exception("State replace-content", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="export")
    @click.argument("state_id")
    @click.option("--version", help="State version to export")
    @click.option("--inline", is_flag=True, help="Write exported content to stdout")
    @click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output file path")
    def export_state(
        state_id: str,
        version: Optional[str],
        inline: bool,
        output: Optional[str],
    ) -> None:
        """Export a stored state to a portable file."""
        _validate_inline_output_options(output, inline)
        payload: Dict[str, Any] = {"state": {"stateID": state_id}}
        if version:
            payload["state"]["stateVersion"] = version
        if inline:
            payload["inline"] = True

        try:
            resp = make_api_request(
                "POST",
                f"{_get_state_service_url()}/export-state",
                payload=payload,
                handle_errors=False,
                stream=not inline,
            )
            if inline:
                _emit_inline_response(resp)
                return

            fallback_name = f"{sanitize_filename(f'state-{state_id}', 'state-export')}.sls"
            filename = output or _get_download_filename(resp, fallback_name)
            output_path = Path(filename)
            _write_binary_response(resp, output_path)
            format_success("State exported", {"output": str(output_path), "id": state_id})
        except requests.RequestException as exc:
            _handle_http_exception("State export", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="capture")
    @click.argument("system_id")
    @click.option("--inline", is_flag=True, help="Write captured content to stdout")
    @click.option("--output", "-o", type=click.Path(dir_okay=False), help="Output file path")
    def capture_state(system_id: str, inline: bool, output: Optional[str]) -> None:
        """Capture a system state into a portable file."""
        _validate_inline_output_options(output, inline)
        payload: Dict[str, Any] = {"systemID": system_id}
        if inline:
            payload["inline"] = True

        try:
            resp = make_api_request(
                "POST",
                f"{_get_state_service_url()}/export-state-from-system",
                payload=payload,
                handle_errors=False,
                stream=not inline,
            )
            if inline:
                _emit_inline_response(resp)
                return

            fallback_name = f"{sanitize_filename(f'system-{system_id}', 'system-state')}.sls"
            filename = output or _get_download_filename(resp, fallback_name)
            output_path = Path(filename)
            _write_binary_response(resp, output_path)
            format_success("State captured", {"output": str(output_path), "system": system_id})
        except requests.RequestException as exc:
            _handle_http_exception("State capture", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="history")
    @click.argument("state_id")
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Number of items per page in table output",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def state_history(state_id: str, take: int, format_output: str) -> None:
        """List version history for a state."""
        try:
            response_data = _fetch_state_history(state_id)
            filtered_resp: Any = FilteredResponse(response_data)
            UniversalResponseHandler.handle_list_response(
                filtered_resp,
                "versions",
                "version",
                format_output,
                _build_history_row_formatter(),
                ["Version", "Description", "Created", "User ID"],
                [42, 28, 24, 36],
                "No state history found.",
                enable_pagination=True,
                page_size=take,
                total_count=response_data.get("totalCount"),
            )
        except requests.RequestException as exc:
            _handle_http_exception("State history", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="version")
    @click.argument("state_id")
    @click.argument("version")
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_state_version(state_id: str, version: str, format_output: str) -> None:
        """Get a specific historical version of a state."""
        url = f"{_get_state_service_url()}/states/{state_id}/history/{version}"
        try:
            resp = make_api_request("GET", url, payload=None)
            data = resp.json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            _print_state_detail(data)
        except requests.RequestException as exc:
            _handle_http_exception("State version", exc)
        except Exception as exc:
            handle_api_error(exc)

    @state.command(name="revert")
    @click.argument("state_id")
    @click.argument("version")
    @click.option("--yes", is_flag=True, help="Skip confirmation prompt")
    def revert_state(state_id: str, version: str, yes: bool) -> None:
        """Revert a state to a historical version."""
        check_readonly_mode("revert a state")
        if not yes:
            if not questionary.confirm(
                f"Are you sure you want to revert state '{state_id}' to version '{version}'?",
                default=False,
            ).ask():
                raise click.Abort()

        payload = {"id": state_id, "version": version}
        try:
            resp = make_api_request(
                "POST",
                f"{_get_state_service_url()}/revert-state-version",
                payload=payload,
                handle_errors=False,
            )
            if resp.status_code == 204:
                format_success("State reverted", {"id": state_id, "version": version})
                return
            _exit_with_state_error("State revert", resp.status_code, _response_json(resp))
        except requests.RequestException as exc:
            _handle_http_exception("State revert", exc)
        except Exception as exc:
            handle_api_error(exc)

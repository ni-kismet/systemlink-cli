"""CLI commands for managing SystemLink WebAssembly function definitions and executions."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import click
import requests

from .cli_utils import validate_output_format
from .function_templates import (
    download_and_extract_template,
    TEMPLATE_REPO,
    TEMPLATE_BRANCH,
    TEMPLATE_SUBFOLDERS,
)
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import (
    display_api_errors,
    ExitCodes,
    get_base_url,
    get_headers,
    get_ssl_verify,
    get_workspace_id_with_fallback,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
)
from .workspace_utils import get_workspace_display_name, resolve_workspace_filter


def load_env_file() -> Dict[str, str]:
    """Load environment variables from a .env file in the current directory.

    Returns:
        Dictionary of environment variables from .env file
    """
    env_vars = {}
    env_file = Path.cwd() / ".env"

    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip().strip('"').strip("'")
        except Exception:
            # Silently ignore .env file parsing errors
            pass

    return env_vars


def get_function_service_base_url() -> str:
    """Get the unified base URL for Function Management Service (v2).

    The unified service consolidates function definition and execution.

    Returns:
        Base URL (prefix) for the unified Function Management Service (without version suffix)
    """
    env_vars = load_env_file()

    # Prefer explicit FUNCTION_SERVICE_URL
    function_url = env_vars.get("FUNCTION_SERVICE_URL") or os.environ.get("FUNCTION_SERVICE_URL")
    if function_url:
        # Normalize to include /nifunction
        return (
            function_url if function_url.endswith("/nifunction") else f"{function_url}/nifunction"
        )

    # Fallback to global SYSTEMLINK_API_URL (handled by get_base_url)
    base_url = get_base_url()
    return f"{base_url}/nifunction"


def get_unified_v2_base() -> str:
    """Get the versioned root for unified Function Management Service (v2)."""
    return f"{get_function_service_base_url()}/v2"


def _query_all_functions(
    workspace_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    interface_filter: Optional[str] = None,
    custom_filter: Optional[str] = None,
    workspace_map: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Query all function definitions using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID to filter by
        name_filter: Optional name pattern to filter by
        interface_filter: Optional text to search for in the interface property
        custom_filter: Optional custom Dynamic LINQ filter expression
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all function definitions matching the filters
    """
    url = f"{get_unified_v2_base()}/query-functions"
    all_functions = []
    continuation_token = None

    while True:
        # Build payload for the request
        payload: Dict[str, Union[int, str, List[str]]] = {
            "take": 100,  # Use smaller page size for efficient pagination
        }

        # Build filter expression
        filter_parts = []

        if workspace_filter:
            filter_parts.append(f'workspaceId == "{workspace_filter}"')

        if name_filter:
            filter_parts.append(f'name.StartsWith("{name_filter}")')

        if interface_filter:
            filter_parts.append(f'interface.Contains("{interface_filter}")')

        # Always filter for WASM runtime by checking for interface.entrypoint since CLI is WASM-only
        # Functions with interface.entrypoint are WASM functions
        filter_parts.append('interface.entrypoint != null && interface.entrypoint != ""')

        # Add custom filter if provided (this will override automatic filters if both are used)
        if custom_filter:
            if filter_parts:
                # Combine automatic filters with custom filter using AND
                combined_filter = f'({" && ".join(filter_parts)}) && ({custom_filter})'
                payload["filter"] = combined_filter
            else:
                payload["filter"] = custom_filter
        elif filter_parts:
            payload["filter"] = " && ".join(filter_parts)

        # Add continuation token if we have one
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        # Extract functions from this page
        functions = data.get("functions", [])
        all_functions.extend(functions)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_functions


def _query_all_executions(
    workspace_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    function_id_filter: Optional[str] = None,
    workspace_map: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Query all function executions using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID to filter by
        status_filter: Optional execution status to filter by
        function_id_filter: Optional function ID to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all function executions matching the filters
    """
    url = f"{get_unified_v2_base()}/query-executions"
    all_executions = []
    continuation_token = None

    while True:
        # Build payload for the request
        payload: Dict[str, Union[int, str, List[str]]] = {
            "take": 100,  # Use smaller page size for efficient pagination
        }

        # Build filter expression
        filter_parts = []

        if workspace_filter:
            filter_parts.append(f'workspaceId == "{workspace_filter}"')

        if status_filter:
            filter_parts.append(f'status == "{status_filter}"')

        if function_id_filter:
            filter_parts.append(f'functionId == "{function_id_filter}"')

        if filter_parts:
            payload["filter"] = " && ".join(filter_parts)

        # Add continuation token if we have one
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload)
        data = resp.json()

        # Extract executions from this page
        executions = data.get("executions", [])
        all_executions.extend(executions)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_executions


def register_function_commands(cli: Any) -> None:
    """Register the 'function' command group and its subcommands."""

    @cli.group()
    def function():
        """Manage function definitions and executions."""

    pass

    # ------------------------------------------------------------------
    # Initialization (template bootstrap) command
    # ------------------------------------------------------------------

    @function.command(name="init")
    @click.option(
        "--language",
        "-l",
        type=click.Choice(["typescript", "python", "ts", "py"], case_sensitive=False),
        help="Template language (typescript|python). Will prompt if omitted.",
    )
    @click.option(
        "--directory",
        "-d",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        help="Target directory to create or populate (defaults to current working directory)",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Overwrite existing non-empty directory contents.",
    )
    def init_function_template(
        language: Optional[str], directory: Optional[Path], force: bool
    ) -> None:
        """Initialize a local function template (TypeScript Hono or Python HTTP)."""
        try:
            # Prompt for language if not supplied
            if not language:
                language = click.prompt(
                    "Select language",
                    type=click.Choice(["typescript", "python"]),  # type: ignore[arg-type]
                )
            if not language:
                click.echo("✗ Language not specified.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)
            language_norm = language.lower()
            if language_norm in {"ts"}:
                language_norm = "typescript"
            if language_norm in {"py"}:
                language_norm = "python"
            if language_norm not in {"typescript", "python"}:
                click.echo("✗ Unsupported language.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            # Prompt for directory if not supplied
            if directory is None:
                dir_input = click.prompt(
                    "Target directory (leave blank for current directory)",
                    default="",
                    show_default=False,
                )
                if dir_input.strip():
                    directory = Path(dir_input.strip())

            target_dir = directory or Path.cwd()
            if not target_dir.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
            else:
                # If directory is not empty and no force, abort
                if any(target_dir.iterdir()) and not force:
                    click.echo(
                        "✗ Target directory is not empty. Use --force to initialize anyway.",
                        err=True,
                    )
                    sys.exit(ExitCodes.INVALID_INPUT)

            repo = TEMPLATE_REPO
            branch = TEMPLATE_BRANCH
            subfolder = TEMPLATE_SUBFOLDERS[language_norm]
            click.echo(f"Downloading {language_norm} template from {repo}@{branch}:{subfolder} ...")
            download_and_extract_template(language_norm, target_dir)
            click.echo("✓ Template files created.")

            # Print next steps (no automatic install/build)
            click.echo("\nNext steps:")
            rel = target_dir.resolve()
            if language_norm == "typescript":
                click.echo(f"  1. cd {rel}")
                click.echo("  2. npm install")
                click.echo("  3. npm run build")
                click.echo(
                    "  4. Use 'slcli function manage create' to register your compiled dist/main.wasm"
                )
            else:
                click.echo(f"  1. cd {rel}")
                click.echo("  2. (Optional) python -m venv .venv && source .venv/bin/activate")
                click.echo("  3. pip install -r requirements.txt (if provided)")
                click.echo(
                    "  4. Use 'slcli function manage create' to register your function per README"
                )
            sys.exit(ExitCodes.SUCCESS)
        except SystemExit:  # re-raise explicit exits
            raise
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # Function Execution Commands Group
    @function.group(name="execute")
    def execute_group():
        """Execute and manage function executions."""
        pass

    # Function Management Commands Group
    @function.group(name="manage")
    def manage_group():
        """Manage function definitions."""
        pass

    @manage_group.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--name",
        "-n",
        help="Filter by function name (starts with pattern)",
    )
    @click.option(
        "--interface-contains",
        help="Filter by interface content (searches interface property for text)",
    )
    @click.option(
        "--filter",
        help='Custom Dynamic LINQ filter expression for advanced filtering. Examples: name.StartsWith("data") && interface.Contains("entrypoint")',
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of functions to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_functions(
        workspace: Optional[str] = None,
        name: Optional[str] = None,
        interface_contains: Optional[str] = None,
        filter: Optional[str] = None,
        take: int = 25,
        format: str = "table",
    ) -> None:
        """List function definitions."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()

            # Resolve workspace filter to ID if specified
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Use continuation token pagination to get all functions
            all_functions = _query_all_functions(
                workspace_filter=workspace_id,
                name_filter=name,
                interface_filter=interface_contains,
                custom_filter=filter,
                workspace_map=workspace_map,
            )

            # Create a mock response with all data
            resp: Any = FilteredResponse({"functions": all_functions})

            # Use universal response handler with function formatter
            def function_formatter(function: Dict[str, Any]) -> List[str]:
                ws_guid = function.get("workspaceId", "")
                ws_name = get_workspace_display_name(ws_guid, workspace_map)

                # Format timestamps
                created_at = function.get("createdAt", "")
                if created_at:
                    created_at = created_at.split("T")[0]  # Just the date part

                return [
                    function.get("id", ""),
                    function.get("name", ""),
                    function.get("version", ""),
                    ws_name,
                    created_at,
                ]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="functions",
                item_name="function",
                format_output=format_output,
                formatter_func=function_formatter,
                headers=[
                    "ID",
                    "Name",
                    "Version",
                    "Workspace",
                    "Created",
                ],
                column_widths=[36, 30, 10, 20, 12],
                empty_message="No function definitions found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @manage_group.command(name="get")
    @click.option(
        "--id",
        "-i",
        "function_id",
        required=True,
        help="Function ID to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_function(function_id: str, format: str = "table") -> None:
        """Get detailed information about a specific function definition."""
        format_output = validate_output_format(format)
        url = f"{get_unified_v2_base()}/functions/{function_id}"

        try:
            resp = make_api_request("GET", url)
            data = resp.json()

            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(data.get("workspaceId", ""), workspace_map)

            click.echo("Function Definition Details:")
            click.echo("=" * 50)
            click.echo(f"ID:          {data.get('id', 'N/A')}")
            click.echo(f"Name:        {data.get('name', 'N/A')}")
            click.echo(f"Description: {data.get('description', 'N/A')}")
            click.echo(f"Workspace:   {ws_name}")
            click.echo(f"Version:     {data.get('version', 'N/A')}")
            click.echo(f"Runtime:     {data.get('runtime', 'N/A')}")
            click.echo(f"Created At:  {data.get('createdAt', 'N/A')}")
            click.echo(f"Updated At:  {data.get('updatedAt', 'N/A')}")

            interface = data.get("interface")
            if interface:
                # New-style interface (HTTP-like) with endpoints summary
                endpoints = interface.get("endpoints")
                if endpoints and isinstance(endpoints, list):
                    click.echo("\nInterface:")
                    default_path = interface.get("defaultPath")
                    if default_path:
                        click.echo(f"Default Path:  {default_path}")
                    click.echo("Endpoints:")
                    for ep in endpoints:
                        methods = (
                            ",".join(ep.get("methods", [])).upper() if ep.get("methods") else "*"
                        )
                        path = ep.get("path", "")
                        desc = ep.get("description", "")
                        click.echo(f"  - {methods} {path} - {desc}")
                # Legacy-style interface fields
                if interface.get("entrypoint"):
                    click.echo(f"Entrypoint:  {interface['entrypoint']}")
                if interface.get("parameters"):
                    click.echo("\nParameters Schema:")
                    click.echo(json.dumps(interface["parameters"], indent=2))
                if interface.get("returns"):
                    click.echo("\nReturns Schema:")
                    click.echo(json.dumps(interface["returns"], indent=2))
            else:
                if data.get("entrypoint"):
                    click.echo(f"Entrypoint:  {data['entrypoint']}")
                if data.get("parameters"):
                    click.echo("\nParameters Schema:")
                    click.echo(json.dumps(data["parameters"], indent=2))
                if data.get("returns"):
                    click.echo("\nReturns Schema:")
                    click.echo(json.dumps(data["returns"], indent=2))

            if data.get("properties"):
                click.echo("\nCustom Properties:")
                for key, value in data["properties"].items():
                    click.echo(f"  {key}: {value}")
        except Exception as exc:
            handle_api_error(exc)

    @manage_group.command(name="create")
    @click.option(
        "--name",
        "-n",
        required=True,
        help="Function display name",
    )
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (default: 'Default')",
    )
    @click.option(
        "--runtime",
        "-r",
        default="wasm",
        type=click.Choice(["wasm"], case_sensitive=False),
        help="Runtime environment for the function (WebAssembly)",
    )
    @click.option(
        "--description",
        "-d",
        help="Function description",
    )
    @click.option(
        "--version",
        "-v",
        default="1.0.0",
        show_default=True,
        help="Function version",
    )
    @click.option(
        "--entrypoint",
        "-e",
        help="WASM file name without extension (stored in interface.entrypoint)",
    )
    @click.option(
        "--content",
        "-c",
        help="Function source code content or file path",
    )
    @click.option(
        "--parameters-schema",
        "-p",
        help="JSON schema for function parameters (stored in interface.parameters) (JSON string or file path)",
    )
    @click.option(
        "--returns-schema",
        help="JSON schema for function return value (stored in interface.returns) (JSON string or file path)",
    )
    @click.option(
        "--properties",
        help='Custom properties as JSON string for metadata and filtering (e.g., \'{"category": "processing", "team": "data-science"}\')',
    )
    def create_function(
        name: str,
        workspace: str = "Default",
        runtime: str = "wasm",
        description: Optional[str] = None,
        version: str = "1.0.0",
        entrypoint: Optional[str] = None,
        content: Optional[str] = None,
        parameters_schema: Optional[str] = None,
        returns_schema: Optional[str] = None,
        properties: Optional[str] = None,
    ) -> None:
        """Create a new function definition with metadata for efficient querying."""
        url = f"{get_unified_v2_base()}/functions"
        try:
            workspace_id = get_workspace_id_with_fallback(workspace)

            custom_properties: Dict[str, Any] = {}
            if properties:
                try:
                    custom_properties.update(json.loads(properties))
                except json.JSONDecodeError:
                    click.echo("✗ Error: Invalid JSON in --properties option", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            params_schema = None
            if parameters_schema:
                try:
                    params_schema = (
                        json.loads(parameters_schema)
                        if parameters_schema.startswith("{")
                        else load_json_file(parameters_schema)
                    )
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error loading parameters schema: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            ret_schema = None
            if returns_schema:
                try:
                    ret_schema = (
                        json.loads(returns_schema)
                        if returns_schema.startswith("{")
                        else load_json_file(returns_schema)
                    )
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error loading returns schema: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            if not entrypoint and content and Path(content).exists():
                entrypoint = Path(content).stem

            interface_obj: Optional[Dict[str, Any]] = None
            if entrypoint or params_schema or ret_schema:
                interface_obj = {}
                if entrypoint:
                    interface_obj["entrypoint"] = entrypoint
                if params_schema:
                    interface_obj["parameters"] = params_schema
                if ret_schema:
                    interface_obj["returns"] = ret_schema

            if content:
                if Path(content).exists():
                    try:
                        with open(content, "rb") as f:
                            content_data = f.read()
                    except Exception as e:  # noqa: BLE001
                        click.echo(f"✗ Error reading content file: {e}", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                else:
                    content_data = content.encode("utf-8")

                function_metadata: Dict[str, Any] = {
                    "name": name,
                    "workspaceId": workspace_id,
                    "runtime": runtime.lower(),
                    "version": version,
                }
                if description:
                    function_metadata["description"] = description
                if interface_obj:
                    function_metadata["interface"] = interface_obj
                if custom_properties:
                    function_metadata["properties"] = custom_properties

                files = {
                    "metadata": (None, json.dumps(function_metadata), "application/json"),
                    "content": ("function_content", content_data, "application/octet-stream"),
                }
                resp = requests.post(
                    url,
                    files=files,
                    headers=get_headers(""),
                    verify=get_ssl_verify(),
                )
                resp.raise_for_status()
            else:
                function_request: Dict[str, Any] = {
                    "name": name,
                    "workspaceId": workspace_id,
                    "runtime": runtime.lower(),
                    "version": version,
                }
                if description:
                    function_request["description"] = description
                if interface_obj:
                    function_request["interface"] = interface_obj
                if custom_properties:
                    function_request["properties"] = custom_properties
                resp = make_api_request("POST", url, function_request)

            response_data = resp.json()
            click.echo(
                f"✓ Function definition created successfully with ID: {response_data.get('id', '')}"
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @manage_group.command(name="update")
    @click.option(
        "--id",
        "-i",
        "function_id",
        required=True,
        help="Function ID to update",
    )
    @click.option(
        "--name",
        "-n",
        help="Updated function display name",
    )
    @click.option(
        "--description",
        "-d",
        help="Updated function description",
    )
    @click.option(
        "--version",
        "-v",
        help="Updated function version",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Updated workspace for the function (name or ID)",
    )
    @click.option(
        "--runtime",
        help="Updated runtime environment (default: wasm)",
        default="wasm",
    )
    @click.option(
        "--entrypoint",
        "-e",
        help="Updated WASM file name without extension (stored in interface.entrypoint)",
    )
    @click.option(
        "--content",
        "-c",
        help="Updated function source code content or file path",
    )
    @click.option(
        "--parameters-schema",
        "-p",
        help="Updated JSON schema for function parameters (stored in interface.parameters) (JSON string or file path)",
    )
    @click.option(
        "--returns-schema",
        help="Updated JSON schema for function return value (stored in interface.returns) (JSON string or file path)",
    )
    @click.option(
        "--properties",
        help="Updated custom properties as JSON string for metadata and filtering (replaces existing properties)",
    )
    def update_function(
        function_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        version: Optional[str] = None,
        workspace: Optional[str] = None,
        runtime: str = "wasm",
        entrypoint: Optional[str] = None,
        content: Optional[str] = None,
        parameters_schema: Optional[str] = None,
        returns_schema: Optional[str] = None,
        properties: Optional[str] = None,
    ) -> None:
        """Update an existing function definition."""
        url = f"{get_unified_v2_base()}/functions/{function_id}"
        try:
            existing_function = make_api_request("GET", url).json()
        except Exception as e:  # noqa: BLE001
            click.echo(f"✗ Error fetching existing function: {e}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        try:
            workspace_id = existing_function.get("workspaceId")
            if workspace:
                try:
                    workspace_id = get_workspace_id_with_fallback(workspace)
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error resolving workspace '{workspace}': {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            params_schema = None
            if parameters_schema:
                try:
                    params_schema = (
                        json.loads(parameters_schema)
                        if parameters_schema.startswith("{")
                        else load_json_file(parameters_schema)
                    )
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error loading parameters schema: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            ret_schema = None
            if returns_schema:
                try:
                    ret_schema = (
                        json.loads(returns_schema)
                        if returns_schema.startswith("{")
                        else load_json_file(returns_schema)
                    )
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error loading returns schema: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            interface_obj = (
                existing_function.get("interface", {}).copy()
                if existing_function.get("interface")
                else {}
            )
            if entrypoint is not None:
                interface_obj["entrypoint"] = entrypoint
            if params_schema is not None:
                interface_obj["parameters"] = params_schema
            if ret_schema is not None:
                interface_obj["returns"] = ret_schema

            custom_properties = None
            if properties:
                try:
                    custom_properties = json.loads(properties)
                except json.JSONDecodeError:
                    click.echo("✗ Error: Invalid JSON in --properties option", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            if (
                name is None
                and description is None
                and version is None
                and workspace is None
                and entrypoint is None
                and content is None
                and parameters_schema is None
                and returns_schema is None
                and properties is None
            ):
                click.echo(
                    "✗ No updates provided. Please specify at least one field to update.", err=True
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            function_metadata: Dict[str, Any] = {
                "name": name if name is not None else existing_function["name"],
                "workspaceId": workspace_id,
                "runtime": runtime,
            }
            if description is not None:
                function_metadata["description"] = description
            elif existing_function.get("description") is not None:
                function_metadata["description"] = existing_function["description"]
            if version is not None:
                function_metadata["version"] = version
            elif existing_function.get("version"):
                function_metadata["version"] = existing_function["version"]
            if interface_obj:
                function_metadata["interface"] = interface_obj
            if custom_properties is not None:
                function_metadata["properties"] = custom_properties
            elif existing_function.get("properties"):
                function_metadata["properties"] = existing_function["properties"]

            content_data = None
            if content:
                if Path(content).exists():
                    try:
                        with open(content, "rb") as f:
                            content_data = f.read()
                    except Exception as e:  # noqa: BLE001
                        click.echo(f"✗ Error reading content file: {e}", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                else:
                    content_data = content.encode("utf-8")

            files: Dict[str, Any] = {
                "metadata": (None, json.dumps(function_metadata), "application/json"),
            }
            if content_data is not None:
                files["content"] = ("function_content", content_data, "application/octet-stream")

            resp = requests.put(
                url,
                files=files,
                headers=get_headers(""),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            click.echo("✓ Function definition updated successfully")
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @manage_group.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "function_id",
        required=True,
        help="Function ID to delete",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Skip confirmation prompt",
    )
    def delete_function(function_id: str, force: bool = False) -> None:
        """Delete a function definition."""
        url = f"{get_unified_v2_base()}/functions/{function_id}"
        try:
            if not force and not click.confirm(
                f"Are you sure you want to delete function {function_id}?"
            ):
                click.echo("Function deletion cancelled.")
                return
            resp = make_api_request("DELETE", url, handle_errors=False)
            if resp.status_code == 204:
                click.echo(f"✓ Function {function_id} deleted successfully.")
            else:
                response_data = resp.json() if resp.text.strip() else {}
                display_api_errors("Function deletion failed", response_data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @manage_group.command(name="download-content")
    @click.option(
        "--id",
        "-i",
        "function_id",
        required=True,
        help="Function ID to download content from",
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (defaults to function_<id> with appropriate extension)",
    )
    def download_function_content(function_id: str, output: Optional[str] = None) -> None:
        """Download function source code content."""
        url = f"{get_unified_v2_base()}/functions/{function_id}/content"
        try:
            resp = make_api_request("GET", url, handle_errors=False)
            if resp.status_code != 200:
                response_data = resp.json() if resp.text.strip() else {}
                display_api_errors("Function content download failed", response_data, detailed=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

            if not output:
                try:
                    meta_data = make_api_request(
                        "GET", f"{get_unified_v2_base()}/functions/{function_id}"
                    ).json()
                    runtime = meta_data.get("runtime", "").lower()
                    ext = {"wasm": ".wasm"}.get(runtime, ".wasm")
                    output = f"function_{function_id}{ext}"
                except Exception:  # noqa: BLE001
                    output = f"function_{function_id}.wasm"

            with open(output, "wb") as f:
                f.write(resp.content)
            click.echo(f"✓ Function content downloaded to '{output}' ({len(resp.content)} bytes)")
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # Function Execution Management Commands
    @execute_group.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--status",
        "-s",
        type=click.Choice(
            ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMEOUT"],
            case_sensitive=False,
        ),
        help="Filter by execution status",
    )
    @click.option(
        "--function-id",
        "-f",
        help="Filter by function ID",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of executions to return",
    )
    @click.option(
        "--format",
        "-fmt",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_executions(
        workspace: Optional[str] = None,
        status: Optional[str] = None,
        function_id: Optional[str] = None,
        take: int = 25,
        format: str = "table",
    ) -> None:
        """List function executions."""
        format_output = validate_output_format(format)

        try:
            workspace_map = get_workspace_map()

            # Resolve workspace filter to ID if specified
            workspace_id = None
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Normalize status to uppercase if provided
            status_filter = status.upper() if status else None

            # Use continuation token pagination to get all executions
            all_executions = _query_all_executions(
                workspace_id, status_filter, function_id, workspace_map
            )

            # Create a mock response with all data
            resp: Any = FilteredResponse({"executions": all_executions})

            # Use universal response handler with execution formatter
            def execution_formatter(execution: Dict[str, Any]) -> List[str]:
                ws_guid = execution.get("workspaceId", "")
                ws_name = get_workspace_display_name(ws_guid, workspace_map)

                # Format timestamps
                queued_at = execution.get("queuedAt", "")
                if queued_at:
                    queued_at = queued_at.split("T")[0]  # Just the date part

                return [
                    execution.get("id", ""),  # Full ID
                    execution.get("functionId", ""),  # Full function ID
                    ws_name,
                    execution.get("status", "UNKNOWN"),
                    queued_at,
                ]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="executions",
                item_name="execution",
                format_output=format_output,
                formatter_func=execution_formatter,
                headers=["ID", "Function ID", "Workspace", "Status", "Queued"],
                column_widths=[36, 36, 20, 12, 12],
                empty_message="No function executions found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @execute_group.command(name="get")
    @click.option(
        "--id",
        "-i",
        "execution_id",
        required=True,
        help="Execution ID to retrieve",
    )
    @click.option(
        "--format",
        "-fmt",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_execution(execution_id: str, format: str = "table") -> None:
        """Get detailed information about a specific function execution."""
        format_output = validate_output_format(format)
        url = f"{get_unified_v2_base()}/executions/{execution_id}"
        try:
            data = make_api_request("GET", url).json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(data.get("workspaceId", ""), workspace_map)
            click.echo("Function Execution Details:")
            click.echo("=" * 50)
            click.echo(f"ID:               {data.get('id', 'N/A')}")
            click.echo(f"Function ID:      {data.get('functionId', 'N/A')}")
            click.echo(f"Workspace:        {ws_name}")
            click.echo(f"Status:           {data.get('status', 'N/A')}")
            click.echo(f"Timeout:          {data.get('timeout', 'N/A')} seconds")
            click.echo(f"Retry Count:      {data.get('retryCount', 0)}")
            click.echo(f"Cached Result:    {data.get('cachedResult', False)}")
            click.echo(f"Queued At:        {data.get('queuedAt', 'N/A')}")
            click.echo(f"Started At:       {data.get('startedAt', 'N/A')}")
            click.echo(f"Completed At:     {data.get('completedAt', 'N/A')}")
            if data.get("parameters"):
                click.echo("\nParameters:")
                click.echo(json.dumps(data["parameters"], indent=2))
            if data.get("result"):
                click.echo("\nResult:")
                click.echo(json.dumps(data["result"], indent=2))
            if data.get("errorMessage"):
                click.echo("\nError Message:")
                click.echo(data["errorMessage"])
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @execute_group.command(name="sync")
    @click.option(
        "--function-id",
        "-f",
        required=True,
        help="Function ID to execute synchronously",
    )
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (default: 'Default')",
    )
    @click.option(
        "--parameters",
        "-p",
        help="Raw JSON (string or file) for advanced parameters object (overrides --method/--path/--header/--body).",
    )
    @click.option(
        "--method",
        default="POST",
        show_default=True,
        help="Invocation HTTP method placed in parameters.method (ignored if --parameters used).",
    )
    @click.option(
        "--path",
        default="/invoke",
        show_default=True,
        help="Invocation path placed in parameters.path (ignored if --parameters used).",
    )
    @click.option(
        "--header",
        "-H",
        multiple=True,
        help="Request header key=value (can repeat). Ignored if --parameters used.",
    )
    @click.option(
        "--body",
        help="JSON string or file for request body placed in parameters.body (ignored if --parameters used).",
    )
    @click.option(
        "--timeout",
        "-t",
        type=int,
        default=300,
        show_default=True,
        help="Execution timeout in seconds (0 for infinite, maximum 3600 for synchronous execution)",
    )
    @click.option(
        "--client-request-id",
        help="Client-provided unique identifier for tracking",
    )
    @click.option(
        "--format",
        "-fmt",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def execute_function(
        function_id: str,
        workspace: str = "Default",
        parameters: Optional[str] = None,
        method: str = "POST",
        path: str = "/invoke",
        header: Optional[tuple] = None,
        body: Optional[str] = None,
        timeout: int = 300,
        client_request_id: Optional[str] = None,
        format: str = "table",
    ) -> None:
        """Execute a function synchronously and return the result.

        This sends a single request and waits for completion (no async polling).
        """
        format_output = validate_output_format(format)
        url = f"{get_unified_v2_base()}/functions/{function_id}/execute"
        try:
            execution_parameters: Dict[str, Any] = {}
            if parameters:
                try:
                    execution_parameters = (
                        json.loads(parameters)
                        if parameters.strip().startswith("{")
                        else load_json_file(parameters)
                    )
                except Exception as e:  # noqa: BLE001
                    click.echo(f"✗ Error parsing parameters: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)
                legacy_keys = {"method", "path", "headers", "body"}
                if not any(k in execution_parameters for k in legacy_keys):
                    execution_parameters = {"body": execution_parameters}
            else:
                # Determine if user explicitly set any of the four HTTP-related flags.
                # We treat them as specified only if they differ from defaults or were
                # provided via the parameters option.
                user_provided_any = (
                    bool(header)
                    or body is not None
                    or (method.upper() != "POST" or path != "/invoke")
                )
                if not user_provided_any:
                    # Pure omission: apply fallback default GET /
                    execution_parameters = {"method": "GET", "path": "/"}
                else:
                    headers_dict: Dict[str, str] = {}
                    if header:
                        for h in header:
                            if "=" not in h:
                                click.echo(
                                    f"✗ Invalid header format (expected key=value): {h}",
                                    err=True,
                                )
                                sys.exit(ExitCodes.INVALID_INPUT)
                            k, v = h.split("=", 1)
                            headers_dict[k.strip()] = v.strip()
                    body_value: Any = None
                    if body:
                        try:
                            body_value = (
                                json.loads(body)
                                if body.strip().startswith("{") or body.strip().startswith("[")
                                else load_json_file(body)
                            )
                        except Exception:
                            body_value = body
                    norm_path = path if path.startswith("/") else f"/{path}"
                    execution_parameters = {
                        "method": method.upper(),
                        "path": norm_path,
                    }
                    if headers_dict:
                        execution_parameters["headers"] = headers_dict
                    if body_value is not None:
                        execution_parameters["body"] = body_value
            if timeout > 3600:
                click.echo(
                    "✗ Timeout cannot exceed 3600 seconds (1 hour) for synchronous execution",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            execute_request: Dict[str, Any] = {
                "parameters": execution_parameters,
                "timeout": timeout,
                "async": False,
            }
            if client_request_id:
                execute_request["clientRequestId"] = client_request_id
            response_data = make_api_request("POST", url, execute_request).json()
            if format_output == "json":
                click.echo(json.dumps(response_data, indent=2))
                return
            click.echo("Function Execution Completed:")
            click.echo("=" * 50)
            click.echo(f"Execution ID:     {response_data.get('executionId', 'N/A')}")
            click.echo(f"Execution Time:   {response_data.get('executionTime', 0)} ms")
            click.echo(f"Cached Result:    {response_data.get('cachedResult', False)}")
            result = response_data.get("result")
            if result is not None:
                click.echo("\nResult:")
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo("\nResult:           None (no return value)")
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @execute_group.command(name="cancel")
    @click.option(
        "--id",
        "-i",
        "execution_ids",
        multiple=True,
        required=True,
        help="Execution ID(s) to cancel (can be specified multiple times)",
    )
    def cancel_executions(execution_ids: tuple) -> None:
        """Cancel one or more function executions."""
        url = f"{get_unified_v2_base()}/executions/cancel"
        payload = {"ids": list(execution_ids)}
        try:
            resp = make_api_request("POST", url, payload, handle_errors=False)
            if resp.status_code == 204:
                if len(execution_ids) == 1:
                    click.echo(f"✓ Execution {execution_ids[0]} cancelled successfully.")
                else:
                    click.echo(f"✓ All {len(execution_ids)} executions cancelled successfully.")
                return
            if resp.status_code == 200:
                data = resp.json()
                cancelled = data.get("cancelled", [])
                failed = data.get("failed", [])
                if cancelled:
                    if len(cancelled) == 1:
                        click.echo(f"✓ Execution {cancelled[0]} cancelled successfully.")
                    else:
                        click.echo(f"✓ {len(cancelled)} executions cancelled successfully:")
                        for eid in cancelled:
                            click.echo(f"  - {eid}")
                if failed:
                    click.echo(f"✗ Failed to cancel {len(failed)} execution(s):", err=True)
                    for failure in failed:
                        eid = failure.get("id", "unknown")
                        err_msg = failure.get("error", {}).get("message", "Unknown error")
                        click.echo(f"  - {eid}: {err_msg}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)
                return
            response_data = resp.json() if resp.text.strip() else {}
            display_api_errors(
                "Function execution cancellation failed", response_data, detailed=True
            )
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @execute_group.command(name="retry")
    @click.option(
        "--id",
        "-i",
        "execution_ids",
        multiple=True,
        required=True,
        help="Execution ID(s) to retry (can be specified multiple times)",
    )
    def retry_executions(execution_ids: tuple) -> None:
        """Retry one or more failed function executions."""
        url = f"{get_unified_v2_base()}/executions/retry"
        payload = {"ids": list(execution_ids)}
        try:
            resp = make_api_request("POST", url, payload, handle_errors=False)
            if resp.status_code in (200, 201):
                data = resp.json()
                executions = data.get("executions", [])
                failed = data.get("failed", [])
                if executions:
                    click.echo(f"✓ {len(executions)} retry executions created successfully:")
                    for execution in executions:
                        click.echo(f"  - New execution: {execution.get('id', '')}")
                if failed:
                    click.echo(f"✗ Failed to retry {len(failed)} execution(s):", err=True)
                    for failure in failed:
                        eid = failure.get("id", "unknown")
                        err_msg = failure.get("error", {}).get("message", "Unknown error")
                        click.echo(f"  - {eid}: {err_msg}", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)
                return
            response_data = resp.json() if resp.text.strip() else {}
            display_api_errors("Function execution retry failed", response_data, detailed=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

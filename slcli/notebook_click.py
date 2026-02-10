"""CLI commands for managing SystemLink notebooks via the SystemLink Notebook API.

Provides CLI commands for listing, creating, updating, downloading, and deleting Jupyter notebooks.
All commands use Click for robust CLI interfaces and error handling.
"""

import datetime
import json
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import click
import requests

from .cli_utils import validate_output_format
from .platform import PLATFORM_SLS, get_platform
from .universal_handlers import UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    make_api_request,
    get_base_url,
    get_headers,
    get_ssl_verify,
    get_workspace_id_with_fallback,
    get_workspace_map,
    handle_api_error,
    save_json_file,
    validate_workspace_access,
)
from .workspace_utils import get_workspace_display_name


# Predefined notebook interfaces - must be assigned exactly as shown
PREDEFINED_NOTEBOOK_INTERFACES = [
    "Assets Grid",
    "Data Table Analysis",
    "Data Space Analysis",
    "File Analysis",
    "Periodic Execution",
    "Resource Changed Routine",
    "Specification Analysis",
    "Systems Grid",
    "Test Data Analysis",
    "Test Data Extraction",
    "Work Item Automations",
    "Work Item Operations",
    "Work Item Scheduler",
]


def _normalize_sls_notebook(notebook: Dict[str, Any]) -> None:
    """Normalize SLS notebook response to include id/name fields.

    SLS notebooks use 'path' as the identifier. This helper adds 'id' and 'name'
    fields derived from 'path' to provide a consistent interface across platforms.

    Args:
        notebook: Notebook dictionary to normalize (modified in place).
    """
    if "path" in notebook:
        if "id" not in notebook:
            notebook["id"] = notebook["path"]
        if "name" not in notebook:
            path = notebook["path"]
            notebook["name"] = path.split("/")[-1] if "/" in path else path


def _get_notebook_base_url() -> str:
    """Get the base URL for notebook API.

    Returns platform-specific URL:
    - SLS (SystemLink Server): /ninbexec/v2 (notebooks by path)
    - SLE (SystemLink Enterprise): /ninotebook/v1 (notebooks by ID)
    """
    if get_platform() == PLATFORM_SLS:
        return f"{get_base_url()}/ninbexec/v2"
    return f"{get_base_url()}/ninotebook/v1"


def _query_notebooks_http(
    filter_str: Optional[str] = None, take: int = 1000
) -> List[Dict[str, Any]]:
    """Query notebooks using continuation token pagination for better performance."""
    base_url = _get_notebook_base_url()
    headers = get_headers("application/json")
    is_sls = get_platform() == PLATFORM_SLS

    all_notebooks = []
    continuation_token = None

    while True:
        # Build payload for the request
        payload: Dict[str, Any] = {"take": 100}  # Use consistent page size for efficient pagination
        if filter_str:
            payload["filter"] = filter_str
        if continuation_token:
            payload["continuationToken"] = continuation_token

        try:
            # SLS uses /query-notebooks, SLE uses /notebook/query
            if is_sls:
                url = f"{base_url}/query-notebooks"
            else:
                url = f"{base_url}/notebook/query"

            response = requests.post(url, headers=headers, json=payload, verify=get_ssl_verify())
            response.raise_for_status()

            data = response.json()
            raw_notebooks = data.get("notebooks", [])  # API returns "notebooks" array

            # Handle invalid parameters gracefully and add notebooks to results
            for nb in raw_notebooks:
                try:
                    # Fix parameters field if it's a list instead of dict
                    if "parameters" in nb and isinstance(nb["parameters"], list):
                        nb["parameters"] = {
                            f"param_{i}": param for i, param in enumerate(nb["parameters"])
                        }
                    elif "parameters" not in nb or not isinstance(nb["parameters"], dict):
                        nb["parameters"] = {}

                    # For SLS, normalize to include id/name derived from path
                    if is_sls:
                        _normalize_sls_notebook(nb)

                    all_notebooks.append(nb)
                except Exception:
                    # Skip notebooks with severe data issues
                    continue

            # Check if there are more pages
            continuation_token = data.get("continuationToken")
            if not continuation_token:
                break

        except requests.exceptions.RequestException as exc:
            raise Exception(f"HTTP request failed: {exc}")
        except Exception as exc:
            raise Exception(f"Failed to query notebooks: {exc}")

    return all_notebooks


def _get_notebook_http(notebook_id: str) -> Dict[str, Any]:
    """Get a single notebook by ID (SLE) or path (SLS) using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers("application/json")
    is_sls = get_platform() == PLATFORM_SLS

    try:
        if is_sls:
            # SLS uses path-based endpoint: /v2/notebooks/{path}
            # The notebook_id is actually a path for SLS
            # Path must be fully URL-encoded (with safe='' to encode all characters including /)
            encoded_path = urllib.parse.quote(notebook_id, safe="")
            url = f"{base_url}/notebooks/{encoded_path}"
        else:
            # SLE uses ID-based endpoint: /notebook/{id}
            url = f"{base_url}/notebook/{notebook_id}"

        response = requests.get(url, headers=headers, verify=get_ssl_verify())
        response.raise_for_status()
        result = response.json()

        # For SLS, normalize the response to include id/name fields
        if is_sls:
            _normalize_sls_notebook(result)

        return result
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


def _get_notebook_content_http(notebook_id: str) -> bytes:
    """Get notebook content by ID (SLE) or path (SLS) using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers()  # No content-type for binary content
    is_sls = get_platform() == PLATFORM_SLS

    try:
        if is_sls:
            # SLS uses path-based endpoint: /v2/notebooks/{path}/data
            # Path must be fully URL-encoded (with safe='' to encode all characters including /)
            encoded_path = urllib.parse.quote(notebook_id, safe="")
            url = f"{base_url}/notebooks/{encoded_path}/data"
        else:
            # SLE uses ID-based endpoint: /notebook/{id}/content
            url = f"{base_url}/notebook/{notebook_id}/content"

        response = requests.get(url, headers=headers, verify=get_ssl_verify())
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


# ------------------------------------------------------------------
# Notebook Execution Service helpers (module-scope for test patching)
# ------------------------------------------------------------------
def _get_notebook_execution_base() -> str:
    """Get the base URL for notebook execution API.

    Returns platform-specific URL:
    - SLS (SystemLink Server): /ninbexec/v2
    - SLE (SystemLink Enterprise): /ninbexecution/v1
    """
    if get_platform() == PLATFORM_SLS:
        return f"{get_base_url()}/ninbexec/v2"
    return f"{get_base_url()}/ninbexecution/v1"


def _query_notebook_executions(
    workspace_id: Optional[str] = None,
    status: Optional[str] = None,
    notebook_id: Optional[str] = None,
    notebook_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Query all notebook executions via POST /query-executions with pagination.

    Args:
        workspace_id: Optional workspace GUID filter (SLE only).
        status: Optional already-mapped service status token (e.g. TIMEDOUT).
        notebook_id: Optional notebook ID filter (SLE only).
        notebook_path: Optional notebook path filter (SLS only).

    Returns:
        List of execution dictionaries.
    """
    base = _get_notebook_execution_base()
    url = f"{base}/query-executions"
    all_execs: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None
    is_sls = get_platform() == PLATFORM_SLS

    def _escape_filter_value(value: str) -> str:
        """Escape special characters in filter string values."""
        # Escape backslashes and quotes to prevent filter injection
        return value.replace("\\", "\\\\").replace('"', '\\"')

    # Build filter based on platform
    base_parts: List[str] = []
    if is_sls:
        # SLS uses notebookPath, no workspaceId
        if notebook_path:
            base_parts.append(f'notebookPath == "{_escape_filter_value(notebook_path)}"')
    else:
        # SLE uses workspaceId and notebookId
        if workspace_id:
            base_parts.append(f'workspaceId == "{_escape_filter_value(workspace_id)}"')
        if notebook_id:
            base_parts.append(f'notebookId == "{_escape_filter_value(notebook_id)}"')

    while True:
        payload: Dict[str, Any] = {
            "take": 100,
            "orderBy": "QUEUED_AT",
            "descending": True,
        }

        # SLS does not support projection, only SLE does
        if not is_sls:
            # SLE uses notebookId and workspaceId projection
            projection = (
                "new(id, notebookId, workspaceId, userId, status, queuedAt, startedAt, "
                "completedAt, source, resourceProfile, errorCode, lastUpdatedBy, retryCount)"
            )
            payload["projection"] = projection

        filters_local = list(base_parts)
        if status:
            filters_local.append(f'status = "{status}"')
        if filters_local:
            payload["filter"] = " && ".join(filters_local)
        if continuation_token:
            payload["continuationToken"] = continuation_token
        resp = make_api_request("POST", url, payload)
        data = resp.json() if resp.text else {}
        if isinstance(data, list):  # pragma: no cover
            executions = data  # type: ignore[assignment]
            continuation_token = None
        else:
            executions = data.get("executions", [])  # type: ignore[assignment]
            continuation_token = data.get("continuationToken")
        all_execs.extend(executions)
        if not continuation_token:
            break
    return all_execs


def _build_create_execution_payload(
    notebook_id: str,
    workspace: str,
    timeout: int,
    no_cache: bool,
    parameters: Optional[str],
    is_sls: bool,
) -> Dict[str, Any]:
    """Build the CreateExecution payload based on platform.

    Args:
        notebook_id: Notebook ID (SLE) or path (SLS).
        workspace: Workspace name or ID (SLE only).
        timeout: Execution timeout in seconds.
        no_cache: Whether to disable result caching.
        parameters: Optional JSON parameters string or @filepath.
        is_sls: Whether the platform is SLS (SystemLink Server).

    Returns:
        Dictionary with the CreateExecution payload.

    Raises:
        SystemExit: If parameters JSON is invalid.
    """
    if is_sls:
        # SLS uses notebookPath, no workspaceId
        create_execution: Dict[str, Any] = {
            "notebookPath": notebook_id,
            "timeout": timeout,
        }
    else:
        # SLE uses notebookId and workspaceId
        ws_id = get_workspace_id_with_fallback(workspace)
        create_execution = {
            "workspaceId": ws_id,
            "timeout": timeout,
            "notebookId": notebook_id,
        }

    if no_cache:
        create_execution["resultCachePeriod"] = 0
    if parameters:
        try:
            if parameters.strip().startswith("@"):
                p_file = parameters[1:]
                with open(p_file, "r", encoding="utf-8") as pf:
                    create_execution["parameters"] = json.load(pf)
            else:
                create_execution["parameters"] = json.loads(parameters)
        except Exception as exc:  # noqa: BLE001
            click.echo(f"✗ Invalid parameters JSON: {exc}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

    return create_execution


def _parse_execution_response(resp_data: Any, is_sls: bool) -> List[Dict[str, Any]]:
    """Parse the execution response based on platform.

    Args:
        resp_data: The JSON response data from the API.
        is_sls: Whether the platform is SLS (SystemLink Server).

    Returns:
        List of execution dictionaries.
    """
    # SLS returns a list directly, SLE returns {"executions": [...]}
    if is_sls:
        return resp_data if isinstance(resp_data, list) else []
    return cast(
        List[Dict[str, Any]],
        resp_data.get("executions") if isinstance(resp_data, dict) else [],
    )


def _create_notebook_http(name: str, workspace: str, content: bytes) -> Dict[str, Any]:
    """Create a notebook using HTTP. Only available on SLE."""
    if get_platform() == PLATFORM_SLS:
        raise Exception("Creating notebooks is not supported on SystemLink Server (SLS)")

    base_url = _get_notebook_base_url()
    headers = get_headers()  # No content-type for multipart

    # Create metadata following the SystemLink NotebookMetadata model structure
    metadata = {
        "name": name,
        "workspace": workspace,
        # Include optional fields that might be expected by the server
        "properties": {},
        "parameters": {},
    }

    # Validate content is valid JSON before sending
    try:
        json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise Exception(f"Invalid notebook content: {e}")

    # Follow the official SystemLink client pattern: use BytesIO for metadata
    metadata_json = json.dumps(metadata, separators=(",", ":"))  # Compact JSON
    metadata_bytes = metadata_json.encode("utf-8")

    files = {
        "metadata": ("metadata.json", metadata_bytes, "application/json"),
        "content": ("notebook.ipynb", content, "application/octet-stream"),
    }

    try:
        response = requests.post(
            f"{base_url}/notebook", headers=headers, files=files, verify=get_ssl_verify()
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        # Enhanced error handling to capture server response details
        error_details = f"HTTP request failed: {exc}"
        if hasattr(exc, "response") and exc.response is not None:
            try:
                error_body = exc.response.text
                error_details += f"\nResponse status: {exc.response.status_code}"
                error_details += f"\nResponse body: {error_body}"

                # Add request details for debugging
                error_details += f"\nRequest URL: {exc.response.url}"
                error_details += f"\nRequest metadata: {json.dumps(metadata)}"
                error_details += f"\nContent size: {len(content)} bytes"
            except Exception:
                pass
        raise Exception(error_details)


def _update_notebook_http(
    notebook_id: str, metadata: Optional[Dict[str, Any]] = None, content: Optional[bytes] = None
) -> Dict[str, Any]:
    """Update a notebook using HTTP. Only available on SLE."""
    if get_platform() == PLATFORM_SLS:
        raise Exception("Updating notebooks is not supported on SystemLink Server (SLS)")

    base_url = _get_notebook_base_url()
    headers = get_headers()  # No content-type for multipart

    files = {}
    if metadata:
        # Use filename 'blob' to mirror working requests accepted by the service
        files["metadata"] = ("blob", json.dumps(metadata), "application/json")
    if content:
        files["content"] = ("notebook.ipynb", content, "application/octet-stream")  # type: ignore

    try:
        response = requests.put(
            f"{base_url}/notebook/{notebook_id}",
            headers=headers,
            files=files,
            verify=get_ssl_verify(),
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


def _delete_notebook_http(notebook_id: str) -> None:
    """Delete a notebook using HTTP. Only available on SLE."""
    if get_platform() == PLATFORM_SLS:
        raise Exception("Deleting notebooks is not supported on SystemLink Server (SLS)")

    base_url = _get_notebook_base_url()
    headers = get_headers()

    try:
        response = requests.delete(
            f"{base_url}/notebook/{notebook_id}", headers=headers, verify=get_ssl_verify()
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


def _validate_notebook_interface(interface: str) -> None:
    """Validate that the interface string is one of the predefined interfaces.

    Args:
        interface: The interface string to validate.

    Raises:
        ValueError: If the interface is not in the predefined list.
    """
    if interface not in PREDEFINED_NOTEBOOK_INTERFACES:
        valid = ", ".join(PREDEFINED_NOTEBOOK_INTERFACES)
        raise ValueError(f"Invalid interface '{interface}'. Must be one of: {valid}")


def _set_notebook_interface_http(notebook_id: str, interface: str) -> Dict[str, Any]:
    """Set the interface property on a notebook via HTTP PUT.

    Args:
        notebook_id: The notebook ID (SLE only).
        interface: One of the predefined interface names.

    Returns:
        The updated notebook metadata.

    Raises:
        Exception: If the update fails or platform is SLS.
    """
    if get_platform() == PLATFORM_SLS:
        raise Exception("Setting notebook interfaces is not supported on SystemLink Server (SLS)")

    _validate_notebook_interface(interface)

    # Fetch current notebook to get name and workspace
    current_notebook = _get_notebook_http(notebook_id)

    # Build metadata with all required fields
    metadata = {
        "name": current_notebook.get("name"),
        "workspace": current_notebook.get("workspace"),
        "properties": {"interface": interface},
    }

    return _update_notebook_http(notebook_id, metadata=metadata)


def _download_notebook_content_and_metadata(
    notebook_id: str,
    notebook_name: str,
    output: Optional[str] = None,
    download_type: str = "both",
) -> None:
    """Download notebook content and/or metadata to disk."""
    content_failed = False
    metadata_failed = False

    # Download content
    if download_type in ("content", "both"):
        try:
            content = _get_notebook_content_http(notebook_id)
            output_path = output or (
                notebook_name if notebook_name.endswith(".ipynb") else f"{notebook_name}.ipynb"
            )
            with open(output_path, "wb") as f:
                f.write(content)
            click.echo(f"Notebook content downloaded to {output_path}")
        except Exception as exc:
            click.echo(f"Failed to download notebook content: {exc}")
            content_failed = True

    # Download metadata
    if download_type in ("metadata", "both"):
        try:
            meta = _get_notebook_http(notebook_id)
            meta_path = (output or notebook_name.replace(".ipynb", "")) + ".json"

            def _json_default(obj: Any) -> str:
                if isinstance(obj, (datetime.datetime, datetime.date)):
                    return obj.isoformat()
                return str(obj)

            save_json_file(meta, meta_path, _json_default)
            click.echo(f"Notebook metadata downloaded to {meta_path}")
        except Exception as exc:
            click.echo(f"Failed to download notebook metadata: {exc}")
            metadata_failed = True

    # If any download failed, raise an exception to trigger proper error handling
    if content_failed and download_type in ("content", "both"):
        raise Exception("Notebook content download failed")
    if metadata_failed and download_type in ("metadata", "both"):
        raise Exception("Notebook metadata download failed")


def register_notebook_commands(cli: Any) -> None:
    """Register CLI commands for managing SystemLink notebooks.

    Reorganized to mirror function commands structure:
      - 'notebook init' for local scaffold
      - 'notebook manage <subcommand>' for remote CRUD operations
      - 'notebook execute <subcommand>' reserved for future execution features
    """

    @cli.group()
    def notebook() -> None:  # pragma: no cover - Click wiring
        """Manage notebooks (init locally, manage remotely, run)."""
        pass

    # ------------------------------------------------------------------
    # Local initialization (no remote API call)
    # ------------------------------------------------------------------
    @notebook.command(name="init")
    @click.option(
        "--name",
        "notebook_name",
        required=False,
        default="new-notebook.ipynb",
        show_default=True,
        help="Notebook file name (will append .ipynb if missing)",
    )
    @click.option(
        "--directory",
        "directory",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        default=Path.cwd(),
        show_default="CWD",
        help="Target directory",
    )
    @click.option("--force", is_flag=True, help="Overwrite existing file if it exists")
    def init_notebook(notebook_name: str, directory: Path, force: bool) -> None:
        """Create a local Jupyter notebook skeleton."""
        try:
            if not notebook_name.lower().endswith(".ipynb"):
                notebook_name += ".ipynb"
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / notebook_name
            if target.exists() and not force:
                click.echo("✗ Target notebook already exists. Use --force to overwrite.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)
            empty_nb: Dict[str, Any] = {
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": [
                            "# New Notebook\n",
                            "Created locally with slcli notebook init.\n",
                        ],
                    }
                ],
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3 (ipykernel)",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {
                        "name": "python",
                        "version": sys.version.split()[0],
                    },
                },
                "nbformat": 4,
                "nbformat_minor": 5,
            }
            with open(target, "w", encoding="utf-8") as f:
                json.dump(empty_nb, f, indent=2)
            format_success("Local notebook initialized", {"Path": str(target)})
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Subgroups
    # ------------------------------------------------------------------
    @notebook.group(name="manage")
    def notebook_manage() -> None:  # pragma: no cover - Click wiring
        """Remote notebook CRUD operations."""
        pass

    @notebook.group(name="execute")
    def notebook_execute() -> None:  # pragma: no cover - Click wiring
        """Notebook execution operations."""
        pass

    # ------------------------------------------------------------------
    # Remote management commands (moved under 'manage')
    # ------------------------------------------------------------------

    # Backward compatibility: allow 'slcli notebook list' to still work by delegating.

    @notebook_manage.command(name="update")
    @click.option("--id", "-i", "notebook_id", required=True, help="Notebook ID to update")
    @click.option(
        "--metadata",
        type=click.Path(exists=True, dir_okay=False),
        required=False,
        help="Path to JSON file containing notebook metadata (must match notebook schema)",
    )
    @click.option(
        "--content",
        type=click.Path(exists=True, dir_okay=False),
        required=False,
        help="Path to .ipynb file containing notebook content",
    )
    @click.option(
        "--interface",
        type=click.Choice(PREDEFINED_NOTEBOOK_INTERFACES, case_sensitive=True),
        required=False,
        help="Interface to assign to the notebook (optional)",
    )
    def update_notebook(
        notebook_id: str,
        metadata: Optional[str],
        content: Optional[str],
        interface: Optional[str] = None,
    ) -> None:
        """Update a notebook's metadata, content, interface, or any combination by ID.

        Note: This command is only available on SystemLink Enterprise (SLE).
        SystemLink Server (SLS) does not support notebook updates via API.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("update a notebook")

        # Check if running on SLS - notebook updates not supported
        if get_platform() == PLATFORM_SLS:
            click.echo(
                "✗ Updating notebooks is not supported on SystemLink Server (SLS). "
                "Please use the SystemLink web interface to modify notebooks.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        if not metadata and not content and not interface:
            click.echo(
                "✗ Must provide at least one of --metadata, --content, or --interface.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            meta_dict = None
            if metadata:
                with open(metadata, "r", encoding="utf-8") as f:
                    meta_dict = json.load(f)

            content_bytes = None
            if content:
                with open(content, "rb") as f:
                    content_bytes = f.read()

            # If interface is provided, validate and add it to the metadata
            if interface:
                _validate_notebook_interface(interface)
                if not meta_dict:
                    meta_dict = {}
                if "properties" not in meta_dict:
                    meta_dict["properties"] = {}
                meta_dict["properties"]["interface"] = interface

            if not meta_dict and not content_bytes:
                click.echo(
                    "✗ Nothing to update. Provide --metadata, --content, and/or --interface.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            _update_notebook_http(notebook_id, metadata=meta_dict, content=content_bytes)
            format_success("Notebook updated", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="set-interface")
    @click.option(
        "--id",
        "-i",
        "notebook_id",
        required=True,
        help="Notebook ID to update",
    )
    @click.option(
        "--interface",
        "-f",
        "interface_name",
        required=True,
        type=click.Choice(PREDEFINED_NOTEBOOK_INTERFACES, case_sensitive=True),
        help="Interface to assign to the notebook",
    )
    def set_notebook_interface(notebook_id: str, interface_name: str) -> None:
        """Assign an interface to a notebook.

        The interface determines which SystemLink UI selectors will display
        this notebook.

        Note: This command is only available on SystemLink Enterprise (SLE).
        SystemLink Server (SLS) does not support notebook interface assignment.
        """
        if get_platform() == PLATFORM_SLS:
            click.echo(
                "✗ Setting notebook interfaces is not supported on SystemLink Server (SLS). "
                "Please use the SystemLink web interface to assign interfaces.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            result = _set_notebook_interface_http(notebook_id, interface_name)
            assigned_interface = result.get("properties", {}).get("interface", interface_name)
            format_success(
                "Interface assigned",
                {"Notebook ID": notebook_id, "Interface": assigned_interface},
            )
        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        default="",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--filter",
        "filter_text",
        default="",
        help="Case-insensitive substring to match name or interface",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of notebooks to return",
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
    def list_notebooks(
        workspace: str = "",
        filter_text: str = "",
        take: int = 25,
        format_output: str = "table",
    ) -> None:
        """List notebooks."""
        format_output = validate_output_format(format_output)

        try:
            ws_id = None
            if workspace:
                ws_id = validate_workspace_access(workspace, warn_on_error=True)

            filter_parts: List[str] = []
            if ws_id:
                filter_parts.append(f'workspace = "{ws_id}"')
            if filter_text:
                # Build case-insensitive contains without ToLower() due to backend limitations.
                # Match common variants: original, lower, upper, title-case.
                # Apply case transformations first, then escape each variant.
                def _esc(s: str) -> str:
                    return s.replace("\\", "\\\\").replace('"', '\\"')

                original_raw = filter_text
                lower_raw = original_raw.lower()
                upper_raw = original_raw.upper()
                title_raw = original_raw.title()
                name_variants = [
                    f'name.Contains("{_esc(original_raw)}")',
                    f'name.Contains("{_esc(lower_raw)}")',
                    f'name.Contains("{_esc(upper_raw)}")',
                    f'name.Contains("{_esc(title_raw)}")',
                ]
                iface_variants = [
                    f'properties.interface.Contains("{_esc(original_raw)}")',
                    f'properties.interface.Contains("{_esc(lower_raw)}")',
                    f'properties.interface.Contains("{_esc(upper_raw)}")',
                    f'properties.interface.Contains("{_esc(title_raw)}")',
                ]
                filter_parts.append(
                    f"(({' or '.join(name_variants)}) or ({' or '.join(iface_variants)}))"
                )

            combined_filter = " and ".join(filter_parts) if filter_parts else None

            try:
                notebooks_raw = _query_notebooks_http(combined_filter, take=1000)
            except Exception as exc:
                click.echo(
                    f"✗ Error querying notebooks: {exc}",
                    err=True,
                )
                notebooks_raw = []

            # Map workspace IDs to names for display
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            notebooks = []
            for idx, nb in enumerate(notebooks_raw):
                try:
                    ws_id = nb.get("workspace", "")
                    ws_name = get_workspace_display_name(ws_id, workspace_map)
                    name = nb.get("name", "")
                    nb_id = nb.get("id", "")
                    parameters = nb.get("parameters", {})
                    interface = nb.get("properties", {}).get("interface")

                    notebook_data = {
                        "workspace": ws_name,
                        "name": name,
                        "id": nb_id,
                        "parameters": parameters,
                    }
                    if interface:
                        notebook_data["properties"] = {"interface": interface}
                    notebooks.append(notebook_data)
                except Exception as nb_exc:
                    click.echo(
                        f"✗ Warning: Skipping invalid notebook result at index {idx}: {nb_exc}",
                        err=True,
                    )

            if not notebooks:
                if format_output.lower() == "json":
                    click.echo("[]")
                else:
                    click.echo("No notebooks found.")
                return

            # Use universal response handler (create a mock response for consistency)
            class MockResponse:
                def json(self) -> Dict[str, Any]:
                    return {"notebooks": notebooks}

                @property
                def status_code(self) -> int:
                    return 200

            mock_resp: Any = MockResponse()  # Type annotation to avoid type checker issues

            def notebook_formatter(notebook: dict) -> list:
                interface = notebook.get("properties", {}).get("interface", "—")
                return [
                    notebook.get("name", "Unknown"),
                    notebook.get("workspace", "N/A"),
                    interface,
                    notebook.get("id", ""),
                    "Jupyter",  # Type
                ]

            UniversalResponseHandler.handle_list_response(
                resp=mock_resp,
                data_key="notebooks",
                item_name="notebook",
                format_output=format_output,
                formatter_func=notebook_formatter,
                headers=["Name", "Workspace", "Interface", "ID", "Type"],
                column_widths=[30, 20, 25, 36, 12],
                empty_message="No notebooks found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="download")
    @click.option("--id", "-i", "notebook_id", help="Notebook ID")
    @click.option("--name", "notebook_name", help="Notebook name")
    @click.option("--workspace", default="Default", help="Workspace name or ID (default: Default)")
    @click.option("--output", required=False, help="Output file path (defaults to notebook name)")
    @click.option(
        "--type",
        "download_type",
        type=click.Choice(["content", "metadata", "both"], case_sensitive=False),
        default="content",
        show_default=True,
        help="What to download: notebook content, metadata, or both",
    )
    def download_notebook(
        notebook_id: str = "",
        notebook_name: str = "",
        workspace: str = "Default",
        output: str = "",
        download_type: str = "content",
    ) -> None:
        """Download notebook content/metadata."""
        if not notebook_id and not notebook_name:
            click.echo("✗ Must provide either --id or --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        ws_id = get_workspace_id_with_fallback(workspace)

        try:
            nb_name = notebook_name
            # Find notebook by name or id
            if notebook_name:
                filter_str = f'name = "{notebook_name}" and workspace = "{ws_id}"'
                results = _query_notebooks_http(filter_str)
                found = next(
                    (nb for nb in results if nb.get("name") == notebook_name),
                    None,
                )
                if not found:
                    click.echo(f"✗ Notebook named '{notebook_name}' not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
                notebook_id = found.get("id", "")
                nb_name = found.get("name", notebook_name)
            elif notebook_id:
                if not output:
                    filter_str = f'id = "{notebook_id}" and workspace = "{ws_id}"'
                    results = _query_notebooks_http(filter_str)
                    nb_name = results[0].get("name", notebook_id) if results else notebook_id

            # Download notebook content and/or metadata using shared helper
            if not isinstance(notebook_id, str) or not notebook_id:
                click.echo("✗ Notebook ID must be a non-empty string.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)
            _download_notebook_content_and_metadata(
                notebook_id,
                nb_name,
                output=output,
                download_type=download_type,
            )
            click.echo(f"✓ Notebook ID: {notebook_id}")
        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="get")
    @click.option(
        "--id",
        "-i",
        "notebook_id",
        required=True,
        help="Notebook ID (SLE) or path (SLS) to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_notebook(notebook_id: str, format: str = "table") -> None:  # type: ignore[override]
        """Show notebook details.

        Displays notebook metadata and basic properties. For content download use
        'slcli notebook manage download'.

        On SLS, use the notebook path (e.g., '_shared/reports/First Pass Yield.ipynb').
        On SLE, use the notebook ID (GUID).
        """
        format_output = validate_output_format(format)
        is_sls = get_platform() == PLATFORM_SLS

        try:
            if is_sls:
                # SLS: Use direct GET endpoint with path
                notebook = _get_notebook_http(notebook_id)
            else:
                # SLE: Use query filter to fetch notebook by ID
                filter_str = f'id = "{notebook_id}"'
                results = _query_notebooks_http(filter_str)
                if not results:
                    click.echo("✗ Notebook not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
                notebook = results[0]

            if format_output == "json":
                click.echo(json.dumps(notebook, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(
                notebook.get("workspace", ""),
                workspace_map,
            )

            click.echo("Notebook Details:")
            click.echo("=" * 50)
            click.echo(f"ID:          {notebook.get('id', 'N/A')}")
            click.echo(f"Name:        {notebook.get('name', 'N/A')}")
            if is_sls:
                click.echo(f"Path:        {notebook.get('path', 'N/A')}")
            click.echo(f"Workspace:   {ws_name}")
            interface = notebook.get("properties", {}).get("interface")
            if interface:
                click.echo(f"Interface:   {interface}")
            click.echo(f"Size (bytes): {notebook.get('size', 'N/A')}")
            click.echo(f"Created At:  {notebook.get('createdAt', 'N/A')}")
            click.echo(f"Updated At:  {notebook.get('updatedAt', 'N/A')}")
            # Additional metadata keys if present
            kernel_spec = notebook.get("kernel") or notebook.get("kernelspec")
            if kernel_spec:
                if isinstance(kernel_spec, dict):
                    click.echo(f"Kernel:      {kernel_spec.get('name', 'python')}")
                else:
                    click.echo(f"Kernel:      {kernel_spec}")
        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="create")
    @click.option("--file", "input_file", required=False, help="Path to notebook file to create")
    @click.option("--workspace", default="Default", help="Workspace name or ID (default: Default)")
    @click.option("--name", "notebook_name", required=True, help="Notebook name")
    @click.option(
        "--interface",
        type=click.Choice(PREDEFINED_NOTEBOOK_INTERFACES, case_sensitive=True),
        required=False,
        help="Interface to assign to the notebook (optional)",
    )
    def create_notebook(
        input_file: str = "",
        workspace: str = "Default",
        notebook_name: str = "",
        interface: Optional[str] = None,
    ) -> None:
        """Create a notebook with optional interface assignment.

        Fails if a notebook with the same name exists.

        Note: This command is only available on SystemLink Enterprise (SLE).
        SystemLink Server (SLS) does not support notebook creation via API.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("create a notebook")

        # Validate interface early if provided
        if interface:
            try:
                _validate_notebook_interface(interface)
            except ValueError as exc:
                click.echo(f"✗ {exc}", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

        # Check if running on SLS - notebook creation not supported
        if get_platform() == PLATFORM_SLS:
            click.echo(
                "✗ Creating notebooks is not supported on SystemLink Server (SLS). "
                "Please use the SystemLink web interface to upload notebooks.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        ws_id = get_workspace_id_with_fallback(workspace)

        try:
            # Validate workspace exists and is accessible
            try:
                workspace_map = get_workspace_map()
                if ws_id not in workspace_map and workspace != ws_id:
                    # If ws_id is not in workspace_map and we didn't get it directly from user
                    click.echo(
                        f"⚠️  Warning: Workspace '{workspace}' may not exist or be accessible.",
                        err=True,
                    )
            except Exception:
                click.echo("⚠️  Warning: Could not validate workspace access.", err=True)

            # Ensure the uploaded file has a .ipynb extension
            if not notebook_name.lower().endswith(".ipynb"):
                notebook_name += ".ipynb"
            # Check for existing notebook with same name in workspace
            filter_str = f'name = "{notebook_name}" and workspace = "{ws_id}"'
            results = _query_notebooks_http(filter_str)
            if results:
                click.echo(
                    f"✗ A notebook named '{notebook_name}' already exists in this workspace. Creation cancelled.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            # No existing notebook, create new
            if input_file:
                with open(input_file, "rb") as content_file:
                    content = content_file.read()
                    result = _create_notebook_http(notebook_name, ws_id, content)
                format_success("Notebook created", {"ID": result.get("id")})
            else:
                # Create a notebook matching the structure of successful SystemLink notebooks
                empty_nb = {
                    "cells": [
                        {
                            "cell_type": "markdown",
                            "id": "new-notebook-cell",
                            "metadata": {},
                            "source": "# New Notebook\n\nThis is a new notebook created with SystemLink CLI.",
                        }
                    ],
                    "metadata": {
                        "kernelspec": {
                            "display_name": "Python 3 (ipykernel)",
                            "language": "python",
                            "name": "python3",
                        },
                        "language_info": {
                            "codemirror_mode": {"name": "ipython", "version": 3},
                            "file_extension": ".py",
                            "mimetype": "text/x-python",
                            "name": "python",
                            "nbconvert_exporter": "python",
                            "pygments_lexer": "ipython3",
                            "version": "3.11.6",
                        },
                        "toc-showtags": False,
                    },
                    "nbformat": 4,
                    "nbformat_minor": 5,
                }

                content = json.dumps(empty_nb, indent=2).encode("utf-8")
                result = _create_notebook_http(notebook_name, ws_id, content)
                format_success("Notebook created", {"ID": result.get("id")})

            # Validate and assign interface if provided (requires separate call after creation)
            if interface and result:
                try:
                    notebook_id = result.get("id", "")
                    if notebook_id:
                        _set_notebook_interface_http(notebook_id, interface)
                        click.echo(f"✓ Interface '{interface}' assigned")
                except Exception as exc:
                    click.echo(f"⚠ Warning: Failed to assign interface: {exc}", err=True)

            # Download option removed: users should run 'notebook manage download' after creation
            # if they want to retrieve content or metadata.
        except Exception as exc:
            handle_api_error(exc)

    @notebook_manage.command(name="delete")
    @click.option("--id", "-i", "notebook_id", required=True, help="Notebook ID to delete")
    @click.confirmation_option(prompt="Are you sure you want to delete this notebook?")
    def delete_notebook(notebook_id: str = "") -> None:
        """Delete a notebook.

        Note: This command is only available on SystemLink Enterprise (SLE).
        SystemLink Server (SLS) does not support notebook deletion via API.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("delete a notebook")

        # Check if running on SLS - notebook deletion not supported
        if get_platform() == PLATFORM_SLS:
            click.echo(
                "✗ Deleting notebooks is not supported on SystemLink Server (SLS). "
                "Please use the SystemLink web interface to delete notebooks.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            _delete_notebook_http(notebook_id)
            format_success("Notebook deleted", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Execution helpers (Notebook Execution Service)
    # ------------------------------------------------------------------

    # (Execution helpers now defined at module scope for test patching.)

    # ------------------------------------------------------------------
    # Execution commands (mirror function execute group)
    # ------------------------------------------------------------------

    @notebook_execute.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--status",
        "-s",
        help=(
            "Filter by execution status (case-insensitive). Allowed: in_progress, queued, failed, "
            "succeeded, canceled, timed_out."
        ),
    )
    @click.option("--notebook-id", "-n", help="Filter by notebook ID")
    @click.option("--take", "-t", type=int, default=25, show_default=True, help="Max rows/page")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_notebook_executions(
        workspace: Optional[str] = None,
        status: Optional[str] = None,
        notebook_id: Optional[str] = None,
        take: int = 25,
        format: str = "table",
    ) -> None:
        """List notebook executions."""
        format_output = validate_output_format(format)
        try:
            workspace_map = get_workspace_map()
            workspace_guid = None
            if workspace:
                workspace_guid = get_workspace_id_with_fallback(workspace)

            def _normalize_execution_status(raw: str) -> str:
                """Normalize user-provided execution status to service token.

                Accept (case-insensitive) one of:
                  in_progress, queued, failed, succeeded, canceled, timed_out

                Map to service forms (no underscore for IN_PROGRESS/TIMED_OUT):
                  IN_PROGRESS -> INPROGRESS
                  TIMED_OUT   -> TIMEDOUT
                Others pass through unchanged uppercased.
                """
                canonical = raw.strip().upper().replace("-", "_")
                mapping = {
                    "IN_PROGRESS": "INPROGRESS",
                    "TIMED_OUT": "TIMEDOUT",
                    "QUEUED": "QUEUED",
                    "FAILED": "FAILED",
                    "SUCCEEDED": "SUCCEEDED",
                    "CANCELED": "CANCELED",
                }
                if canonical in mapping:
                    return mapping[canonical]
                click.echo(
                    "✗ Invalid status. Allowed: in_progress, queued, failed, succeeded, canceled, timed_out",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            status_service_value = _normalize_execution_status(status) if status else None

            is_sls = get_platform() == PLATFORM_SLS
            if is_sls:
                # SLS doesn't support workspaceId filtering, uses notebookPath
                executions = _query_notebook_executions(
                    status=status_service_value, notebook_path=notebook_id
                )
            else:
                # SLE uses workspaceId and notebookId
                executions = _query_notebook_executions(
                    workspace_guid, status_service_value, notebook_id
                )

            class ExecResp:
                def json(self) -> Dict[str, Any]:  # noqa: D401
                    return {"executions": executions}

                @property
                def status_code(self) -> int:
                    return 200

            mock_resp: Any = ExecResp()

            def exec_formatter(exe: Dict[str, Any]) -> List[str]:
                queued_at = exe.get("queuedAt", "")
                if queued_at:
                    queued_at = queued_at.split("T")[0]
                if is_sls:
                    # SLS uses notebookPath
                    return [
                        exe.get("id", ""),
                        exe.get("notebookPath", ""),
                        exe.get("status", "UNKNOWN"),
                        queued_at,
                    ]
                else:
                    # SLE uses notebookId and workspaceId
                    ws_name = get_workspace_display_name(exe.get("workspaceId", ""), workspace_map)
                    return [
                        exe.get("id", ""),
                        exe.get("notebookId", ""),
                        ws_name,
                        exe.get("status", "UNKNOWN"),
                        queued_at,
                    ]

            if is_sls:
                headers = ["ID", "Notebook Path", "Status", "Queued"]
                column_widths = [36, 50, 12, 12]
            else:
                headers = ["ID", "Notebook ID", "Workspace", "Status", "Queued"]
                column_widths = [36, 36, 20, 12, 12]

            UniversalResponseHandler.handle_list_response(
                resp=mock_resp,
                data_key="executions",
                item_name="execution",
                format_output=format_output,
                formatter_func=exec_formatter,
                headers=headers,
                column_widths=column_widths,
                empty_message="No notebook executions found.",
                enable_pagination=True,
                page_size=take,
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @notebook_execute.command(name="get")
    @click.option("--id", "-i", "execution_id", required=True, help="Execution ID")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_notebook_execution(execution_id: str, format: str = "table") -> None:
        """Show a notebook execution."""
        format_output = validate_output_format(format)
        base = _get_notebook_execution_base()
        url = f"{base}/executions/{execution_id}"
        try:
            data = make_api_request("GET", url).json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return

            is_sls = get_platform() == PLATFORM_SLS
            click.echo("Notebook Execution Details:")
            click.echo("=" * 50)
            click.echo(f"ID:               {data.get('id', 'N/A')}")

            if is_sls:
                # SLS uses notebookPath
                click.echo(f"Notebook Path:    {data.get('notebookPath', 'N/A')}")
            else:
                # SLE uses notebookId and workspaceId
                workspace_map = get_workspace_map()
                ws_name = get_workspace_display_name(data.get("workspaceId", ""), workspace_map)
                click.echo(f"Notebook ID:      {data.get('notebookId', 'N/A')}")
                click.echo(f"Workspace:        {ws_name}")

            click.echo(f"Status:           {data.get('status', 'N/A')}")
            click.echo(f"Timeout:          {data.get('timeout', 'N/A')}")
            click.echo(f"Queued At:        {data.get('queuedAt', 'N/A')}")
            click.echo(f"Started At:       {data.get('startedAt', 'N/A')}")
            click.echo(f"Completed At:     {data.get('completedAt', 'N/A')}")
            if data.get("parameters"):
                click.echo("\nParameters:")
                click.echo(json.dumps(data["parameters"], indent=2))
            if data.get("result"):
                click.echo("\nResult:")
                click.echo(json.dumps(data["result"], indent=2))
            # Display platform-specific error field with precise label
            if is_sls and data.get("exception"):
                click.echo("\nException:")
                click.echo(data["exception"])
            elif not is_sls and data.get("errorMessage"):
                click.echo("\nError Message:")
                click.echo(data["errorMessage"])
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @notebook_execute.command(name="start")
    @click.option(
        "--notebook-id",
        "-n",
        required=True,
        help="Notebook ID (SLE) or notebook path (SLS) to execute",
    )
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (SLE only, default: 'Default')",
    )
    @click.option(
        "--parameters",
        "-p",
        help="Raw JSON string or @file for parameters passed to execution service",
    )
    @click.option(
        "--timeout",
        "-t",
        type=int,
        default=1800,
        show_default=True,
        help="Execution timeout in seconds",
    )
    @click.option(
        "--no-cache",
        is_flag=True,
        help="Disable result caching (sets resultCachePeriod=0)",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def start_notebook_execution(
        notebook_id: str,
        workspace: str = "Default",
        parameters: Optional[str] = None,
        timeout: int = 1800,
        no_cache: bool = False,
        format: str = "table",
    ) -> None:
        """Start a notebook execution and return immediately."""
        format_output = validate_output_format(format)
        base = _get_notebook_execution_base()
        is_sls = get_platform() == PLATFORM_SLS

        # Warn if workspace is specified on SLS (where it's ignored)
        if is_sls and workspace != "Default":
            click.echo(
                "⚠ Warning: --workspace is ignored on SystemLink Server (SLS). "
                "SLS does not use workspace filtering for notebook executions.",
                err=True,
            )

        # Build CreateExecution payload using helper function
        create_execution = _build_create_execution_payload(
            notebook_id=notebook_id,
            workspace=workspace,
            timeout=timeout,
            no_cache=no_cache,
            parameters=parameters,
            is_sls=is_sls,
        )
        # The API expects an array of CreateExecution objects.
        payload: List[Dict[str, Any]] = [create_execution]
        url = f"{base}/executions"
        try:
            # Use direct requests.post because make_api_request only supports dict payloads.
            headers = get_headers("application/json")
            resp = requests.post(url, headers=headers, json=payload, verify=get_ssl_verify())
            resp.raise_for_status()
            resp_data = resp.json()

            # Parse response using helper function
            executions = _parse_execution_response(resp_data, is_sls)

            if not executions:
                # API may return error in BaseResponse.error
                if isinstance(resp_data, dict):
                    error_obj = resp_data.get("error")
                    if error_obj:
                        click.echo(
                            f"✗ Error: {error_obj.get('message', 'Unknown error')}", err=True
                        )
                        sys.exit(ExitCodes.GENERAL_ERROR)
                click.echo("✗ No execution returned by service", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
            execution = executions[0]
            if format_output == "json":
                # Emit the first execution for convenience (matches table output scope)
                click.echo(json.dumps(execution, indent=2))
                return
            click.echo("Notebook Execution Result:")
            click.echo("=" * 50)
            click.echo(f"Execution ID:  {execution.get('id', 'N/A')}")
            click.echo(f"Status:        {execution.get('status', 'N/A')}")
            if "cachedResult" in execution:
                cached = execution.get("cachedResult")
                note = " (served from cache)" if cached else ""
                click.echo(f"Cached Result: {cached}{note}")
            if execution.get("result"):
                click.echo("\nResult:")
                click.echo(json.dumps(execution["result"], indent=2))
            if execution.get("errorMessage"):
                click.echo("\nError Message:")
                click.echo(execution["errorMessage"])
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @notebook_execute.command(name="sync")
    @click.option(
        "--notebook-id",
        "-n",
        required=True,
        help="Notebook ID (SLE) or notebook path (SLS) to execute synchronously",
    )
    @click.option(
        "--workspace",
        "-w",
        default="Default",
        help="Workspace name or ID (SLE only, default: 'Default')",
    )
    @click.option(
        "--parameters",
        "-p",
        help="Raw JSON string or @file for parameters passed to execution service",
    )
    @click.option(
        "--timeout",
        "-t",
        type=int,
        default=1800,
        show_default=True,
        help="Execution timeout in seconds (server-side; 0 for infinite)",
    )
    @click.option(
        "--poll-interval",
        type=float,
        default=2.0,
        show_default=True,
        help="Polling interval when waiting for completion",
    )
    @click.option(
        "--max-wait",
        type=int,
        default=None,
        help="Maximum seconds to wait client-side (default: timeout + 60 if set)",
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
        "--no-cache",
        is_flag=True,
        help="Disable result caching (sets resultCachePeriod=0)",
    )
    def execute_notebook_sync(
        notebook_id: str,
        workspace: str = "Default",
        parameters: Optional[str] = None,
        timeout: int = 1800,
        poll_interval: float = 2.0,
        max_wait: Optional[int] = None,
        no_cache: bool = False,
        format: str = "table",
    ) -> None:
        """Execute a notebook and wait for completion."""
        format_output = validate_output_format(format)
        base = _get_notebook_execution_base()
        is_sls = get_platform() == PLATFORM_SLS

        # Build CreateExecution payload using helper function
        create_execution = _build_create_execution_payload(
            notebook_id=notebook_id,
            workspace=workspace,
            timeout=timeout,
            no_cache=no_cache,
            parameters=parameters,
            is_sls=is_sls,
        )
        payload: List[Dict[str, Any]] = [create_execution]
        url = f"{base}/executions"
        try:
            headers = get_headers("application/json")
            resp = requests.post(url, headers=headers, json=payload, verify=get_ssl_verify())
            resp.raise_for_status()
            resp_data = resp.json()

            # Parse response using helper function
            executions = _parse_execution_response(resp_data, is_sls)

            if not executions:
                if isinstance(resp_data, dict):
                    error_obj = resp_data.get("error")
                    if error_obj:
                        click.echo(
                            f"✗ Error creating execution: {error_obj.get('message', 'Unknown error')}",
                            err=True,
                        )
                        sys.exit(ExitCodes.GENERAL_ERROR)
                click.echo("✗ No execution returned by service", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
            execution = executions[0]
            execution_id = execution.get("id")
            if not execution_id:
                click.echo("✗ Execution response missing ID", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
            # Polling loop
            terminal_statuses = {"SUCCEEDED", "FAILED", "CANCELED", "TIMED_OUT"}
            spinner_frames = ["|", "/", "-", "\\"]
            spinner_index = 0
            start_time = time.time()
            computed_max_wait = (
                max_wait if max_wait is not None else (timeout + 60 if timeout else None)
            )
            status = execution.get("status", "QUEUED")
            last_print_status = ""
            while status not in terminal_statuses:
                # Respect client-side max wait
                if computed_max_wait is not None and (time.time() - start_time) > computed_max_wait:
                    click.echo("\n✗ Reached client-side max wait timeout", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)
                spinner = spinner_frames[spinner_index % len(spinner_frames)]
                spinner_index += 1
                # Fetch latest execution state
                try:
                    exec_resp = make_api_request(
                        "GET", f"{base}/executions/{execution_id}", payload=None
                    ).json()
                    status = exec_resp.get("status", status)
                    execution = exec_resp
                except Exception:  # noqa: BLE001
                    # Transient fetch error; continue (error already printed by handler)
                    pass
                if format_output == "json":
                    # Suppress spinner for machine-readable output (could add to stderr)
                    pass
                else:
                    if status != last_print_status:
                        click.echo("")  # newline when status changes
                        last_print_status = status
                    msg = (
                        f"{spinner} Waiting for execution {execution_id} | Status: {status} | "
                        f"Elapsed: {int(time.time() - start_time)}s"
                    )
                    # carriage return for inline spinner
                    click.echo(msg, nl=False)
                    click.echo("\r", nl=False)
                time.sleep(poll_interval)
            # Finished
            if format_output == "json":
                click.echo(json.dumps(execution, indent=2))
                return
            click.echo("")  # ensure newline after spinner line
            click.echo("Notebook Execution Completed:")
            click.echo("=" * 50)
            click.echo(f"Execution ID:  {execution.get('id', 'N/A')}")
            click.echo(f"Status:        {execution.get('status', 'N/A')}")
            if "cachedResult" in execution:
                cached = execution.get("cachedResult")
                note = " (served from cache)" if cached else ""
                click.echo(f"Cached Result: {cached}{note}")
            if execution.get("result"):
                click.echo("\nResult:")
                click.echo(json.dumps(execution["result"], indent=2))
            if execution.get("errorMessage"):
                click.echo("\nError Message:")
                click.echo(execution["errorMessage"])
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @notebook_execute.command(name="cancel")
    @click.option("--id", "-i", "execution_id", required=True, help="Execution ID to cancel")
    def cancel_notebook_execution(execution_id: str) -> None:
        """Cancel a notebook execution."""
        base = _get_notebook_execution_base()
        is_sls = get_platform() == PLATFORM_SLS

        try:
            if is_sls:
                # SLS uses bulk cancel endpoint with array of IDs
                url = f"{base}/cancel-executions"
                headers = get_headers("application/json")
                resp = requests.post(
                    url, headers=headers, json=[execution_id], verify=get_ssl_verify()
                )
                resp.raise_for_status()
            else:
                # SLE uses individual cancel endpoint
                url = f"{base}/executions/{execution_id}/cancel"
                make_api_request("POST", url, payload={})
            format_success("Notebook execution cancellation requested", {"ID": execution_id})
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @notebook_execute.command(name="retry")
    @click.option("--id", "-i", "execution_id", required=True, help="Execution ID to retry")
    def retry_notebook_execution(execution_id: str) -> None:
        """Retry a failed notebook execution (SLE only)."""
        is_sls = get_platform() == PLATFORM_SLS
        if is_sls:
            click.echo(
                "✗ Execution retry is not available on SystemLink Server. "
                "Please create a new execution instead.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        base = _get_notebook_execution_base()
        url = f"{base}/executions/{execution_id}/retry"
        try:
            data = make_api_request("POST", url, payload={}).json()
            format_success("Notebook execution retry started", {"ID": data.get("id", execution_id)})
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

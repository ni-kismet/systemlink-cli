"""CLI commands for managing SystemLink notebooks via the SystemLink Notebook API.

Provides CLI commands for listing, creating, updating, downloading, and deleting Jupyter notebooks.
All commands use Click for robust CLI interfaces and error handling.
"""

import datetime
import json
import sys
from typing import Any, Dict, List, Optional

import click
import requests

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
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


def _get_notebook_base_url() -> str:
    """Get the base URL for notebook API."""
    return f"{get_base_url()}/ninotebook/v1"


def _query_notebooks_http(
    filter_str: Optional[str] = None, take: int = 1000
) -> List[Dict[str, Any]]:
    """Query notebooks using continuation token pagination for better performance."""
    base_url = _get_notebook_base_url()
    headers = get_headers("application/json")

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
            response = requests.post(
                f"{base_url}/notebook/query", headers=headers, json=payload, verify=get_ssl_verify()
            )
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
    """Get a single notebook by ID using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers("application/json")

    try:
        response = requests.get(
            f"{base_url}/notebook/{notebook_id}", headers=headers, verify=get_ssl_verify()
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


def _get_notebook_content_http(notebook_id: str) -> bytes:
    """Get notebook content by ID using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers()  # No content-type for binary content

    try:
        response = requests.get(
            f"{base_url}/notebook/{notebook_id}/content", headers=headers, verify=get_ssl_verify()
        )
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


def _create_notebook_http(name: str, workspace: str, content: bytes) -> Dict[str, Any]:
    """Create a notebook using HTTP."""
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
    """Update a notebook using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers()  # No content-type for multipart

    files = {}
    if metadata:
        files["metadata"] = (None, json.dumps(metadata), "application/json")
    if content:
        files["content"] = ("notebook.ipynb", content, "application/octet-stream")

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
    """Delete a notebook using HTTP."""
    base_url = _get_notebook_base_url()
    headers = get_headers()

    try:
        response = requests.delete(
            f"{base_url}/notebook/{notebook_id}", headers=headers, verify=get_ssl_verify()
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise Exception(f"HTTP request failed: {exc}")


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
    """Register CLI commands for managing SystemLink notebooks."""

    @cli.group()
    def notebook() -> None:
        """Manage Jupyter notebooks."""
        pass

    @notebook.command(name="update")
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
    def update_notebook(notebook_id: str, metadata: Optional[str], content: Optional[str]) -> None:
        """Update a notebook's metadata, content, or both by ID."""
        if not metadata and not content:
            click.echo("✗ Must provide at least one of --metadata or --content.", err=True)
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

            if not meta_dict and not content_bytes:
                click.echo(
                    "✗ Nothing to update. Provide --metadata and/or --content.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            _update_notebook_http(notebook_id, metadata=meta_dict, content=content_bytes)
            format_success("Notebook updated", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        default="",
        help="Filter by workspace name or ID",
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
    def list_notebooks(workspace: str = "", take: int = 25, format_output: str = "table") -> None:
        """List all notebooks. Optionally filter by workspace."""
        format_output = validate_output_format(format_output)

        try:
            ws_id = None
            if workspace:
                ws_id = validate_workspace_access(workspace, warn_on_error=True)

            filter_str = None
            if ws_id:
                filter_str = f'workspace = "{ws_id}"'

            try:
                notebooks_raw = _query_notebooks_http(filter_str, take=1000)
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

                    notebooks.append(
                        {
                            "workspace": ws_name,
                            "name": name,
                            "id": nb_id,
                            "parameters": parameters,
                        }
                    )
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
                return [
                    notebook.get("name", "Unknown"),
                    notebook.get("workspace", "N/A"),
                    notebook.get("id", ""),
                    "Jupyter",  # Type
                ]

            UniversalResponseHandler.handle_list_response(
                resp=mock_resp,
                data_key="notebooks",
                item_name="notebook",
                format_output=format_output,
                formatter_func=notebook_formatter,
                headers=["Name", "Workspace", "ID", "Type"],
                column_widths=[40, 30, 36, 12],
                empty_message="No notebooks found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="download")
    @click.option("--id", "-i", "notebook_id", help="Notebook ID")
    @click.option("--name", "notebook_name", help="Notebook name")
    @click.option("--workspace", default="Default", help="Workspace name (default: Default)")
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
        """Download a notebook's content, metadata, or both by ID or name."""
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

    @notebook.command(name="create")
    @click.option("--file", "input_file", required=False, help="Path to notebook file to create")
    @click.option("--workspace", default="Default", help="Workspace name (default: Default)")
    @click.option("--name", "notebook_name", required=True, help="Notebook name")
    @click.option(
        "--download",
        is_flag=True,
        default=False,
        help="Download notebook content and metadata after creation.",
    )
    def create_notebook(
        input_file: str = "",
        workspace: str = "Default",
        notebook_name: str = "",
        download: bool = False,
    ) -> None:
        """Create a new notebook in the specified workspace.

        Fails if a notebook with the same name exists.
        """
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

            # Download notebook content and metadata if requested
            if download:
                notebook_id = result.get("id")
                if not notebook_id:
                    click.echo("✗ Notebook ID not found, cannot download.", err=True)
                    return
                _download_notebook_content_and_metadata(
                    notebook_id,
                    notebook_name,
                    output=None,
                    download_type="both",
                )
        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="delete")
    @click.option("--id", "-i", "notebook_id", required=True, help="Notebook ID to delete")
    def delete_notebook(notebook_id: str = "") -> None:
        """Delete a notebook by ID."""
        try:
            _delete_notebook_http(notebook_id)
            format_success("Notebook deleted", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

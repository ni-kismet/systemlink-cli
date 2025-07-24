"""CLI commands for managing SystemLink notebooks via the SystemLink Notebook API.

Provides CLI commands for listing, creating, updating, downloading, and deleting Jupyter notebooks.
All commands use Click for robust CLI interfaces and error handling.
"""

import dataclasses
import datetime
import json
import sys
import tempfile

import click
from nisystemlink.clients.notebook._notebook_client import NotebookClient
from nisystemlink.clients.notebook.models._notebook_metadata import NotebookMetadata
from nisystemlink.clients.notebook.models._query_notebook_request import QueryNotebookRequest

from .utils import (
    get_http_configuration,
    get_workspace_map,
    ExitCodes,
    handle_api_error,
    format_success,
    validate_workspace_access,
    get_workspace_id_with_fallback,
    save_json_file,
)


def _get_notebooks_from_query(nb_client, query_obj):
    """Helper to parse paged notebook query response and return a list of notebook objects."""
    paged_result = nb_client.query_notebooks(query_obj)
    notebooks = getattr(paged_result, "notebooks", None)
    if notebooks is None:
        notebooks = []
    return notebooks


def _download_notebook_content_and_metadata(
    nb_client, notebook_id, notebook_name, output=None, download_type="both"
):
    """Download notebook content and/or metadata to disk."""
    """Download notebook content and/or metadata to disk."""
    # Download content
    if download_type in ("content", "both"):
        try:
            content = nb_client.get_notebook_content(str(notebook_id)).read()
            output_path = output or (
                notebook_name if notebook_name.endswith(".ipynb") else f"{notebook_name}.ipynb"
            )
            with open(output_path, "wb") as f:
                f.write(content)
            click.echo(f"Notebook content downloaded to {output_path}")
        except Exception as exc:
            click.echo(f"Failed to download notebook content: {exc}")
    # Download metadata
    if download_type in ("metadata", "both"):
        try:
            meta = nb_client.get_notebook(str(notebook_id))
            meta_path = (output or notebook_name.replace(".ipynb", "")) + ".json"

            def _json_default(obj):
                if isinstance(obj, (datetime.datetime, datetime.date)):
                    return obj.isoformat()
                return str(obj)

            if dataclasses.is_dataclass(meta) and not isinstance(meta, type):
                data = dataclasses.asdict(meta)
            else:
                data = getattr(meta, "__dict__", meta)
            save_json_file(data, meta_path, _json_default)
            click.echo(f"Notebook metadata downloaded to {meta_path}")
        except Exception as exc:
            click.echo(f"Failed to download notebook metadata: {exc}")


def register_notebook_commands(cli):
    """Register CLI commands for managing SystemLink notebooks."""

    @cli.group()
    def notebook():
        """Manage Jupyter notebooks."""
        pass

    @notebook.command(name="update")
    @click.option("--id", "notebook_id", required=True, help="Notebook ID to update")
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
    def update_notebook(notebook_id, metadata, content):
        """Update a notebook's metadata, content, or both by ID."""
        import json

        if not metadata and not content:
            click.echo("✗ Must provide at least one of --metadata or --content.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            nb_client = NotebookClient(configuration=get_http_configuration())
            meta_obj = None
            if metadata:
                with open(metadata, "r", encoding="utf-8") as f:
                    meta_json = json.load(f)
                meta_obj = NotebookMetadata(**meta_json)
            content_file = None
            if content:
                with open(content, "rb") as content_file:
                    if not meta_obj and not content_file:
                        click.echo(
                            "✗ Nothing to update. Provide --metadata and/or --content.", err=True
                        )
                        sys.exit(ExitCodes.INVALID_INPUT)
                    nb_client.update_notebook(notebook_id, metadata=meta_obj, content=content_file)
                    format_success("Notebook updated", {"ID": notebook_id})
            else:
                if not meta_obj:
                    click.echo(
                        "✗ Nothing to update. Provide --metadata and/or --content.", err=True
                    )
                    sys.exit(ExitCodes.INVALID_INPUT)
                nb_client.update_notebook(notebook_id, metadata=meta_obj, content=None)
                format_success("Notebook updated", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="list")
    @click.option("--workspace", required=False, help="Workspace name to filter by (optional)")
    @click.option(
        "--take", default=25, show_default=True, help="Number of notebooks to show per page"
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        help="Output format: table or json",
    )
    def list_notebooks(workspace: str = "", take: int = 25, format: str = "table") -> None:
        """List all notebooks. Optionally filter by workspace.

        Args:
            workspace (str, optional): Workspace name to filter by.
            take (int, optional): Number of notebooks to show per page.
            format (str, optional): Output format (table or json).
        """
        try:
            nb_client = NotebookClient(configuration=get_http_configuration())
            ws_id = None
            if workspace:
                ws_id = validate_workspace_access(workspace, warn_on_error=True)
            query_args = {}
            if ws_id:
                query_args["workspace"] = ws_id
            filter_str = None
            if "workspace" in query_args:
                filter_str = f'workspace = "{query_args["workspace"]}"'
            query_obj = QueryNotebookRequest(filter=filter_str, take=take)
            try:
                notebooks_raw = _get_notebooks_from_query(nb_client, query_obj)
            except Exception as exc:
                click.echo(
                    f"✗ Warning: Validation error in PagedNotebooks response: {exc}. Some results may be skipped.",
                    err=True,
                )
                notebooks_raw = []
            # ...existing code...
            notebooks = []
            # Map workspace IDs to names for display
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}
            for idx, nb in enumerate(notebooks_raw):
                try:
                    nb_data = getattr(nb, "__dict__", {})
                    ws_id = nb_data.get("workspace", "")
                    ws_name = workspace_map.get(ws_id, ws_id)
                    name = nb_data.get("name", "")
                    nb_id = nb_data.get("id", "")
                    parameters = nb_data.get("parameters", {})
                    if not isinstance(parameters, dict):
                        parameters = {}
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
                if format.lower() == "json":
                    click.echo("[]")
                else:
                    click.echo("No notebooks found.")
                return

            # Handle output format
            if format.lower() == "json":
                click.echo(json.dumps(notebooks, indent=2))
            else:
                # Table output
                from tabulate import tabulate
                from click import style as cstyle

                def color_row(row):
                    ws = str(row[0])
                    ws_short = ws[:15] + ("…" if len(ws) > 15 else "")
                    return [
                        cstyle(ws_short, fg="blue"),
                        cstyle(str(row[1]), fg="green"),
                        cstyle(str(row[2]), fg="blue"),
                    ]

                table = []
                for nb in notebooks[:take]:
                    ws_name = nb.get("workspace", "")
                    name = nb.get("name", "")
                    nb_id = nb.get("id", "")
                    short_name = name[:40] + ("…" if len(name) > 40 else "")
                    table.append(color_row([ws_name, short_name, nb_id]))
                headers = [
                    cstyle("Workspace", fg="blue", bold=True),
                    cstyle("Name", fg="green", bold=True),
                    cstyle("Notebook ID", fg="blue", bold=True),
                ]
                click.echo(tabulate(table, headers=headers, tablefmt="github"))

                # Use continuation token for paging through notebooks (table output only)
                continuation_token = getattr(
                    nb_client.query_notebooks(query_obj), "continuation_token", None
                )
                while continuation_token:
                    if not click.confirm(f"Show next {take} notebooks?", default=True):
                        break
                    next_query = QueryNotebookRequest(
                        filter=filter_str, take=take, continuation_token=continuation_token
                    )
                    try:
                        next_notebooks_raw = _get_notebooks_from_query(nb_client, next_query)
                    except Exception as exc:
                        click.echo(
                            f"✗ Warning: Validation error in PagedNotebooks response: {exc}. Some results may be skipped.",
                            err=True,
                        )
                        next_notebooks_raw = []
                    next_notebooks = []
                    for idx, nb in enumerate(next_notebooks_raw):
                        nb_data = getattr(nb, "__dict__", {})
                        ws_id = nb_data.get("workspace", "")
                        ws_name = workspace_map.get(ws_id, ws_id)
                        name = nb_data.get("name", "")
                        nb_id = nb_data.get("id", "")
                        parameters = nb_data.get("parameters", {})
                        if not isinstance(parameters, dict):
                            parameters = {}
                        next_notebooks.append(
                            {
                                "workspace": ws_name,
                                "name": name,
                                "id": nb_id,
                                "parameters": parameters,
                            }
                        )
                    if not next_notebooks:
                        click.echo("No more notebooks found.")
                        break
                    table = []
                    for nb in next_notebooks:
                        ws_name = nb.get("workspace", "")
                        name = nb.get("name", "")
                        nb_id = nb.get("id", "")
                        short_name = name[:40] + ("…" if len(name) > 40 else "")
                        table.append(color_row([ws_name, short_name, nb_id]))
                    click.echo(tabulate(table, headers=headers, tablefmt="github"))
                    continuation_token = getattr(
                        nb_client.query_notebooks(next_query), "continuation_token", None
                    )
        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="download")
    @click.option("--id", "notebook_id", help="Notebook ID")
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
        """Download a notebook's content, metadata, or both by ID or name.

        Args:
            notebook_id (str, optional): Notebook ID.
            notebook_name (str, optional): Notebook name.
            workspace (str, optional): Workspace name.
            output (str, optional): Output file path.
            download_type (str, optional): What to download: content, metadata, or both.
        """
        if not notebook_id and not notebook_name:
            click.echo("✗ Must provide either --id or --name.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        ws_id = get_workspace_id_with_fallback(workspace)

        try:
            nb_client = NotebookClient(configuration=get_http_configuration())
            nb_name = notebook_name
            # Find notebook by name or id
            if notebook_name:
                filter_str = f'name = "{notebook_name}" and workspace = "{ws_id}"'
                query_obj = QueryNotebookRequest(filter=filter_str)
                results = _get_notebooks_from_query(nb_client, query_obj)
                found = next(
                    (nb for nb in results if getattr(nb, "name", None) == notebook_name), None
                )
                if not found:
                    click.echo(f"✗ Notebook named '{notebook_name}' not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
                notebook_id = getattr(found, "id", "")
                nb_name = getattr(found, "name", notebook_name)
            elif notebook_id:
                if not output:
                    filter_str = f'id = "{notebook_id}" and workspace = "{ws_id}"'
                    query_obj = QueryNotebookRequest(filter=filter_str)
                    results = _get_notebooks_from_query(nb_client, query_obj)
                    nb_name = getattr(results[0], "name", notebook_id) if results else notebook_id

            # Download notebook content and/or metadata using shared helper
            if not isinstance(notebook_id, str) or not notebook_id:
                click.echo("✗ Notebook ID must be a non-empty string.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)
            _download_notebook_content_and_metadata(
                nb_client, notebook_id, nb_name, output=output, download_type=download_type
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

        Args:
            input_file (str, optional): Path to notebook file to create.
            workspace (str, optional): Workspace name.
            notebook_name (str): Notebook name.
            download (bool, optional): Download notebook content and metadata after creation.

        Fails if a notebook with the same name exists.
        """
        ws_id = get_workspace_id_with_fallback(workspace)

        try:
            nb_client = NotebookClient(configuration=get_http_configuration())
            # Ensure the uploaded file has a .ipynb extension
            if not notebook_name.lower().endswith(".ipynb"):
                notebook_name += ".ipynb"
            # Check for existing notebook with same name in workspace
            filter_str = f'name = "{notebook_name}" and workspace = "{ws_id}"'
            query_obj = QueryNotebookRequest(filter=filter_str)
            results = _get_notebooks_from_query(nb_client, query_obj)
            if results:
                click.echo(
                    f"✗ A notebook named '{notebook_name}' already exists in this workspace. Creation cancelled.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            # No existing notebook, create new
            if input_file:
                with open(input_file, "rb") as content_file:
                    metadata = NotebookMetadata(name=notebook_name, workspace=ws_id)
                    result = nb_client.create_notebook(metadata=metadata, content=content_file)
                format_success("Notebook created", {"ID": result.id})
            else:
                # Create an empty notebook JSON structure using a temp file
                empty_nb = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}

                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ipynb")
                tmp.write(json.dumps(empty_nb).encode("utf-8"))
                tmp.close()
                with open(tmp.name, "rb") as content_file:
                    metadata = NotebookMetadata(name=notebook_name, workspace=ws_id)
                    result = nb_client.create_notebook(metadata=metadata, content=content_file)
                # Clean up temp file
                import os

                os.unlink(tmp.name)
                format_success("Notebook created", {"ID": result.id})

            # Download notebook content and metadata if requested
            if download:
                notebook_id = getattr(result, "id", None)
                if not notebook_id:
                    click.echo("✗ Notebook ID not found, cannot download.", err=True)
                    return
                _download_notebook_content_and_metadata(
                    nb_client, notebook_id, notebook_name, output=None, download_type="both"
                )
        except Exception as exc:
            handle_api_error(exc)

    @notebook.command(name="delete")
    @click.option("--id", "notebook_id", required=True, help="Notebook ID to delete")
    def delete_notebook(notebook_id: str = "") -> None:
        """Delete a notebook by ID.

        Args:
            notebook_id (str): Notebook ID to delete.
        """
        try:
            nb_client = NotebookClient(configuration=get_http_configuration())
            nb_client.delete_notebook(notebook_id)
            format_success("Notebook deleted", {"ID": notebook_id})
        except Exception as exc:
            handle_api_error(exc)

"""CLI commands for managing SystemLink notebooks via the artifact API."""

import click
import requests

from .utils import get_base_url, get_headers, get_ssl_verify, get_workspace_id_by_name


def register_notebook_commands(cli):
    """Register CLI commands for managing SystemLink notebooks."""

    @cli.group()
    def notebook():
        """Manage Jupyter notebooks as artifacts."""
        pass

    @notebook.command(name="update")
    @click.option("--id", "notebook_id", required=True, help="Notebook artifact ID to update")
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
        """Update notebook metadata and/or content."""
        import json

        if not metadata and not content:
            raise click.ClickException("Must provide at least one of --metadata or --content.")

        files = {}
        # Validate and add metadata if provided
        if metadata:
            with open(metadata, "r", encoding="utf-8") as f:
                meta_json = json.load(f)
            # Validate against notebook schema (required: name, workspace, etc.)
            if not isinstance(meta_json, dict):
                raise click.ClickException("Metadata must be a JSON object.")
            if not meta_json.get("name") or not isinstance(meta_json["name"], str):
                raise click.ClickException("Metadata must include a string 'name' field.")
            # workspace is required by schema, but allow user to omit if not moving workspaces
            if "workspace" in meta_json and not isinstance(meta_json["workspace"], str):
                raise click.ClickException("If present, 'workspace' must be a string.")
            if (
                "properties" in meta_json
                and meta_json["properties"] is not None
                and not isinstance(meta_json["properties"], dict)
            ):
                raise click.ClickException(
                    "If present, 'properties' must be a JSON object or null."
                )
            # Accept other fields (createdBy, updatedBy, etc.) as per schema
            files["metadata"] = ("metadata", json.dumps(meta_json), "application/json")

        # Add content if provided
        if content:
            with open(content, "rb") as f:
                content_bytes = f.read()
            files["content"] = (content, content_bytes, "application/octet-stream")

        if not files:
            raise click.ClickException("Nothing to update. Provide --metadata and/or --content.")

        url = f"{get_base_url()}/ninotebook/v1/notebook/{notebook_id}"
        resp = requests.put(
            url,
            headers=get_headers(),
            files=files,
            verify=get_ssl_verify(),
        )
        resp.raise_for_status()
        click.echo(f"Notebook updated for ID: {notebook_id}")
        pass

    @notebook.command(name="list")
    @click.option("--workspace", required=False, help="Workspace name to filter by (optional)")
    @click.option(
        "--take", default=25, show_default=True, help="Number of notebooks to show per page"
    )
    def list_notebooks(workspace, take):
        """List all notebook artifacts. Optionally filter by workspace."""
        payload = {"take": 1000, "filter": None}
        if workspace:
            try:
                ws_id = get_workspace_id_by_name(workspace)
                if not isinstance(ws_id, str):
                    raise ValueError("Workspace ID must be a string.")
            except Exception:
                raise click.ClickException(
                    f"Workspace '{workspace}' not found or invalid. Please provide a valid workspace name."
                )
            payload["filter"] = f'workspace = "{ws_id}"'
        url = f"{get_base_url()}/ninotebook/v1/notebook/query"
        try:
            from .utils import get_workspace_map

            workspace_map = get_workspace_map()
            resp = requests.post(
                url, headers=get_headers("application/json"), json=payload, verify=get_ssl_verify()
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("notebooks", []) if isinstance(data, dict) else []
            if not items:
                click.echo("No notebooks found.")
                return
            # Format as ASCII table
            from tabulate import tabulate
            from click import style as cstyle

            def color_row(row):
                # Truncate workspace name to max 15 characters
                ws = str(row[0])
                ws_short = ws[:15] + ("…" if len(ws) > 15 else "")
                # Color workspace blue, name green, id blue
                return [
                    cstyle(ws_short, fg="blue"),
                    cstyle(str(row[1]), fg="green"),
                    cstyle(str(row[2]), fg="blue"),
                ]

            table = []
            for nb in items[:take]:
                ws_name = workspace_map.get(nb.get("workspace", ""), nb.get("workspace", ""))
                name = nb.get("name", "")
                # Truncate name to max 40 characters
                short_name = name[:40] + ("…" if len(name) > 40 else "")
                table.append(color_row([ws_name, short_name, nb.get("id", "")]))
            headers = [
                cstyle("Workspace", fg="blue", bold=True),
                cstyle("Name", fg="green", bold=True),
                cstyle("Notebook ID", fg="blue", bold=True),
            ]
            click.echo(tabulate(table, headers=headers, tablefmt="github"))
            if len(items) > take:
                if click.confirm(
                    f"Show the remaining {len(items) - take} notebooks?", default=False
                ):
                    table = []
                    for nb in items[take:]:
                        ws_name = workspace_map.get(
                            nb.get("workspace", ""), nb.get("workspace", "")
                        )
                        name = nb.get("name", "")
                        short_name = name[:40] + ("…" if len(name) > 40 else "")
                        table.append(color_row([ws_name, short_name, nb.get("id", "")]))
                    click.echo(tabulate(table, headers=headers, tablefmt="github"))
        except Exception as exc:
            click.echo(f"Error: {exc}")
            raise click.ClickException(str(exc))

    @notebook.command(name="download")
    @click.option("--id", "notebook_id", help="Notebook artifact ID")
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
    def download_notebook(notebook_id, notebook_name, workspace, output, download_type):
        """Download a notebook's content, metadata, or both by ID or name."""
        import json

        if not notebook_id and not notebook_name:
            raise click.ClickException("Must provide either --id or --name.")
        try:
            ws_id = get_workspace_id_by_name(workspace)
        except Exception:
            ws_id = workspace
        nb_name = notebook_name
        if notebook_name:
            # Lookup ID by name using the notebook query API
            url = f"{get_base_url()}/ninotebook/v1/notebook/query"
            payload = {"take": 1000, "workspace": ws_id, "filter": f'name = "{notebook_name}"'}
            resp = requests.post(
                url, headers=get_headers("application/json"), json=payload, verify=get_ssl_verify()
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("notebooks", []) if isinstance(data, dict) else []
            found = next((nb for nb in items if nb.get("name") == notebook_name), None)
            if not found:
                raise click.ClickException(f"Notebook named '{notebook_name}' not found.")
            notebook_id = found["id"]
            nb_name = found.get("name", notebook_name)
        elif notebook_id:
            # Lookup name by id if output is not provided
            if not output:
                # Query notebook metadata to get the name
                url = f"{get_base_url()}/ninotebook/v1/notebook/query"
                payload = {"take": 1, "workspace": ws_id, "filter": f'id = "{notebook_id}"'}
                resp = requests.post(
                    url,
                    headers=get_headers("application/json"),
                    json=payload,
                    verify=get_ssl_verify(),
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("notebooks", []) if isinstance(data, dict) else []
                nb_name = items[0].get("name", notebook_id) if items else notebook_id

        # Download notebook content and/or metadata
        if download_type in ("content", "both"):
            url = f"{get_base_url()}/niapp/v1/webapps/{notebook_id}/content"
            resp = requests.get(
                url, headers=get_headers("application/json"), verify=get_ssl_verify()
            )
            resp.raise_for_status()
            # Always expect the user to provide the full .ipynb filename if using --output
            output_path = (
                output
                if output
                else (f"{nb_name}.ipynb" if not nb_name.endswith(".ipynb") else nb_name)
            )
            with open(output_path, "wb") as f:
                f.write(resp.content)
            click.echo(f"Notebook content downloaded to {output_path}")
        if download_type in ("metadata", "both"):
            url = f"{get_base_url()}/ninotebook/v1/notebook/{notebook_id}"
            resp = requests.get(
                url, headers=get_headers("application/json"), verify=get_ssl_verify()
            )
            resp.raise_for_status()
            meta = resp.json()
            meta_path = (
                (output or f"{nb_name}") + ".json"
                if download_type == "both"
                else (output or f"{nb_name}.json")
            )
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            click.echo(f"Notebook metadata downloaded to {meta_path}")

    @notebook.command(name="create")
    @click.option("--file", "input_file", required=False, help="Path to notebook file to create")
    @click.option("--workspace", default="Default", help="Workspace name (default: Default)")
    @click.option("--name", "notebook_name", required=True, help="Notebook name")
    def create_notebook(input_file, workspace, notebook_name):
        """Create a new notebook in the specified workspace.

        Fails if a notebook with the same name exists.
        """
        import json
        import os

        try:
            ws_id = get_workspace_id_by_name(workspace)
        except Exception:
            ws_id = workspace
        if not notebook_name and input_file:
            notebook_name = os.path.splitext(os.path.basename(input_file))[0]
        elif not notebook_name:
            notebook_name = "Untitled"
        # Ensure the uploaded file has a .ipynb extension
        if not notebook_name.lower().endswith(".ipynb"):
            notebook_name += ".ipynb"
        # Check for existing notebook with same name in workspace
        query_url = f"{get_base_url()}/ninotebook/v1/notebook/query"
        query_payload = {"take": 1, "workspace": ws_id, "filter": f'name = "{notebook_name}"'}
        resp = requests.post(
            query_url,
            headers=get_headers("application/json"),
            json=query_payload,
            verify=get_ssl_verify(),
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("notebooks", []) if isinstance(data, dict) else []
        if items:
            click.echo(
                f"A notebook named '{notebook_name}' already exists in this workspace. Creation cancelled."
            )
            return
        # No existing notebook, create new
        url = f"{get_base_url()}/ninotebook/v1/notebook"
        if input_file:
            with open(input_file, "rb") as f:
                content = f.read()
        else:
            # Create an empty notebook JSON structure
            empty_nb = {"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
            content = json.dumps(empty_nb).encode("utf-8")
        # Only include workspace in the metadata JSON, not as a separate form field
        metadata = {
            "name": notebook_name,
            "workspace": ws_id,
        }
        files = {
            "metadata": ("metadata", json.dumps(metadata), "application/json"),
            "content": (notebook_name, content, "application/octet-stream"),
        }
        # Omit Content-Type header by passing no argument
        resp = requests.post(
            url,
            headers=get_headers(),
            files=files,
            verify=get_ssl_verify(),
        )
        resp.raise_for_status()
        result = resp.json()
        click.echo(f"Notebook created. Artifact ID: {result.get('id')}")

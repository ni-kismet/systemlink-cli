"""CLI commands for managing SystemLink WebApps via the WebApp Service.

Provides local scaffolding (init), packing helpers (pack), and remote
management (list, get, delete, publish, open).
"""

import io
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import requests

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    get_web_url,
    get_headers,
    get_ssl_verify,
    get_workspace_id_with_fallback,
    get_workspace_map,
    handle_api_error,
    sanitize_filename,
)
from .workspace_utils import get_workspace_display_name


def _get_webapp_base_url() -> str:
    return f"{get_base_url()}/niapp/v1"


def _query_webapps_http(filter_str: str, max_items: int = 1000) -> List[Dict[str, Any]]:
    """Query webapps using continuation token pagination.

    Args:
        filter_str: Filter string for the query (server syntax)
        max_items: Maximum number of items to retrieve in total

    Returns:
        List of webapp dicts
    """
    base = _get_webapp_base_url()
    headers = get_headers("application/json")

    all_items: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    # Choose a reasonable page size for server-side paging
    page_size = 100
    if max_items and max_items < page_size:
        page_size = max_items

    while True:
        payload: Dict[str, Any] = {
            "take": page_size,
            "orderBy": "updated",
            "orderByDescending": True,
        }
        if filter_str:
            payload["filter"] = filter_str
        if continuation_token:
            payload["continuationToken"] = continuation_token

        # Request the server to include a total count when available
        resp = requests.post(
            f"{base}/webapps/query?includeTotalCount=true",
            headers=headers,
            json=payload,
            verify=get_ssl_verify(),
        )
        resp.raise_for_status()
        data = resp.json()
        page_items: List[Dict[str, Any]] = data.get("webapps", []) if isinstance(data, dict) else []

        for it in page_items:
            all_items.append(it)

        # Stop if we've reached max_items
        if max_items and len(all_items) >= max_items:
            return all_items[:max_items]

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_items


def _fetch_webapps_page(
    filter_str: str, take: int = 100, continuation_token: Optional[str] = None
) -> tuple:
    """Fetch a single page of webapps from the server.

    Returns a tuple: (items, continuationToken, total)
    """
    base = _get_webapp_base_url()
    headers = get_headers("application/json")

    payload: Dict[str, Any] = {"take": take, "orderBy": "updated", "orderByDescending": True}
    if filter_str:
        payload["filter"] = filter_str
    if continuation_token:
        payload["continuationToken"] = continuation_token

    # Request the server to include a total count when available
    resp = requests.post(
        f"{base}/webapps/query?includeTotalCount=true",
        headers=headers,
        json=payload,
        verify=get_ssl_verify(),
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("webapps", []) if isinstance(data, dict) else []
    cont = data.get("continuationToken")
    total = data.get("totalCount")

    return items, cont, total


def _pack_folder_to_nipkg(folder: Path, output: Optional[Path] = None) -> Path:
    """Pack a folder into a .nipkg (ar) file and return the output path.

    The .nipkg produced by this helper uses a Debian-style ar layout with
    three members: debian-binary, control.tar.gz and data.tar.gz. The
    implementation writes the ar archive directly; long member names are
    truncated to 16 bytes (simple strategy) which is acceptable for our
    use-case but could be extended to support GNU longname tables if
    needed.
    """
    if not folder.exists() or not folder.is_dir():
        raise click.ClickException(f"Folder not found: {folder}")

    if output is None:
        output = folder.with_suffix(".nipkg")

    # Ensure parent exists
    output.parent.mkdir(parents=True, exist_ok=True)
    # Debian-style package layout inside an ar archive:
    # - debian-binary (contains version string, e.g. "2.0\n")
    # - control.tar.gz (contains a control file with package metadata)
    # - data.tar.gz (contains the payload files)

    # Derive package metadata from folder name where possible.
    pkg_name = sanitize_filename(folder.name)
    version = "1.0.0"
    architecture = "all"
    if "_" in folder.name:
        first, rest = folder.name.split("_", 1)
        pkg_name = sanitize_filename(first)
        rest_parts = rest.split("_")
        if rest_parts:
            version = rest_parts[0]
        if len(rest_parts) > 1:
            architecture = "_".join(rest_parts[1:])

    control_fields = {
        "Package": pkg_name,
        "Version": version,
        "Architecture": architecture,
        "Maintainer": "slcli <no-reply@example.com>",
        "Description": f"Package created by slcli for {pkg_name}",
    }

    control_lines = [f"{k}: {v}" for k, v in control_fields.items()]
    control_content = ("\n".join(control_lines) + "\n").encode("utf-8")

    # Create control.tar.gz in-memory containing a single file 'control'
    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="control")
        ti.size = len(control_content)
        ti.mtime = int(time.time())
        tf.addfile(ti, io.BytesIO(control_content))
    control_bytes = control_buf.getvalue()

    # Create data.tar.gz in-memory containing the folder contents at the root
    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:gz") as dtf:
        # tarfile.add will handle directories and files; preserve relative paths
        dtf.add(str(folder), arcname=".")
    data_bytes = data_buf.getvalue()

    # debian-binary content
    debian_bin = b"2.0\n"

    # Write an ar archive (the Debian .deb format) but use .nipkg extension
    def _ar_header(
        name: str,
        size: int,
        mtime: Optional[int] = None,
        uid: int = 0,
        gid: int = 0,
        mode: int = 0o100644,
    ) -> bytes:
        if mtime is None:
            mtime = int(time.time())
        # Header fields: name(16) mtime(12) uid(6) gid(6) mode(8) size(10) magic(2)
        name_field = name.encode("utf-8")
        if len(name_field) > 16:
            # use truncated name (simple strategy)
            name_field = name_field[:16]
        header = (
            name_field.ljust(16, b" ")
            + str(int(mtime)).encode("ascii").ljust(12, b" ")
            + str(int(uid)).encode("ascii").ljust(6, b" ")
            + str(int(gid)).encode("ascii").ljust(6, b" ")
            + oct(mode)[2:].encode("ascii").ljust(8, b" ")
            + str(int(size)).encode("ascii").ljust(10, b" ")
            + b"`\n"
        )
        return header

    with open(output, "wb") as out_f:
        # Global header
        out_f.write(b"!<arch>\n")

        # debian-binary
        out_f.write(_ar_header("debian-binary", len(debian_bin)))
        out_f.write(debian_bin)
        if len(debian_bin) % 2:
            out_f.write(b"\n")

        # control.tar.gz
        out_f.write(_ar_header("control.tar.gz", len(control_bytes)))
        out_f.write(control_bytes)
        if len(control_bytes) % 2:
            out_f.write(b"\n")

        # data.tar.gz
        out_f.write(_ar_header("data.tar.gz", len(data_bytes)))
        out_f.write(data_bytes)
        if len(data_bytes) % 2:
            out_f.write(b"\n")

    return output


def register_webapp_commands(cli: Any) -> None:
    """Register CLI commands for SystemLink webapps."""

    @cli.group()
    def webapp() -> None:  # pragma: no cover - Click wiring
        """Manage web applications (init/pack locally, publish/CRUD remotely)."""

    @webapp.command(name="init")
    @click.option(
        "--directory",
        "directory",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        default=Path.cwd(),
        show_default="CWD",
        help="Target directory to create example index.html",
    )
    @click.option("--force", is_flag=True, help="Overwrite existing files")
    def init_webapp(directory: Path, force: bool) -> None:
        """Scaffold a sample webapp (index.html)."""
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Create a subfolder named 'app' and put the example index.html inside it
            target_folder = directory / "app"
            target_folder.mkdir(parents=True, exist_ok=True)
            index = target_folder / "index.html"
            if index.exists() and not force:
                click.echo("✗ app/index.html already exists. Use --force to overwrite.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            content = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <title>Example WebApp</title>
  </head>
  <body>
    <h1>Example WebApp</h1>
    <p>Created with slcli webapp init</p>
  </body>
</html>
"""
            index.write_text(content, encoding="utf-8")
            format_success("Created example index.html", {"Path": str(index)})
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="pack")
    @click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
    @click.option(
        "--output",
        "output",
        type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
        default=None,
        help="Output .nipkg file path",
    )
    def pack_cmd(folder: Path, output: Optional[Path]) -> None:
        """Pack a folder into a .nipkg."""
        try:
            out = Path(output) if output else None
            result = _pack_folder_to_nipkg(folder, out)
            format_success("Packed folder", {"Path": str(result)})
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="list")
    @click.option(
        "--workspace", "-w", "workspace", default="", help="Filter by workspace name or ID"
    )
    @click.option(
        "--filter",
        "filter_text",
        default="",
        help="Case-insensitive substring match on name",
    )
    @click.option("--take", "take", type=int, default=25, show_default=True, help="Max rows/page")
    @click.option(
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_webapps(workspace: str, filter_text: str, take: int, format_output: str) -> None:
        """List webapps."""
        try:

            # Validate and normalize format option
            format_output = validate_output_format(format_output)

            # Determine how many items to request from the API
            if format_output.lower() == "json":
                # For JSON output we want to return all matching items (no
                # interactive pagination). Use a falsy api_take (0) to indicate
                # "fetch all" to the helper.
                api_take = 0
            else:
                api_take = take if take != 25 else 1000
            # Use server-side query to only retrieve WebVI documents
            base_filter = 'type == "WebVI"'
            if workspace:
                ws_id = get_workspace_id_with_fallback(workspace)
                # add workspace constraint to filter
                base_filter = f'{base_filter} and workspace == "{ws_id}"'

            if filter_text:
                term = filter_text.lower().replace("\\", "\\\\").replace('"', '\\"')
                name_clause = f'name.ToLower().Contains("{term}")'
                base_filter = f"({base_filter}) and ({name_clause})"

            # If the user requested JSON output or did not request a specific take,
            # fetch all matching items (using server-side paging). Otherwise, if
            # the user specified a take and wants table output, perform interactive
            # server-side paging: fetch a page, show total (if available), and offer
            # to fetch the next page(s).
            webapps: List[Dict[str, Any]] = []
            if format_output.lower() == "json" or take == 0:
                webapps = _query_webapps_http(base_filter, max_items=api_take)
            else:
                # Interactive server-side paging: show each fetched page immediately
                # using the same display formatting so the user sees the first page
                # before being prompted to fetch the next one.
                cont: Optional[str] = None
                first_page = True

                # Prepare workspace map once for display name resolution
                try:
                    workspace_map = get_workspace_map()
                except Exception:
                    workspace_map = {}

                from .universal_handlers import FilteredResponse

                def _format_page_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                    page_items: List[Dict[str, Any]] = []
                    for wa in raw_items:
                        if wa.get("type", "") != "WebVI":
                            continue
                        ws_name = get_workspace_display_name(wa.get("workspace", ""), workspace_map)
                        page_items.append(
                            {
                                "id": wa.get("id", ""),
                                "name": wa.get("name", ""),
                                "workspace": ws_name,
                                "type": wa.get("type", ""),
                            }
                        )
                    return page_items

                while True:
                    raw_page, cont, total = _fetch_webapps_page(base_filter, take, cont)

                    # Format and display this page immediately
                    page_display_items = _format_page_items(raw_page)

                    # Track how many items we've displayed so far and, if the
                    # server provided a total, show a concise summary like:
                    # "Showing 25 of 556 webapp(s). 531 more available."
                    if "shown_count" not in locals():
                        shown_count = 0
                    shown_count += len(page_display_items)

                    # We now delegate printing the "Showing X of Y..." summary
                    # to the UniversalResponseHandler so behavior matches other
                    # list commands (e.g., notebooks). Supply total_count and
                    # shown_count to enable that summary.
                    first_page = False

                    # Use the UniversalResponseHandler to display this page (no internal pagination)
                    def formatter(item: Dict[str, Any]) -> List[str]:
                        return [
                            item.get("name", ""),
                            item.get("workspace", ""),
                            item.get("id", ""),
                            item.get("type", ""),
                        ]

                    UniversalResponseHandler.handle_list_response(
                        resp=FilteredResponse({"webapps": page_display_items}),
                        data_key="webapps",
                        item_name="webapp",
                        format_output=format_output,
                        formatter_func=formatter,
                        headers=["Name", "Workspace", "ID", "Type"],
                        column_widths=[40, 30, 36, 16],
                        empty_message="No webapps found.",
                        enable_pagination=False,
                        page_size=take,
                        total_count=total,
                        shown_count=shown_count,
                    )
                    # Flush stdout so that the rendered table is visible before prompting
                    try:
                        sys.stdout.flush()
                    except Exception:
                        pass

                    # Accumulate raw items so callers that expect an aggregated
                    # list (or further processing) can see all fetched pages.
                    webapps.extend(raw_page)

                    # If there's no continuation token, we're done
                    if not cont:
                        break

                    # Ask the user if they want to fetch the next set
                    if not click.confirm("Show next set of results?", default=True):
                        break

                # We've already displayed each page interactively above; avoid
                # rendering a second, aggregated table below. Return early.
                return

            # Map workspace ids
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            items: List[Dict[str, Any]] = []
            for wa in webapps:
                # Only include WebVI documents
                if wa.get("type", "") != "WebVI":
                    continue
                ws_name = get_workspace_display_name(wa.get("workspace", ""), workspace_map)
                items.append(
                    {
                        "id": wa.get("id", ""),
                        "name": wa.get("name", ""),
                        "workspace": ws_name,
                        "type": wa.get("type", ""),
                    }
                )

            from .universal_handlers import FilteredResponse

            def formatter(item: Dict[str, Any]) -> List[str]:
                return [
                    item.get("name", ""),
                    item.get("workspace", ""),
                    item.get("id", ""),
                    item.get("type", ""),
                ]

            UniversalResponseHandler.handle_list_response(
                resp=FilteredResponse({"webapps": items}),
                data_key="webapps",
                item_name="webapp",
                format_output=format_output,
                formatter_func=formatter,
                headers=["Name", "Workspace", "ID", "Type"],
                column_widths=[40, 30, 36, 16],
                empty_message="No webapps found.",
                enable_pagination=True,
                page_size=take,
            )
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="get")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to retrieve")
    @click.option(
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
    )
    def get_webapp(webapp_id: str, format_output: str) -> None:
        """Show webapp metadata."""
        try:
            base = _get_webapp_base_url()
            resp = requests.get(
                f"{base}/webapps/{webapp_id}",
                headers=get_headers("application/json"),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("type", "") != "WebVI":
                click.echo("✗ Webapp is not a WebVI document.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)
            UniversalResponseHandler.handle_get_response(resp, "webapp", format_output)
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="delete")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to delete")
    @click.confirmation_option(prompt="Are you sure you want to delete this webapp?")
    def delete_webapp(webapp_id: str) -> None:
        """Delete a webapp."""
        try:
            base = _get_webapp_base_url()
            resp = requests.delete(
                f"{base}/webapps/{webapp_id}", headers=get_headers(), verify=get_ssl_verify()
            )
            # Validate response and type if possible
            try:
                data = resp.json()
                if data.get("type", "") != "WebVI":
                    click.echo("✗ Webapp is not a WebVI document.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
            except Exception:
                # If no JSON, continue and let handler report success/failure
                pass

            # Use UniversalResponseHandler to print a friendly message
            UniversalResponseHandler.handle_delete_response(resp, "webapp", item_count=1)
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="open")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to open in browser")
    def open_webapp(webapp_id: str) -> None:
        """Open a webapp in the browser."""
        import webbrowser
        from urllib.parse import quote

        try:
            base = _get_webapp_base_url()
            resp = requests.get(
                f"{base}/webapps/{webapp_id}",
                headers=get_headers("application/json"),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            data = resp.json()
            # Try to construct the public webapps URL which looks like:
            # https://<host>/webapps/app/<WorkspaceName>/<Name>
            name = data.get("name")
            workspace_id = data.get("workspace")

            # Resolve workspace display name
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            workspace_name = get_workspace_display_name(workspace_id or "", workspace_map)

            # If we have both a workspace name and webapp name, build the friendly URL
            if workspace_name and name:
                # Prefer explicit web UI URL, otherwise derive from API URL
                web_base = get_web_url()
                # Ensure no trailing slash on base
                web_base = web_base.rstrip("/")

                app_path = f"/webapps/app/{quote(workspace_name)}/{quote(name)}"
                app_url = f"{web_base}{app_path}"
                webbrowser.open(app_url)
                click.echo(f"✓ Opening: {app_url}")
                return

            # Fallback: try any embed/url/interface property
            props = data.get("properties", {}) or {}
            url = props.get("embedLocation") or props.get("url") or props.get("interface")
            if url:
                webbrowser.open(url)
                click.echo(f"✓ Opening: {url}")
                return

            # Last-resort fallback: open content endpoint (may require auth)
            content_url = f"{base}/webapps/{webapp_id}/content"
            webbrowser.open(content_url)
            click.echo("✓ Opening content endpoint (may require authentication in browser)")
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="publish")
    @click.argument(
        "source",
        type=click.Path(exists=True, path_type=Path),
    )
    @click.option(
        "--id",
        "-i",
        "webapp_id",
        default="",
        help="Existing webapp ID to upload content to",
    )
    @click.option(
        "--name",
        "-n",
        "name",
        default="",
        help="Create a new webapp with this name before publishing",
    )
    @click.option(
        "--workspace",
        "-w",
        "workspace",
        default="Default",
        help="Workspace name or ID for new webapp",
    )
    def publish(source: Path, webapp_id: str, name: str, workspace: str) -> None:
        """Publish a .nipkg (or folder) to the WebApp service.

        SOURCE may be a .nipkg file or a folder. If a folder is provided it will be
        packed into a .nipkg archive prior to upload.
        """
        tmp_file: Optional[Path] = None
        try:
            # If folder, pack it first using a context-managed TemporaryDirectory
            if source.is_dir():
                click.echo("Packing folder into .nipkg...")
                # Keep the TemporaryDirectory alive for the duration of the
                # metadata creation and upload so the packaged file remains
                # available. The context manager will ensure cleanup afterwards.
                with tempfile.TemporaryDirectory() as _tmp_dir:
                    tmp_dir = Path(_tmp_dir)
                    suggested = tmp_dir / (sanitize_filename(source.name) + ".nipkg")
                    packaged = _pack_folder_to_nipkg(source, suggested)
                    tmp_file = packaged

                    # If no webapp id provided create webapp metadata using name
                    base = _get_webapp_base_url()
                    if not webapp_id:
                        if not name:
                            click.echo("✗ Must provide --id or --name to publish.", err=True)
                            sys.exit(ExitCodes.INVALID_INPUT)
                        ws_id = get_workspace_id_with_fallback(workspace)
                        payload = {
                            "name": name,
                            "type": "WebVI",
                            "workspace": ws_id,
                            "policyIds": [],
                            "properties": {},
                        }
                        resp_create = requests.post(
                            f"{base}/webapps",
                            headers=get_headers("application/json"),
                            json=payload,
                            verify=get_ssl_verify(),
                        )
                        resp_create.raise_for_status()
                        created = resp_create.json()
                        webapp_id = created.get("id")
                        if not webapp_id:
                            click.echo("✗ Failed to create webapp metadata.", err=True)
                            sys.exit(ExitCodes.GENERAL_ERROR)
                        click.echo(f"✓ Created webapp metadata: {webapp_id}")

                    # Upload content (binary). Use requests.put because content may be binary.
                    with open(packaged, "rb") as f:  # type: ignore[arg-type]
                        data = f.read()

                    upload_headers = get_headers("application/octet-stream")
                    url = f"{base}/webapps/{webapp_id}/content"
                    resp = requests.put(
                        url, headers=upload_headers, data=data, verify=get_ssl_verify()
                    )
                    if resp.status_code in (200, 201, 204):
                        format_success(
                            "Published webapp content",
                            {"Webapp ID": webapp_id, "Source": str(packaged)},
                        )
                    else:
                        # Try to show body message
                        try:
                            click.echo(resp.text, err=True)
                        except Exception:
                            pass
                        click.echo("✗ Failed to upload content.", err=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                packaged = source

                # If no webapp id provided create webapp metadata using name
                base = _get_webapp_base_url()
                if not webapp_id:
                    if not name:
                        click.echo("✗ Must provide --id or --name to publish.", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                    ws_id = get_workspace_id_with_fallback(workspace)
                    payload = {
                        "name": name,
                        "type": "WebVI",
                        "workspace": ws_id,
                        "policyIds": [],
                        "properties": {},
                    }
                    resp_create = requests.post(
                        f"{base}/webapps",
                        headers=get_headers("application/json"),
                        json=payload,
                        verify=get_ssl_verify(),
                    )
                    resp_create.raise_for_status()
                    created = resp_create.json()
                    webapp_id = created.get("id")
                    if not webapp_id:
                        click.echo("✗ Failed to create webapp metadata.", err=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
                    click.echo(f"✓ Created webapp metadata: {webapp_id}")

                # Upload content (binary). Use requests.put because content may be binary.
                with open(packaged, "rb") as f:  # type: ignore[arg-type]
                    data = f.read()

                upload_headers = get_headers("application/octet-stream")
                url = f"{base}/webapps/{webapp_id}/content"
                resp = requests.put(url, headers=upload_headers, data=data, verify=get_ssl_verify())
                if resp.status_code in (200, 201, 204):
                    format_success(
                        "Published webapp content",
                        {"Webapp ID": webapp_id, "Source": str(packaged)},
                    )
                else:
                    # Try to show body message
                    try:
                        click.echo(resp.text, err=True)
                    except Exception:
                        pass
                    click.echo("✗ Failed to upload content.", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

            # No further action here; upload is handled in the branches above
            # (inside the TemporaryDirectory for folders, or in the file branch).

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)
        finally:
            # Cleanup temporary packaged file if we created one and it still exists.
            # In the common case the TemporaryDirectory context manager removes the
            # file for us when it exits; however, if something unusual happened and
            # the file remains, attempt to remove it here.
            try:
                if tmp_file and tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass

"""CLI commands for managing SystemLink files."""

import json
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .cli_utils import validate_output_format
from .universal_handlers import UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import resolve_workspace_filter


def _get_file_service_url() -> str:
    """Get the file service base URL."""
    return f"{get_base_url()}/nifile/v1/service-groups/Default"


def _format_file_size(size_bytes: Optional[int]) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string
    """
    if size_bytes is None:
        return "N/A"

    size: float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def _format_timestamp(timestamp: Optional[str]) -> str:
    """Format ISO timestamp to readable format.

    Args:
        timestamp: ISO format timestamp string

    Returns:
        Formatted date string or N/A
    """
    if not timestamp:
        return "N/A"
    try:
        # Parse ISO format and return just the date/time part
        return timestamp[:19].replace("T", " ")
    except Exception:
        return timestamp


def _get_file_name(file_item: dict) -> str:
    """Extract file name from file metadata.

    The API stores the filename in properties['Name'].

    Args:
        file_item: File metadata dictionary

    Returns:
        File name or 'Unknown'
    """
    properties = file_item.get("properties", {})
    return properties.get("Name", "Unknown")


def _get_file_size(file_item: dict) -> Optional[int]:
    """Get file size, preferring size64 for large files.

    Args:
        file_item: File metadata dictionary

    Returns:
        File size in bytes or None
    """
    size64 = file_item.get("size64")
    if size64 is not None:
        return size64
    size = file_item.get("size")
    # size == -1 means the file is larger than 32-bit int
    if size is not None and size >= 0:
        return size
    return None


def _get_file_by_id(file_id: str) -> Optional[dict]:
    """Get file metadata by ID using query-files-linq endpoint.

    The API doesn't have a GET /files/{id} endpoint, so we use
    query-files-linq with an ID filter instead.

    Args:
        file_id: The file ID to look up

    Returns:
        File metadata dictionary or None if not found
    """
    url = f"{_get_file_service_url()}/query-files-linq"
    payload = {
        "filter": f'id = "{file_id}"',
        "take": 1,
    }
    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()
    files = data.get("availableFiles", [])
    if files:
        return files[0]
    return None


def register_file_commands(cli: Any) -> None:
    """Register the 'file' command group and its subcommands."""

    @cli.group()
    def file() -> None:
        """Manage files in SystemLink File Service."""
        pass

    @file.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of files to return",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--id-filter",
        help="Filter by file IDs (comma-separated)",
    )
    @click.option(
        "--filter",
        "name_filter",
        help="Filter by file name or extension (contains search)",
    )
    def list_files(
        format: str = "table",
        take: int = 25,
        workspace: Optional[str] = None,
        id_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
    ) -> None:
        """List files in the File Service.

        Use --filter to search for files by name or extension.
        """
        format_output = validate_output_format(format)

        # Use search-files endpoint for better performance
        url = f"{_get_file_service_url()}/search-files"

        try:
            # Resolve workspace name to ID if needed
            workspace_id = None
            if workspace:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Build search filter
            filter_parts = []

            if workspace_id:
                filter_parts.append(f'workspaceId:("{workspace_id}")')

            if id_filter:
                # Split comma-separated IDs
                ids = [f'"{id.strip()}"' for id in id_filter.split(",")]
                id_list = " OR ".join(ids)
                filter_parts.append(f"id:({id_list})")

            if name_filter:
                # Search by name or extension contains using wildcard syntax
                filter_parts.append(f'(name:("*{name_filter}*") OR extension:("*{name_filter}*"))')

            # For JSON format, respect the take parameter exactly
            if format_output.lower() == "json":
                api_take = take
            else:
                api_take = take if take != 25 else 1000

            # Build request payload for search-files endpoint
            payload: Dict[str, Any] = {
                "take": api_take,
                "orderBy": "updated",
                "orderByDescending": True,
            }

            if filter_parts:
                payload["filter"] = " AND ".join(filter_parts)

            resp = make_api_request("POST", url, payload=payload)

            def file_formatter(file_item: dict) -> list:
                name = _get_file_name(file_item)
                file_id = file_item.get("id", "")
                size = _format_file_size(_get_file_size(file_item))
                created = _format_timestamp(file_item.get("created"))
                return [name, file_id, size, created]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="availableFiles",
                item_name="file",
                format_output=format_output,
                formatter_func=file_formatter,
                headers=["Name", "ID", "Size", "Created"],
                column_widths=[35, 36, 12, 20],
                empty_message="No files found.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="get")
    @click.argument("file_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_file(file_id: str, format: str = "table") -> None:
        """Get metadata for a specific file.

        FILE_ID is the unique identifier of the file.
        """
        format_output = validate_output_format(format)

        try:
            data = _get_file_by_id(file_id)

            if data is None:
                click.echo(f"✗ File not found: {file_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            if format_output.lower() == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                # Display file metadata in a readable format
                file_name = _get_file_name(data)
                click.echo(f"\n{'=' * 60}")
                click.echo(f"  File: {file_name}")
                click.echo(f"{'=' * 60}")
                click.echo(f"  ID:          {data.get('id', 'N/A')}")
                click.echo(f"  Size:        {_format_file_size(_get_file_size(data))}")
                click.echo(f"  Created:     {_format_timestamp(data.get('created'))}")
                click.echo(f"  Workspace:   {data.get('workspace', 'N/A')}")
                click.echo(f"  Service Grp: {data.get('serviceGroup', 'N/A')}")

                # Show properties if present
                properties = data.get("properties", {})
                if properties:
                    click.echo(f"\n  Properties:")
                    for key, value in properties.items():
                        click.echo(f"    {key}: {value}")

                click.echo(f"{'=' * 60}\n")

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="upload")
    @click.argument("file_path", type=click.Path(exists=True))
    @click.option(
        "--workspace",
        "-w",
        help="Target workspace name or ID",
    )
    @click.option(
        "--name",
        "-n",
        help="Custom name for the uploaded file (defaults to filename)",
    )
    @click.option(
        "--properties",
        "-p",
        help="JSON string of properties to attach to the file",
    )
    def upload_file(
        file_path: str,
        workspace: Optional[str] = None,
        name: Optional[str] = None,
        properties: Optional[str] = None,
    ) -> None:
        """Upload a file to the File Service.

        FILE_PATH is the local path to the file to upload.
        """
        file_path_obj = Path(file_path)
        file_name = name if name else file_path_obj.name
        file_size = file_path_obj.stat().st_size

        url = f"{_get_file_service_url()}/upload-files"

        # Resolve workspace name to ID and build query string
        if workspace:
            workspace_map = get_workspace_map()
            workspace_id = resolve_workspace_filter(workspace, workspace_map)
            url += f"?workspace={workspace_id}"

        try:
            # Parse properties if provided
            props_dict: Dict[str, str] = {}
            if properties:
                try:
                    props_dict = json.loads(properties)
                except json.JSONDecodeError as e:
                    click.echo(f"✗ Invalid JSON for properties: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

            # Build metadata for the file - Name goes in properties
            # The API stores filename in properties['Name']
            metadata: Dict[str, Any] = {
                "Name": file_name,
            }
            # Merge any additional properties
            metadata.update(props_dict)

            # Prepare multipart form data
            # The API expects 'file' field for file content and metadata as JSON
            with open(file_path, "rb") as f:
                files = {
                    "file": (file_name, f, "application/octet-stream"),
                }
                # Add metadata as form field (JSON dict of key/value pairs)
                data = {
                    "metadata": json.dumps(metadata),
                }

                # Make request with multipart form data
                resp = make_api_request("POST", url, payload=None, files=files, data=data)

            result = resp.json()

            # The API returns a URI like '/nifile/v1/service-groups/Default/files/{id}'
            # Extract the file ID from the URI
            uri = result.get("uri", "")
            file_id = uri.split("/")[-1] if uri else "N/A"

            format_success(
                "File uploaded successfully",
                {
                    "ID": file_id,
                    "Name": file_name,
                    "Size": _format_file_size(file_size),
                },
            )

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="download")
    @click.argument("file_id")
    @click.option(
        "--output",
        "-o",
        type=click.Path(),
        help="Output file path (defaults to original filename in current directory)",
    )
    @click.option(
        "--force",
        is_flag=True,
        help="Overwrite existing file without prompting",
    )
    def download_file(
        file_id: str,
        output: Optional[str] = None,
        force: bool = False,
    ) -> None:
        """Download a file from the File Service.

        FILE_ID is the unique identifier of the file to download.
        """
        try:
            # First get file metadata to determine filename
            metadata = _get_file_by_id(file_id)
            if metadata is None:
                click.echo(f"✗ File not found: {file_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            original_name = _get_file_name(metadata)
            if original_name == "Unknown":
                original_name = f"file_{file_id}"

            # Determine output path
            if output:
                output_path = Path(output)
            else:
                output_path = Path.cwd() / original_name

            # Check if file exists
            if output_path.exists() and not force:
                if not click.confirm(f"File '{output_path}' already exists. Overwrite?"):
                    click.echo("Download cancelled.")
                    sys.exit(ExitCodes.SUCCESS)

            # Download file content
            download_url = f"{_get_file_service_url()}/files/{file_id}/data"
            resp = make_api_request("GET", download_url, payload=None, stream=True)

            # Write to file
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            format_success(
                "File downloaded successfully",
                {
                    "Path": str(output_path),
                    "Size": _format_file_size(output_path.stat().st_size),
                },
            )

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="delete")
    @click.argument("file_id")
    @click.option(
        "--force",
        is_flag=True,
        help="Delete without confirmation",
    )
    def delete_file(file_id: str, force: bool = False) -> None:
        """Delete a file from the File Service.

        FILE_ID is the unique identifier of the file to delete.
        """
        try:
            # Get file info first using query (no GET endpoint exists)
            metadata = _get_file_by_id(file_id)
            if metadata is None:
                click.echo(f"✗ File not found: {file_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            file_name = _get_file_name(metadata)
            if file_name == "Unknown":
                file_name = file_id

            if not force:
                if not click.confirm(f"Are you sure you want to delete '{file_name}'?"):
                    click.echo("Delete cancelled.")
                    sys.exit(ExitCodes.SUCCESS)

            # Delete the file
            delete_url = f"{_get_file_service_url()}/files/{file_id}"
            make_api_request("DELETE", delete_url, payload=None)

            format_success("File deleted", {"Name": file_name, "ID": file_id})

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="query")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of files to return",
    )
    @click.option(
        "--filter",
        "filter_query",
        help="Search filter expression (e.g., 'name:(\"*test*\")')",
    )
    @click.option(
        "--order-by",
        help="Order by field (e.g., 'updated', 'created', 'name')",
    )
    @click.option(
        "--descending/--ascending",
        default=True,
        help="Sort order (default: descending)",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    def query_files(
        format: str = "table",
        take: int = 25,
        filter_query: Optional[str] = None,
        order_by: Optional[str] = None,
        descending: bool = True,
        workspace: Optional[str] = None,
    ) -> None:
        r"""Query files using search expressions.

        Filter syntax uses field:(value) format with wildcards:
        \b
          - name:("*test*")         Files with 'test' in the name
          - extension:("csv")       Files with .csv extension
          - workspaceId:("id")      Files in a specific workspace
          - id:("file-id")          Files with specific ID
        \b
        Combine filters with AND/OR:
          - name:("*test*") AND extension:("csv")
        """
        format_output = validate_output_format(format)

        # Use search-files endpoint for better performance
        url = f"{_get_file_service_url()}/search-files"

        try:
            # Build request body
            query_body: Dict[str, Any] = {
                "take": take if format_output.lower() == "json" else (take if take != 25 else 1000),
                "orderByDescending": descending,
            }

            # Build filter parts
            filter_parts = []

            if filter_query:
                filter_parts.append(filter_query)

            # Resolve workspace name to ID if needed
            if workspace:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace, workspace_map)
                filter_parts.append(f'workspaceId:("{workspace_id}")')

            if filter_parts:
                query_body["filter"] = " AND ".join(filter_parts)

            if order_by:
                query_body["orderBy"] = order_by
            else:
                query_body["orderBy"] = "updated"

            resp = make_api_request("POST", url, payload=query_body)

            def file_formatter(file_item: dict) -> list:
                name = _get_file_name(file_item)
                file_id = file_item.get("id", "")
                size = _format_file_size(_get_file_size(file_item))
                created = _format_timestamp(file_item.get("created"))
                return [name, file_id, size, created]

            UniversalResponseHandler.handle_list_response(
                resp=resp,
                data_key="availableFiles",
                item_name="file",
                format_output=format_output,
                formatter_func=file_formatter,
                headers=["Name", "ID", "Size", "Created"],
                column_widths=[35, 36, 12, 20],
                empty_message="No files match the query.",
                enable_pagination=True,
                page_size=take,
            )

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="update-metadata")
    @click.argument("file_id")
    @click.option(
        "--name",
        "-n",
        help="New name for the file",
    )
    @click.option(
        "--properties",
        "-p",
        help="JSON string of properties to set (replaces existing)",
    )
    @click.option(
        "--add-property",
        multiple=True,
        help="Add/update a property (format: key=value). Can be used multiple times.",
    )
    def update_metadata(
        file_id: str,
        name: Optional[str] = None,
        properties: Optional[str] = None,
        add_property: tuple = (),
    ) -> None:
        """Update metadata for a file.

        FILE_ID is the unique identifier of the file to update.
        """
        update_url = f"{_get_file_service_url()}/files/{file_id}/update-metadata"

        try:
            # Get current metadata using query endpoint
            current_data = _get_file_by_id(file_id)
            if current_data is None:
                click.echo(f"✗ File not found: {file_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            current_props = current_data.get("properties", {}).copy()

            # Build update payload - API requires replaceExisting and properties
            update_props: Dict[str, str] = {}

            # If renaming, set the Name property
            if name:
                update_props["Name"] = name

            # Handle properties
            if properties:
                try:
                    props_input = json.loads(properties)
                    update_props.update(props_input)
                except json.JSONDecodeError as e:
                    click.echo(f"✗ Invalid JSON for properties: {e}", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)
            elif add_property:
                # Start with existing properties and add/update
                update_props = current_props.copy()
                if name:
                    update_props["Name"] = name
                for prop in add_property:
                    if "=" in prop:
                        key, value = prop.split("=", 1)
                        update_props[key.strip()] = value.strip()
                    else:
                        click.echo(f"✗ Invalid property format: {prop}. Use key=value", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
            elif name:
                # Just renaming - merge with existing properties
                update_props = current_props.copy()
                update_props["Name"] = name

            if not update_props:
                click.echo("✗ No updates specified. Use --name, --properties, or --add-property.")
                sys.exit(ExitCodes.INVALID_INPUT)

            # Build the request body per API spec
            update_body: Dict[str, Any] = {
                "replaceExisting": True,
                "properties": update_props,
            }

            # Update the file metadata using POST to /update-metadata endpoint
            make_api_request("POST", update_url, payload=update_body)

            format_success(
                "File metadata updated",
                {"ID": file_id, "Name": update_props.get("Name", current_props.get("Name", "N/A"))},
            )

        except Exception as exc:
            handle_api_error(exc)

    @file.command(name="watch")
    @click.argument("watch_dir", type=click.Path(exists=True, file_okay=False))
    @click.option(
        "--workspace",
        "-w",
        help="Target workspace name or ID for uploaded files",
    )
    @click.option(
        "--move-to",
        type=click.Path(file_okay=False),
        help="Directory to move files after successful upload",
    )
    @click.option(
        "--delete-after-upload",
        is_flag=True,
        help="Delete files after successful upload (mutually exclusive with --move-to)",
    )
    @click.option(
        "--pattern",
        "-p",
        default="*",
        show_default=True,
        help="Glob pattern for files to watch (e.g., '*.csv')",
    )
    @click.option(
        "--debounce",
        type=float,
        default=1.0,
        show_default=True,
        help="Seconds to wait before uploading (debounce file writes)",
    )
    @click.option(
        "--recursive",
        "-r",
        is_flag=True,
        help="Watch subdirectories recursively",
    )
    def watch_folder(
        watch_dir: str,
        workspace: Optional[str] = None,
        move_to: Optional[str] = None,
        delete_after_upload: bool = False,
        pattern: str = "*",
        debounce: float = 1.0,
        recursive: bool = False,
    ) -> None:
        """Watch a folder and upload new files automatically.

        WATCH_DIR is the directory to watch for new files.

        Files will be uploaded to the File Service when they are created or modified.
        Use --move-to to move files after upload, or --delete-after-upload to remove them.
        """
        # Validate mutual exclusivity
        if move_to and delete_after_upload:
            click.echo("✗ Cannot use both --move-to and --delete-after-upload", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        # Resolve workspace name to ID if needed
        workspace_id: Optional[str] = None
        if workspace:
            workspace_map = get_workspace_map()
            workspace_id = resolve_workspace_filter(workspace, workspace_map)

        # Create move-to directory if specified
        if move_to:
            move_to_path = Path(move_to)
            move_to_path.mkdir(parents=True, exist_ok=True)

        try:
            # Try to import watchdog
            from watchdog.events import FileSystemEventHandler  # type: ignore[import-not-found]
            from watchdog.observers import Observer  # type: ignore[import-not-found]
        except ImportError:
            click.echo(
                "✗ The 'watchdog' package is required for the watch command.\n"
                "  Install it with: pip install watchdog",
                err=True,
            )
            sys.exit(ExitCodes.GENERAL_ERROR)

        import fnmatch

        watch_path = Path(watch_dir).resolve()

        # Track pending uploads with debounce
        pending_uploads: Dict[str, float] = {}
        pending_lock = threading.Lock()

        def upload_file_async(file_path: Path) -> None:
            """Upload a file and handle post-upload actions."""
            try:
                file_name = file_path.name
                file_size = file_path.stat().st_size

                url = f"{_get_file_service_url()}/upload-files"
                if workspace_id:
                    url += f"?workspace={workspace_id}"

                # Metadata uses 'Name' property for filename
                metadata: Dict[str, Any] = {"Name": file_name}

                with open(file_path, "rb") as f:
                    files = {"file": (file_name, f, "application/octet-stream")}
                    data = {"metadata": json.dumps(metadata)}
                    resp = make_api_request("POST", url, payload=None, files=files, data=data)

                result = resp.json()
                # Extract file ID from the URI in response
                uri = result.get("uri", "")
                uploaded_file_id = uri.split("/")[-1] if uri else "N/A"

                click.echo(
                    f"✓ Uploaded: {file_name} "
                    f"({_format_file_size(file_size)}) -> ID: {uploaded_file_id}"
                )

                # Handle post-upload action
                if move_to:
                    dest_path = Path(move_to) / file_name
                    shutil.move(str(file_path), str(dest_path))
                    click.echo(f"  → Moved to: {dest_path}")
                elif delete_after_upload:
                    file_path.unlink()
                    click.echo(f"  → Deleted: {file_path}")

            except Exception as e:
                click.echo(f"✗ Failed to upload {file_path.name}: {e}", err=True)

        def process_pending_uploads() -> None:
            """Process pending uploads after debounce period."""
            while True:
                time.sleep(0.5)
                current_time = time.time()
                to_upload: List[str] = []

                with pending_lock:
                    for path, timestamp in list(pending_uploads.items()):
                        if current_time - timestamp >= debounce:
                            to_upload.append(path)

                    for path in to_upload:
                        del pending_uploads[path]

                for path in to_upload:
                    file_path = Path(path)
                    if file_path.exists() and file_path.is_file():
                        upload_file_async(file_path)

        class FileUploadHandler(FileSystemEventHandler):  # type: ignore[misc]
            """Handler for file system events."""

            def on_created(self, event: Any) -> None:
                if event.is_directory:
                    return
                self._handle_file(event.src_path)

            def on_modified(self, event: Any) -> None:
                if event.is_directory:
                    return
                self._handle_file(event.src_path)

            def _handle_file(self, file_path: str) -> None:
                path = Path(file_path)

                # Ignore dot files (e.g., .DS_Store, .gitignore)
                if path.name.startswith("."):
                    return

                # Check pattern match
                if not fnmatch.fnmatch(path.name, pattern):
                    return

                with pending_lock:
                    pending_uploads[file_path] = time.time()

        # Start the upload processor thread
        upload_thread = threading.Thread(target=process_pending_uploads, daemon=True)
        upload_thread.start()

        # Set up file watcher
        event_handler = FileUploadHandler()
        observer = Observer()
        observer.schedule(event_handler, str(watch_path), recursive=recursive)
        observer.start()

        click.echo(f"Watching: {watch_path}")
        click.echo(f"Pattern: {pattern}")
        if workspace:
            click.echo(f"Target workspace: {workspace}")
        if move_to:
            click.echo(f"Move after upload: {move_to}")
        elif delete_after_upload:
            click.echo("Delete after upload: enabled")
        click.echo("\nPress Ctrl+C to stop watching...\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            click.echo("\n\nStopping file watcher...")
            observer.stop()
            observer.join()
            click.echo("File watcher stopped.")

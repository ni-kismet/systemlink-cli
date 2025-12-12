"""CLI commands for managing NI Package Manager feeds.

This module provides commands for managing package feeds in SystemLink,
supporting both SLE (/nifeed/v1) and SLS (/nirepo/v1) APIs.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import requests

from .cli_utils import validate_output_format
from .platform import PLATFORM_SLS, get_platform
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    get_workspace_id_with_fallback,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import get_workspace_display_name, get_workspace_map


class JobPollingError(Exception):
    """Raised when a job fails or cannot be retrieved."""


class JobNotFoundError(Exception):
    """Raised when a job is not found."""


class PackageUploadError(Exception):
    """Raised when a package upload response is missing required identifiers."""


def _get_feed_base_url() -> str:
    """Get the base URL for feed API.

    Returns platform-specific URL:
    - SLS (SystemLink Server): /nirepo/v1
    - SLE (SystemLink Enterprise): /nifeed/v1
    """
    if get_platform() == PLATFORM_SLS:
        return f"{get_base_url()}/nirepo/v1"
    return f"{get_base_url()}/nifeed/v1"


def _normalize_platform(platform: str) -> str:
    """Normalize platform value based on current SystemLink platform.

    SLE uses uppercase (WINDOWS, NI_LINUX_RT), SLS uses lowercase (windows, ni-linux-rt).
    CLI accepts either case and normalizes appropriately.

    Args:
        platform: Platform string (case-insensitive)

    Returns:
        Normalized platform string for the current API
    """
    platform_lower = platform.lower().replace("_", "-")
    is_sls = get_platform() == PLATFORM_SLS

    if platform_lower in ("windows", "win"):
        return "windows" if is_sls else "WINDOWS"
    elif platform_lower in ("ni-linux-rt", "ni_linux_rt", "linux-rt", "linux_rt", "linuxrt"):
        return "ni-linux-rt" if is_sls else "NI_LINUX_RT"
    else:
        # Return as-is for unknown platforms
        return platform.lower() if is_sls else platform.upper()


def _get_feed_name_field() -> str:
    """Get the feed name field based on platform.

    SLS uses 'feedName', SLE uses 'name'.
    """
    return "feedName" if get_platform() == PLATFORM_SLS else "name"


def _extract_feed_name(feed: Dict[str, Any]) -> str:
    """Extract feed name from response, handling both SLE and SLS formats."""
    return feed.get("name") or feed.get("feedName") or "Unknown"


def _wait_for_job(
    job_id: str, timeout: int = 300, poll_interval: int = 2, feed_id: Optional[str] = None
) -> Dict[str, Any]:
    """Wait for an async job to complete.

    Args:
        job_id: The job ID to wait for
        timeout: Maximum time to wait in seconds
        poll_interval: Time between status checks in seconds
        feed_id: Optional feed ID for feed-specific jobs

    Returns:
        Final job status dictionary

    Raises:
        TimeoutError: If job doesn't complete within timeout
        Exception: If job fails
    """
    base_url = _get_feed_base_url()
    if feed_id:
        url = f"{base_url}/feeds/{feed_id}/jobs/{job_id}"
    else:
        url = f"{base_url}/jobs/{job_id}"
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Job {job_id} did not complete within {timeout} seconds")

        try:
            resp = make_api_request("GET", url, handle_errors=False)
            data = resp.json()

            # Handle both response formats: {job: {...}} or direct {...}
            job = data.get("job", data)
            status = job.get("status", "").upper()

            if status in ("SUCCESS", "SUCCEEDED", "COMPLETED"):
                return job
            if status in ("FAILED", "ERROR"):
                error = job.get("error", {})
                error_msg = error.get("message", "Unknown error")
                raise JobPollingError(f"Job failed: {error_msg}")
            if status in ("COMPLETED_WITH_ERROR",):
                # Partial success - return but with warning
                click.echo("⚠️ Job completed with errors", err=True)
                return job

            # Still processing - wait and retry
            time.sleep(poll_interval)

        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                raise JobNotFoundError(f"Job {job_id} not found")
            raise
        except requests.RequestException:
            raise


def _list_feeds(
    platform: Optional[str] = None, workspace_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List all feeds, optionally filtered by platform and workspace.

    Args:
        platform: Optional platform filter (windows or ni-linux-rt)
        workspace_id: Optional workspace ID filter

    Returns:
        List of feed dictionaries
    """
    base_url = _get_feed_base_url()

    # Build query parameters
    params = []
    if platform:
        normalized_platform = _normalize_platform(platform)
        params.append(f"platform={normalized_platform}")
    if workspace_id:
        params.append(f"workspace={workspace_id}")

    url = f"{base_url}/feeds"
    if params:
        url += "?" + "&".join(params)

    try:
        resp = make_api_request("GET", url)
        data = resp.json()
        return data.get("feeds", [])
    except Exception as exc:
        handle_api_error(exc)
        return []


def _get_feed(feed_id: str) -> Dict[str, Any]:
    """Get a single feed by ID.

    Args:
        feed_id: Feed ID

    Returns:
        Feed dictionary
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/feeds/{feed_id}"

    resp = make_api_request("GET", url)
    data = resp.json()
    # Handle both response formats: {feed: {...}} or direct {...}
    return data.get("feed", data)


def _create_feed(
    name: str, platform: str, description: Optional[str] = None, workspace: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new feed.

    Args:
        name: Feed name
        platform: Target platform (windows or ni-linux-rt)
        description: Optional feed description
        workspace: Optional workspace ID

    Returns:
        Response dictionary containing job ID or feed details
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/feeds"

    # Build payload with platform-specific field names
    name_field = _get_feed_name_field()
    payload: Dict[str, Any] = {
        name_field: name,
        "platform": _normalize_platform(platform),
    }

    if description:
        payload["description"] = description
    if workspace:
        payload["workspace"] = workspace

    resp = make_api_request("POST", url, payload=payload)
    return resp.json()


def _delete_feed(feed_id: str) -> str:
    """Delete a feed.

    Args:
        feed_id: Feed ID to delete

    Returns:
        Job ID for the async operation
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/feeds/{feed_id}"

    resp = make_api_request("DELETE", url)

    if resp.status_code == 204 or not resp.content:
        return ""

    data = resp.json()
    return data.get("jobId", data.get("job", {}).get("id", ""))


def _replicate_feed(
    name: str,
    platform: str,
    source_url: str,
    description: Optional[str] = None,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Replicate a feed from an external source.

    Args:
        name: Name for the new feed
        platform: Target platform
        source_url: URL of the source feed to replicate
        description: Optional description
        workspace: Optional workspace ID

    Returns:
        Response dictionary containing job ID or feed details
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/replicate-feed"

    # Build payload
    name_field = _get_feed_name_field()
    payload: Dict[str, Any] = {
        name_field: name,
        "platform": _normalize_platform(platform),
        "urls": [source_url],
    }

    if description:
        payload["description"] = description
    if workspace:
        payload["workspace"] = workspace

    resp = make_api_request("POST", url, payload=payload)
    return resp.json()


def _list_packages(feed_id: str) -> List[Dict[str, Any]]:
    """List all packages in a feed.

    Args:
        feed_id: Feed ID

    Returns:
        List of package dictionaries
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/feeds/{feed_id}/packages"

    resp = make_api_request("GET", url)
    data = resp.json()
    return data.get("packages", [])


def _upload_package_sle(feed_id: str, file_path: str, overwrite: bool = False) -> Dict[str, Any]:
    """Upload a package to a feed on SLE.

    SLE uploads directly to the feed.

    Args:
        feed_id: Feed ID
        file_path: Path to the package file
        overwrite: Whether to overwrite existing package

    Returns:
        Response dictionary containing job ID or package details
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/feeds/{feed_id}/packages"
    if overwrite:
        url += "?shouldOverwrite=true"

    file_name = Path(file_path).name
    with open(file_path, "rb") as f:
        files = {"package": (file_name, f, "application/octet-stream")}
        resp = make_api_request("POST", url, files=files)

    return resp.json()


def _upload_package_sls(feed_id: str, file_path: str, overwrite: bool = False) -> Dict[str, Any]:
    """Upload a package on SLS.

    SLS uploads to the package pool first, then adds reference to feed.

    Note: Even when the CLI command is invoked without ``--wait``, this helper must block on the
    initial upload job to obtain the package ID before the feed association step can be queued.

    Args:
        feed_id: Feed ID
        file_path: Path to the package file
        overwrite: Whether to overwrite existing package

    Returns:
        Response dictionary containing job ID and package ID
    """
    base_url = _get_feed_base_url()

    # Step 1: Upload to package pool
    upload_url = f"{base_url}/upload-packages"
    if overwrite:
        upload_url += "?shouldOverwrite=true"

    file_name = Path(file_path).name
    with open(file_path, "rb") as f:
        files = {"package": (file_name, f, "application/octet-stream")}
        resp = make_api_request("POST", upload_url, files=files)

    data = resp.json()
    job_ids = data.get("jobIds", [])

    if not job_ids:
        raise PackageUploadError("No job ID returned from package upload")

    # Wait for upload to complete to get package ID
    job = _wait_for_job(job_ids[0], timeout=300)
    package_id = job.get("resourceId")

    if not package_id:
        raise PackageUploadError("Package upload completed but no package ID returned")

    # Step 2: Add package reference to feed
    ref_url = f"{base_url}/feeds/{feed_id}/add-package-references"
    ref_payload = {"packageReferences": [package_id]}
    resp = make_api_request("POST", ref_url, payload=ref_payload)

    data = resp.json()
    # Inject packageId into response for CLI usage
    result = data.copy()
    result["packageId"] = package_id
    return result


def _upload_package(feed_id: str, file_path: str, overwrite: bool = False) -> Dict[str, Any]:
    """Upload a package to a feed.

    Routes to platform-specific implementation.

    Args:
        feed_id: Feed ID
        file_path: Path to the package file
        overwrite: Whether to overwrite existing package

    Returns:
        Response dictionary containing job ID or package details
    """
    if get_platform() == PLATFORM_SLS:
        return _upload_package_sls(feed_id, file_path, overwrite)
    return _upload_package_sle(feed_id, file_path, overwrite)


def _delete_package(package_id: str) -> str:
    """Delete a package.

    Args:
        package_id: Package ID to delete

    Returns:
        Job ID for the async operation
    """
    base_url = _get_feed_base_url()
    url = f"{base_url}/delete-packages"
    payload = {"packageIds": [package_id]}

    resp = make_api_request("POST", url, payload=payload)

    if resp.status_code == 204 or not resp.content:
        return ""

    data = resp.json()
    return data.get("jobId", data.get("job", {}).get("id", ""))


def register_feed_commands(cli: Any) -> None:
    """Register the 'feed' command group and its subcommands."""

    @cli.group()
    def feed() -> None:
        """Manage NI Package Manager feeds.

        Feeds are package repositories that can be used by NI Package Manager
        to install software on test systems. Supports both Windows (.nipkg)
        and NI Linux RT (.ipk/.deb) platforms.
        """
        pass

    # -------------------------------------------------------------------------
    # Feed management commands
    # -------------------------------------------------------------------------

    @feed.command(name="list")
    @click.option(
        "--format",
        "-f",
        "format_",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    @click.option("--take", "-t", type=int, default=25, show_default=True, help="Items per page")
    @click.option(
        "--platform",
        "-p",
        type=click.Choice(["windows", "ni-linux-rt"], case_sensitive=False),
        help="Filter by platform",
    )
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    def list_feeds(
        format_: str, take: int, platform: Optional[str], workspace: Optional[str]
    ) -> None:
        """List all feeds."""
        format_output = validate_output_format(format_)

        try:
            workspace_id = None
            if workspace:
                workspace_id = get_workspace_id_with_fallback(workspace)

            feeds = _list_feeds(platform=platform, workspace_id=workspace_id)
            workspace_map = get_workspace_map()

            def feed_formatter(f: Dict[str, Any]) -> List[str]:
                ws_name = get_workspace_display_name(f.get("workspace", ""), workspace_map)
                return [
                    _extract_feed_name(f),
                    f.get("platform", "").lower(),
                    f.get("id", ""),
                    ws_name,
                ]

            mock_resp: Any = FilteredResponse({"feeds": feeds})

            UniversalResponseHandler.handle_list_response(
                resp=mock_resp,
                data_key="feeds",
                item_name="feed",
                format_output=format_output,
                formatter_func=feed_formatter,
                headers=["Name", "Platform", "ID", "Workspace"],
                column_widths=[30, 12, 36, 20],
                empty_message="No feeds found.",
                enable_pagination=True,
                page_size=take,
            )
        except Exception as exc:
            handle_api_error(exc)

    @feed.command(name="get")
    @click.option("--id", "-i", "feed_id", required=True, help="Feed ID")
    @click.option(
        "--format",
        "-f",
        "format_",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    def get_feed(feed_id: str, format_: str) -> None:
        """Get details of a specific feed."""
        format_output = validate_output_format(format_)

        try:
            feed_data = _get_feed(feed_id)

            if format_output == "json":
                click.echo(json.dumps(feed_data, indent=2))
                return

            workspace_map = get_workspace_map()
            ws_name = get_workspace_display_name(feed_data.get("workspace", ""), workspace_map)

            click.echo("Feed Details:")
            click.echo("=" * 50)
            click.echo(f"ID:          {feed_data.get('id', 'N/A')}")
            click.echo(f"Name:        {_extract_feed_name(feed_data)}")
            click.echo(f"Platform:    {feed_data.get('platform', 'N/A')}")
            click.echo(f"Workspace:   {ws_name}")
            click.echo(f"Description: {feed_data.get('description', 'N/A')}")
            click.echo(f"Directory:   {feed_data.get('directoryUri', 'N/A')}")
            click.echo(f"Ready:       {feed_data.get('ready', 'N/A')}")
            click.echo(f"Updated:     {feed_data.get('lastUpdated', 'N/A')}")

            # Show package sources if available
            sources = feed_data.get("packageSources", [])
            if sources:
                click.echo(f"\nPackage Sources ({len(sources)}):")
                for src in sources[:5]:  # Limit display
                    click.echo(f"  - {src}")
                if len(sources) > 5:
                    click.echo(f"  ... and {len(sources) - 5} more")

        except Exception as exc:
            handle_api_error(exc)

    @feed.command(name="create")
    @click.option("--name", "-n", required=True, help="Feed name")
    @click.option(
        "--platform",
        "-p",
        required=True,
        type=click.Choice(["windows", "ni-linux-rt"], case_sensitive=False),
        help="Target platform",
    )
    @click.option("--description", "-d", help="Feed description")
    @click.option("--workspace", "-w", help="Workspace name or ID")
    @click.option("--wait", is_flag=True, help="Wait for operation to complete")
    @click.option("--timeout", type=int, default=300, help="Timeout in seconds when using --wait")
    def create_feed(
        name: str,
        platform: str,
        description: Optional[str],
        workspace: Optional[str],
        wait: bool,
        timeout: int,
    ) -> None:
        """Create a new feed."""
        try:
            workspace_id = None
            if workspace:
                workspace_id = get_workspace_id_with_fallback(workspace)

            result = _create_feed(
                name=name,
                platform=platform,
                description=description,
                workspace=workspace_id,
            )

            job_id = result.get("jobId", result.get("job", {}).get("id"))

            if wait:
                if job_id:
                    click.echo(f"Creating feed '{name}'... (job: {job_id})")
                    job = _wait_for_job(job_id, timeout=timeout)
                    feed_id = job.get("resourceId", "")
                else:
                    # Synchronous creation
                    feed_id = result.get("id", "")

                format_success("Feed created", {"ID": feed_id, "Name": name})
            else:
                if job_id:
                    format_success("Feed creation started", {"Job ID": job_id, "Name": name})
                else:
                    feed_id = result.get("id", "")
                    format_success("Feed created", {"ID": feed_id, "Name": name})

        except TimeoutError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

    @feed.command(name="delete")
    @click.option("--id", "-i", "feed_id", required=True, help="Feed ID to delete")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    @click.option("--wait", is_flag=True, help="Wait for operation to complete")
    @click.option("--timeout", type=int, default=300, help="Timeout in seconds when using --wait")
    def delete_feed(feed_id: str, yes: bool, wait: bool, timeout: int) -> None:
        """Delete a feed and all its packages."""
        if not yes:
            if not click.confirm(f"Are you sure you want to delete feed {feed_id}?"):
                click.echo("Cancelled.")
                return

        try:
            job_id = _delete_feed(feed_id)

            if not job_id:
                format_success("Feed deleted", {"ID": feed_id})
                return

            if wait:
                click.echo(f"Deleting feed... (job: {job_id})")
                _wait_for_job(job_id, timeout=timeout)
                format_success("Feed deleted", {"ID": feed_id})
            else:
                format_success("Feed deletion started", {"Job ID": job_id, "Feed ID": feed_id})

        except TimeoutError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

    @feed.command(name="replicate")
    @click.option("--name", "-n", required=True, help="Name for the new feed")
    @click.option(
        "--platform",
        "-p",
        required=True,
        type=click.Choice(["windows", "ni-linux-rt"], case_sensitive=False),
        help="Target platform",
    )
    @click.option("--url", "-u", required=True, help="Source feed URL to replicate from")
    @click.option("--description", "-d", help="Feed description")
    @click.option("--workspace", "-w", help="Workspace name or ID")
    @click.option("--wait", is_flag=True, help="Wait for operation to complete")
    @click.option("--timeout", type=int, default=600, help="Timeout in seconds when using --wait")
    def replicate_feed(
        name: str,
        platform: str,
        url: str,
        description: Optional[str],
        workspace: Optional[str],
        wait: bool,
        timeout: int,
    ) -> None:
        """Replicate a feed from an external source URL."""
        try:
            workspace_id = None
            if workspace:
                workspace_id = get_workspace_id_with_fallback(workspace)

            result = _replicate_feed(
                name=name,
                platform=platform,
                source_url=url,
                description=description,
                workspace=workspace_id,
            )

            job_id = result.get("jobId", result.get("job", {}).get("id"))

            if wait:
                if job_id:
                    click.echo(f"Replicating feed from {url}... (job: {job_id})")
                    click.echo("This may take several minutes for large feeds.")
                    job = _wait_for_job(job_id, timeout=timeout)
                    feed_id = job.get("resourceId", "")
                else:
                    feed_id = result.get("id", "")

                format_success("Feed replicated", {"ID": feed_id, "Name": name})
            else:
                if job_id:
                    format_success(
                        "Feed replication started",
                        {"Job ID": job_id, "Name": name, "Source": url},
                    )
                else:
                    feed_id = result.get("id", "")
                    format_success("Feed replicated", {"ID": feed_id, "Name": name})

        except TimeoutError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

    # -------------------------------------------------------------------------
    # Package subgroup
    # -------------------------------------------------------------------------

    @feed.group(name="package")
    def package() -> None:
        """Manage packages within feeds."""
        pass

    @package.command(name="list")
    @click.option("--feed-id", "-f", required=True, help="Feed ID")
    @click.option(
        "--format",
        "format_",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    @click.option("--take", "-t", type=int, default=25, show_default=True, help="Items per page")
    def list_packages(feed_id: str, format_: str, take: int) -> None:
        """List all packages in a feed."""
        format_output = validate_output_format(format_)

        try:
            packages = _list_packages(feed_id)

            def package_formatter(p: Dict[str, Any]) -> List[str]:
                metadata = p.get("metadata", {})
                return [
                    metadata.get("packageName", p.get("id", "")[:20]),
                    metadata.get("version", "N/A"),
                    metadata.get("architecture", "N/A"),
                    p.get("id", ""),
                ]

            mock_resp: Any = FilteredResponse({"packages": packages})

            UniversalResponseHandler.handle_list_response(
                resp=mock_resp,
                data_key="packages",
                item_name="package",
                format_output=format_output,
                formatter_func=package_formatter,
                headers=["Name", "Version", "Architecture", "ID"],
                column_widths=[30, 20, 15, 36],
                empty_message="No packages found in this feed.",
                enable_pagination=True,
                page_size=take,
            )
        except Exception as exc:
            handle_api_error(exc)

    @package.command(name="upload")
    @click.option("--feed-id", "-f", required=True, help="Feed ID to upload to")
    @click.option("--file", "-i", "file_path", required=True, help="Path to package file")
    @click.option("--overwrite", is_flag=True, help="Overwrite existing package")
    @click.option(
        "--wait",
        is_flag=True,
        help=(
            "Wait for the final association job to finish (SLS still waits for initial pool upload)."
        ),
    )
    @click.option("--timeout", type=int, default=300, help="Timeout in seconds when using --wait")
    def upload_package(
        feed_id: str, file_path: str, overwrite: bool, wait: bool, timeout: int
    ) -> None:
        """Upload a package to a feed."""
        # Validate file exists
        path = Path(file_path)
        if not path.exists():
            click.echo(f"✗ File not found: {file_path}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        if not path.is_file():
            click.echo(f"✗ Not a file: {file_path}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            platform_value = get_platform()
            if platform_value == PLATFORM_SLS and not wait:
                click.echo(
                    "Note: SLS uploads wait for the initial package pool upload even without --wait.",
                    err=False,
                )

            result = _upload_package(feed_id, file_path, overwrite)
            job_id = result.get("jobId", result.get("job", {}).get("id", ""))

            if wait:
                if job_id:
                    click.echo(f"Uploading {path.name}... (job: {job_id})")
                    try:
                        job = _wait_for_job(job_id, timeout=timeout, feed_id=feed_id)
                        package_id = job.get("resourceId", "")
                    except JobNotFoundError:
                        # If job is gone but we have a package ID (e.g. SLS), assume success
                        pkg_id_from_start = result.get("packageId")
                        if pkg_id_from_start:
                            package_id = pkg_id_from_start
                            click.echo(
                                "⚠️ Job not found, but package ID is known. Assuming success.",
                                err=True,
                            )
                        else:
                            raise
                else:
                    # Synchronous success
                    package_id = result.get("id", result.get("packageId", ""))

                format_success("Package uploaded", {"ID": package_id, "File": path.name})
            else:
                if job_id:
                    format_success("Package upload started", {"Job ID": job_id, "File": path.name})
                else:
                    package_id = result.get("id", result.get("packageId", ""))
                    format_success("Package uploaded", {"ID": package_id, "File": path.name})

        except TimeoutError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

    @package.command(name="delete")
    @click.option("--id", "-i", "package_id", required=True, help="Package ID to delete")
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    @click.option("--wait", is_flag=True, help="Wait for operation to complete")
    @click.option("--timeout", type=int, default=300, help="Timeout in seconds when using --wait")
    def delete_package(package_id: str, yes: bool, wait: bool, timeout: int) -> None:
        """Delete a package from the repository."""
        if not yes:
            if not click.confirm(f"Are you sure you want to delete package {package_id}?"):
                click.echo("Cancelled.")
                return

        try:
            job_id = _delete_package(package_id)

            if wait:
                if job_id:
                    click.echo(f"Deleting package... (job: {job_id})")
                    _wait_for_job(job_id, timeout=timeout)
                format_success("Package deleted", {"ID": package_id})
            else:
                if job_id:
                    format_success(
                        "Package deletion started", {"Job ID": job_id, "Package ID": package_id}
                    )
                else:
                    format_success("Package deleted", {"ID": package_id})

        except TimeoutError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

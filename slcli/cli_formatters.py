"""Unified table formatters for all CLI resource types."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


def format_templates_table(template: Dict[str, Any]) -> List[str]:
    """Format template data for table display."""
    name = template.get("name", "Unknown")
    version = template.get("version", "N/A")
    created = _format_timestamp(template.get("createdTimestamp"))
    status = template.get("status", "Unknown")

    return [name, version, created, status]


def format_users_table(user: Dict[str, Any]) -> List[str]:
    """Format user data for table display."""
    username = user.get("username", "Unknown")
    email = user.get("email", "N/A")
    role = user.get("role", "N/A")
    status = "Active" if user.get("enabled", True) else "Disabled"

    return [username, email, role, status]


def format_workflows_table(workflow: Dict[str, Any]) -> List[str]:
    """Format workflow data for table display."""
    name = workflow.get("name", "Unknown")
    status = workflow.get("status", "Unknown")
    last_run = _format_timestamp(workflow.get("lastRunTimestamp"))
    duration = _format_duration(workflow.get("lastRunDuration"))

    return [name, status, last_run, duration]


def format_notebooks_table(notebook: Dict[str, Any]) -> List[str]:
    """Format notebook data for table display."""
    name = notebook.get("name", "Unknown")
    notebook_type = notebook.get("type", "Unknown")
    modified = _format_timestamp(notebook.get("modifiedTimestamp"))
    size = _format_file_size(notebook.get("size", 0))

    return [name, notebook_type, modified, size]


def format_workspaces_table(workspace: Dict[str, Any]) -> List[str]:
    """Format workspace data for table display."""
    name = workspace.get("name", "Unknown")
    workspace_type = workspace.get("type", "Unknown")
    file_count = str(workspace.get("fileCount", 0))
    modified = _format_timestamp(workspace.get("modifiedTimestamp"))

    return [name, workspace_type, file_count, modified]


def format_dff_files_table(file_info: Dict[str, Any]) -> List[str]:
    """Format DFF file data for table display."""
    name = file_info.get("name", "Unknown")
    size = _format_file_size(file_info.get("size", 0))
    modified = _format_timestamp(file_info.get("modifiedTimestamp"))
    file_type = file_info.get("type", "file").title()

    return [name, size, modified, file_type]


def format_dff_data_table(data_info: Dict[str, Any]) -> List[str]:
    """Format DFF data entry for table display."""
    id_val = data_info.get("id", "Unknown")
    name = data_info.get("name", "N/A")
    created = _format_timestamp(data_info.get("createdTimestamp"))
    size = _format_file_size(data_info.get("size", 0))

    return [id_val, name, created, size]


def format_tags_table(tag: Dict[str, Any]) -> List[str]:
    """Format tag data for table display."""
    name = tag.get("name", "Unknown")
    tag_type = tag.get("type", "Unknown")
    count = str(tag.get("dataCount", 0))
    created = _format_timestamp(tag.get("createdTimestamp"))

    return [name, tag_type, count, created]


def format_systems_table(system: Dict[str, Any]) -> List[str]:
    """Format system data for table display."""
    name = system.get("name", "Unknown")
    status = system.get("status", "Unknown")
    ip_address = system.get("ipAddress", "N/A")
    last_seen = _format_timestamp(system.get("lastSeenTimestamp"))

    return [name, status, ip_address, last_seen]


def format_assets_table(asset: Dict[str, Any]) -> List[str]:
    """Format asset data for table display."""
    name = asset.get("name", "Unknown")
    asset_type = asset.get("type", "Unknown")
    location = asset.get("location", "N/A")
    status = asset.get("status", "Unknown")

    return [name, asset_type, location, status]


def _format_timestamp(timestamp: Any) -> str:
    """Format timestamp for table display."""
    if not timestamp:
        return "N/A"

    try:
        if isinstance(timestamp, str):
            # Handle ISO format timestamps
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        elif isinstance(timestamp, (int, float)):
            # Handle Unix timestamps
            dt = datetime.fromtimestamp(timestamp)
        else:
            return "N/A"

        # Return relative time if recent, otherwise date
        now = datetime.now()
        diff = now - dt.replace(tzinfo=None)

        if diff.days == 0:
            return dt.strftime("%H:%M")
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return dt.strftime("%Y-%m-%d")

    except (ValueError, TypeError, AttributeError):
        return "N/A"


def _format_duration(duration: Any) -> str:
    """Format duration for table display."""
    if not duration:
        return "N/A"

    try:
        if isinstance(duration, str):
            return duration
        elif isinstance(duration, (int, float)):
            # Convert seconds to readable format
            if duration < 60:
                return f"{duration:.1f}s"
            elif duration < 3600:
                return f"{duration // 60:.0f}m {duration % 60:.0f}s"
            else:
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                return f"{hours:.0f}h {minutes:.0f}m"
        else:
            return "N/A"
    except (ValueError, TypeError):
        return "N/A"


def _format_file_size(size: Any) -> str:
    """Format file size for table display."""
    if not size or size == 0:
        return "0 B"

    try:
        size = float(size)
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{size:.0f} {units[unit_index]}"
        else:
            return f"{size:.1f} {units[unit_index]}"

    except (ValueError, TypeError):
        return "N/A"


# Formatter mapping for dynamic lookup
FORMATTER_MAP: Dict[str, Callable[[Dict[str, Any]], List[str]]] = {
    "template": format_templates_table,
    "templates": format_templates_table,
    "user": format_users_table,
    "users": format_users_table,
    "workflow": format_workflows_table,
    "workflows": format_workflows_table,
    "notebook": format_notebooks_table,
    "notebooks": format_notebooks_table,
    "workspace": format_workspaces_table,
    "workspaces": format_workspaces_table,
    "file": format_dff_files_table,
    "files": format_dff_files_table,
    "data": format_dff_data_table,
    "tag": format_tags_table,
    "tags": format_tags_table,
    "system": format_systems_table,
    "systems": format_systems_table,
    "asset": format_assets_table,
    "assets": format_assets_table,
}


def get_formatter(resource_type: str) -> Optional[Callable[[Dict[str, Any]], List[str]]]:
    """Get the appropriate formatter function for a resource type.

    Args:
        resource_type: The resource type key (e.g., 'workflow', 'user').

    Returns:
        A formatter function that accepts a mapping and returns a list of strings, or
        None if no formatter exists for the provided resource type.
    """
    return FORMATTER_MAP.get(resource_type.lower())

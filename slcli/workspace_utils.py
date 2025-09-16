"""Workspace utilities for CLI commands."""

from typing import Dict, List, Any, Optional, Callable

from .utils import get_workspace_map


def resolve_workspace_filter(workspace: str, workspace_map: Dict[str, str]) -> str:
    """Resolve workspace name to ID for filtering.

    Args:
        workspace: Workspace name or ID to resolve
        workspace_map: Dictionary mapping workspace IDs to names

    Returns:
        Workspace ID (either the original if it was an ID, or resolved from name)
    """
    if not workspace:
        return workspace

    # Check if it's already an ID (exists as key in workspace_map)
    if workspace in workspace_map:
        return workspace

    # Try to find by name (case-insensitive)
    for ws_id, ws_name in workspace_map.items():
        if ws_name and workspace.lower() == ws_name.lower():
            return ws_id

    # Return original if no match found
    return workspace


def filter_by_workspace(
    items: List[Dict[str, Any]],
    workspace: str,
    workspace_map: Dict[str, str],
    workspace_field: str = "workspace",
) -> List[Dict[str, Any]]:
    """Filter items by workspace name or ID.

    Args:
        items: List of items to filter
        workspace: Workspace name or ID to filter by
        workspace_map: Dictionary mapping workspace IDs to names
        workspace_field: Field name in items that contains workspace ID

    Returns:
        Filtered list of items
    """
    if not workspace:
        return items

    filtered_items = []
    for item in items:
        item_workspace = item.get(workspace_field, "")
        item_workspace_name = workspace_map.get(item_workspace, item_workspace)

        # Match by ID or name (case-insensitive)
        if workspace.lower() == item_workspace.lower() or (
            item_workspace_name and workspace.lower() == item_workspace_name.lower()
        ):
            filtered_items.append(item)

    return filtered_items


def resolve_workspace_id(workspace: Optional[str]) -> str:
    """Resolve workspace name to ID with error handling.

    Args:
        workspace: Workspace name or ID to resolve

    Returns:
        Resolved workspace ID
    """
    if not workspace:
        return ""

    try:
        workspace_map = get_workspace_map()
        return resolve_workspace_filter(workspace, workspace_map)
    except Exception:
        return workspace


def get_workspace_display_name(
    workspace_id: str, workspace_map: Optional[Dict[str, str]] = None
) -> str:
    """Get display name for a workspace ID.

    Args:
        workspace_id: Workspace ID to get display name for
        workspace_map: Optional workspace map, will fetch if not provided

    Returns:
        Workspace display name (name if available, otherwise ID)
    """
    if not workspace_map:
        try:
            workspace_map = get_workspace_map()
        except Exception:
            return workspace_id or ""

    return workspace_map.get(workspace_id, workspace_id) or ""


class WorkspaceFormatter:
    """Utility class for formatting workspace-related data."""

    @staticmethod
    def create_workspace_row_formatter(
        workspace_map: Dict[str, str], name_field: str = "name", id_field: str = "id"
    ) -> Callable[[Dict[str, Any]], List[str]]:
        """Create a row formatter function for workspace-based tables."""

        def formatter(item: Dict[str, Any]) -> List[str]:
            workspace_id = item.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
            name = item.get(name_field, "")
            item_id = item.get(id_field, "")
            return [workspace_name, name, item_id]

        return formatter

    @staticmethod
    def create_config_row_formatter(
        workspace_map: Dict[str, str],
    ) -> Callable[[Dict[str, Any]], List[str]]:
        """Create a row formatter for DFF configurations."""

        def formatter(config: Dict[str, Any]) -> List[str]:
            workspace_id = config.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
            name = config.get("name", "")
            config_id = config.get("id", "")
            return [workspace_name, name, config_id]

        return formatter

    @staticmethod
    def create_group_field_row_formatter(
        workspace_map: Dict[str, str],
    ) -> Callable[[Dict[str, Any]], List[str]]:
        """Create a row formatter for DFF groups and fields."""

        def formatter(item: Dict[str, Any]) -> List[str]:
            workspace_id = item.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
            name = item.get("displayText", item.get("name", ""))
            key = item.get("key", "")
            return [workspace_name, name, key]

        return formatter

    @staticmethod
    def create_table_row_formatter(
        workspace_map: Dict[str, str],
    ) -> Callable[[Dict[str, Any]], List[str]]:
        """Create a row formatter for DFF table properties."""

        def formatter(table: Dict[str, Any]) -> List[str]:
            workspace_id = table.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id) or ""
            resource_type = table.get("resourceType", "")
            resource_id = table.get("resourceId", "")
            table_id = table.get("id", "")
            return [workspace_name, resource_type, resource_id, table_id]

        return formatter

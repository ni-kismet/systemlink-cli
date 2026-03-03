"""Unit tests for workspace_utils.py — including profile default workspace fallback."""

from typing import Any, Dict, List
from unittest.mock import patch

from slcli.workspace_utils import filter_by_workspace, resolve_workspace_id

WORKSPACE_MAP: Dict[str, str] = {
    "ws-1": "Production",
    "ws-2": "Development",
}

ITEMS: List[Dict[str, Any]] = [
    {"id": "a", "name": "Item A", "workspace": "ws-1"},
    {"id": "b", "name": "Item B", "workspace": "ws-2"},
]


# ---------------------------------------------------------------------------
# filter_by_workspace
# ---------------------------------------------------------------------------


def test_filter_by_workspace_explicit_name() -> None:
    """Explicit workspace name filters to that workspace."""
    result = filter_by_workspace(ITEMS, "Production", WORKSPACE_MAP)
    assert len(result) == 1
    assert result[0]["id"] == "a"


def test_filter_by_workspace_explicit_id() -> None:
    """Explicit workspace ID filters to that workspace."""
    result = filter_by_workspace(ITEMS, "ws-2", WORKSPACE_MAP)
    assert len(result) == 1
    assert result[0]["id"] == "b"


def test_filter_by_workspace_no_match_returns_empty() -> None:
    """Non-matching workspace name returns empty list."""
    result = filter_by_workspace(ITEMS, "Nonexistent", WORKSPACE_MAP)
    assert result == []


def test_filter_by_workspace_empty_no_profile_default_returns_all() -> None:
    """When no workspace is given and profile has no default, all items are returned."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value=None):
        result = filter_by_workspace(ITEMS, "", WORKSPACE_MAP)
    assert result == ITEMS


def test_filter_by_workspace_empty_falls_back_to_profile_default() -> None:
    """When no workspace is given but profile has a default, it is applied."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value="Development"):
        result = filter_by_workspace(ITEMS, "", WORKSPACE_MAP)
    assert len(result) == 1
    assert result[0]["id"] == "b"


def test_filter_by_workspace_none_falls_back_to_profile_default() -> None:
    """None workspace also triggers profile default fallback."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value="Production"):
        result = filter_by_workspace(ITEMS, "", WORKSPACE_MAP)
    assert len(result) == 1
    assert result[0]["id"] == "a"


def test_filter_by_workspace_explicit_overrides_profile_default() -> None:
    """Explicit workspace takes precedence over profile default."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value="Production"):
        result = filter_by_workspace(ITEMS, "Development", WORKSPACE_MAP)
    assert len(result) == 1
    assert result[0]["id"] == "b"


# ---------------------------------------------------------------------------
# resolve_workspace_id
# ---------------------------------------------------------------------------


def test_resolve_workspace_id_explicit_name() -> None:
    """Explicit workspace name resolves to ID."""
    with patch("slcli.workspace_utils.get_workspace_map", return_value=WORKSPACE_MAP):
        result = resolve_workspace_id("Production")
    assert result == "ws-1"


def test_resolve_workspace_id_explicit_id_passthrough() -> None:
    """Explicit workspace ID is returned as-is."""
    with patch("slcli.workspace_utils.get_workspace_map", return_value=WORKSPACE_MAP):
        result = resolve_workspace_id("ws-2")
    assert result == "ws-2"


def test_resolve_workspace_id_none_no_profile_returns_empty() -> None:
    """No workspace and no profile default returns empty string."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value=None):
        result = resolve_workspace_id(None)
    assert result == ""


def test_resolve_workspace_id_none_falls_back_to_profile_default() -> None:
    """None workspace resolves via profile default."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value="Development"):
        with patch("slcli.workspace_utils.get_workspace_map", return_value=WORKSPACE_MAP):
            result = resolve_workspace_id(None)
    assert result == "ws-2"


def test_resolve_workspace_id_empty_string_falls_back_to_profile_default() -> None:
    """Empty string workspace also triggers profile default fallback."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value="Production"):
        with patch("slcli.workspace_utils.get_workspace_map", return_value=WORKSPACE_MAP):
            result = resolve_workspace_id("")
    assert result == "ws-1"


def test_resolve_workspace_id_explicit_overrides_profile_default() -> None:
    """Explicit workspace is used, profile default is not consulted."""
    with patch("slcli.workspace_utils.get_default_workspace") as mock_default:
        with patch("slcli.workspace_utils.get_workspace_map", return_value=WORKSPACE_MAP):
            result = resolve_workspace_id("Production")
    mock_default.assert_not_called()
    assert result == "ws-1"

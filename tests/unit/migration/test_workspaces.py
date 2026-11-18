"""Tests for discovering source workspaces and synchronizing destination workspaces."""

from typing import Iterable, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from slcli.migration.workspace_client import Workspace
from slcli.migration.workspaces import (
    MappedWorkspace,
    WorkspaceMappingError,
    discover_workspaces,
    synchronize_workspaces,
)


def _workspaces(prefix: str, names: Iterable[str]) -> List[Workspace]:
    return [Workspace(id=f"{prefix}-{name}", name=name) for name in names]


SOURCE = _workspaces("s", ["Lab", "Default"])


@pytest.fixture
def create_destination_workspace() -> MagicMock:
    """Record creation requests and return a workspace with a distinct ID."""
    return MagicMock(side_effect=lambda name: Workspace(id=f"created-{name}", name=name))


def test_omitted_selection_discovers_every_source_workspace() -> None:
    """Every source workspace is in scope, ordered by name."""
    discovered = discover_workspaces(SOURCE, None)

    assert [w.name for w in discovered.source.values()] == ["Default", "Lab"]
    assert discovered.selected == ("Default", "Lab")


def test_unknown_source_workspaces_are_all_reported() -> None:
    """Every requested workspace the source lacks is reported together."""
    with pytest.raises(WorkspaceMappingError) as raised:
        discover_workspaces(SOURCE, ["Lab", "Missing", "Absent"])

    assert raised.value.missing_source == ["Absent", "Missing"]
    assert str(raised.value) == "unknown source workspace: Absent, Missing"


@pytest.mark.parametrize(
    "selection, expected_selected",
    [(None, ("Default", "Lab")), (["Lab"], ("Lab",)), ([], ())],
)
def test_discovery_excludes_disabled_source_workspaces(
    selection: Optional[List[str]],
    expected_selected: Tuple[str, ...],
) -> None:
    """Disabled sources are excluded from discovery even with an explicit selection."""
    discovered = discover_workspaces(
        iter([*SOURCE, Workspace(id="disabled-id", name="Disabled", enabled=False)]),
        selection,
    )

    assert [workspace.name for workspace in discovered.source.values()] == ["Default", "Lab"]
    assert discovered.selected == expected_selected
    assert discovered.disabled == ("Disabled",)


def test_disabled_source_names_are_reported_with_explicit_selection() -> None:
    """Disabled names are reported even when the selection excludes them."""
    discovered = discover_workspaces(
        iter([*SOURCE, Workspace(id="disabled-id", name="Disabled", enabled=False)]),
        ["Default"],
    )

    assert discovered.selected == ("Default",)
    assert discovered.disabled == ("Disabled",)


def test_explicit_selection_rejects_disabled_source_workspace() -> None:
    """An explicitly requested disabled source cannot be migrated."""
    with pytest.raises(WorkspaceMappingError) as raised:
        discover_workspaces(
            [*SOURCE, Workspace(id="disabled-id", name="Disabled", enabled=False)],
            ["Lab", "Disabled"],
        )

    assert raised.value.missing_source == ["Disabled"]


def test_discovery_with_only_disabled_sources_is_empty() -> None:
    """A server with no enabled workspaces has nothing in scope."""
    discovered = discover_workspaces(
        [Workspace(id="disabled-id", name="Disabled", enabled=False)], None
    )

    assert discovered.source == {}
    assert discovered.selected == ()


def test_omitted_mappings_map_every_selected_workspace_by_name(
    create_destination_workspace: MagicMock,
) -> None:
    """Every selected source workspace maps to the same-named destination workspace."""
    mapping = synchronize_workspaces(
        discover_workspaces(SOURCE, None),
        _workspaces("d", ["Lab", "Default", "Extra"]),
        create_destination_workspace,
        None,
    )

    assert mapping.workspaces == (
        MappedWorkspace(
            source_name="Default",
            source_id="s-Default",
            destination_name="Default",
            destination_id="d-Default",
        ),
        MappedWorkspace(
            source_name="Lab", source_id="s-Lab", destination_name="Lab", destination_id="d-Lab"
        ),
    )
    create_destination_workspace.assert_not_called()


def test_explicit_mappings_select_and_rename(create_destination_workspace: MagicMock) -> None:
    """Only selected source workspaces are mapped, to the requested destinations."""
    requested = {"Lab": "Target"}
    mapping = synchronize_workspaces(
        discover_workspaces(SOURCE, requested),
        _workspaces("d", ["Target"]),
        create_destination_workspace,
        requested,
    )

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [("Lab", "d-Target")]
    create_destination_workspace.assert_not_called()
    assert mapping.workspace("Lab").destination_id == "d-Target"
    with pytest.raises(KeyError):
        mapping.workspace("Default")


def test_missing_destination_workspace_is_created(create_destination_workspace: MagicMock) -> None:
    """Missing destinations are created while existing destinations retain their IDs."""
    requested = {"Lab": "Lab", "Default": "Absent"}
    mapping = synchronize_workspaces(
        discover_workspaces(SOURCE, requested),
        _workspaces("d", ["Lab"]),
        create_destination_workspace,
        requested,
    )

    create_destination_workspace.assert_called_once_with("Absent")
    assert [
        (workspace.source_name, workspace.destination_id) for workspace in mapping.workspaces
    ] == [
        ("Default", "created-Absent"),
        ("Lab", "d-Lab"),
    ]


def test_empty_source_maps_nothing(create_destination_workspace: MagicMock) -> None:
    """A source without workspaces needs no destination workspaces."""
    mapping = synchronize_workspaces(
        discover_workspaces([], None), [], create_destination_workspace, None
    )

    assert mapping.workspaces == ()
    create_destination_workspace.assert_not_called()


def test_omitted_mappings_preserve_special_character_names(
    create_destination_workspace: MagicMock,
) -> None:
    """Auto-mapping matches names verbatim, including delimiters and quotes."""
    names = ["Lab:A", "a, b", 'Say "hi"', "x/y", "Ünïcødé"]

    mapping = synchronize_workspaces(
        discover_workspaces(_workspaces("s", names), None),
        _workspaces("d", names),
        create_destination_workspace,
        None,
    )

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [
        (name, f"d-{name}") for name in sorted(names)
    ]
    create_destination_workspace.assert_not_called()

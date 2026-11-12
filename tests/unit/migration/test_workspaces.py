"""Tests for discovering source workspaces and synchronizing destination workspaces."""

from typing import Iterable, List

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


def test_omitted_selection_discovers_every_source_workspace() -> None:
    """Every source workspace is in scope, ordered by name."""
    discovered = discover_workspaces(SOURCE, None)

    assert [w.name for w in discovered.source] == ["Default", "Lab"]
    assert discovered.selected == ("Default", "Lab")


def test_unknown_source_workspaces_are_all_reported() -> None:
    """Every requested workspace the source lacks is reported together."""
    with pytest.raises(WorkspaceMappingError) as raised:
        discover_workspaces(SOURCE, ["Lab", "Missing", "Absent"])

    assert raised.value.missing_source == ["Absent", "Missing"]
    assert str(raised.value) == "unknown source workspace: Absent, Missing"


def test_omitted_mappings_map_every_selected_workspace_by_name() -> None:
    """Every selected source workspace maps to the same-named destination workspace."""
    mapping = synchronize_workspaces(
        discover_workspaces(SOURCE, None), _workspaces("d", ["Lab", "Default", "Extra"]), None
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


def test_explicit_mappings_select_and_rename() -> None:
    """Only selected source workspaces are mapped, to the requested destinations."""
    requested = {"Lab": "Target"}
    mapping = synchronize_workspaces(
        discover_workspaces(SOURCE, requested), _workspaces("d", ["Target"]), requested
    )

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [("Lab", "d-Target")]
    assert mapping.workspace("Lab").destination_id == "d-Target"
    with pytest.raises(KeyError):
        mapping.workspace("Default")


def test_missing_destination_workspaces_are_all_reported() -> None:
    """Every missing destination workspace is reported together and nothing is mapped."""
    requested = {"Lab": "Lab", "Default": "Absent"}
    with pytest.raises(WorkspaceMappingError) as raised:
        synchronize_workspaces(
            discover_workspaces(SOURCE, requested), _workspaces("d", ["Lab"]), requested
        )

    assert raised.value.missing_destination == ["Default -> Absent"]
    assert str(raised.value) == "missing destination workspace: Default -> Absent"


def test_empty_source_maps_nothing() -> None:
    """A source without workspaces needs no destination workspaces."""
    assert synchronize_workspaces(discover_workspaces([], None), [], None).workspaces == ()


def test_omitted_mappings_preserve_special_character_names() -> None:
    """Auto-mapping matches names verbatim, including delimiters and quotes."""
    names = ["Lab:A", "a, b", 'Say "hi"', "x/y", "Ünïcødé"]

    mapping = synchronize_workspaces(
        discover_workspaces(_workspaces("s", names), None), _workspaces("d", names), None
    )

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [
        (name, f"d-{name}") for name in sorted(names)
    ]

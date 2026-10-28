"""Tests for source-to-destination workspace mapping."""

from typing import Iterable, List

import pytest

from slcli.migration.workspace_client import Workspace
from slcli.migration.workspaces import (
    MappedWorkspace,
    WorkspaceMappingError,
    map_workspaces,
)


def _workspaces(prefix: str, names: Iterable[str]) -> List[Workspace]:
    return [Workspace(id=f"{prefix}-{name}", name=name) for name in names]


SOURCE = _workspaces("s", ["Default", "Lab"])


def test_omitted_mappings_map_every_source_workspace_by_name() -> None:
    """Every source workspace maps to the same-named destination workspace."""
    mapping = map_workspaces(SOURCE, _workspaces("d", ["Lab", "Default", "Extra"]), None)

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
    """Only requested source workspaces are mapped, to the requested destinations."""
    mapping = map_workspaces(SOURCE, _workspaces("d", ["Target"]), {"Lab": "Target"})

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [("Lab", "d-Target")]
    assert mapping.destination_id("Lab") == "d-Target"
    with pytest.raises(KeyError):
        mapping.destination_id("Default")


def test_missing_workspaces_on_either_side_are_all_reported() -> None:
    """Every missing workspace is reported together and nothing is mapped."""
    with pytest.raises(WorkspaceMappingError) as raised:
        map_workspaces(
            SOURCE,
            _workspaces("d", ["Lab"]),
            {"Lab": "Lab", "Default": "Absent", "Missing": "Lab"},
        )

    assert raised.value.missing_source == ["Missing"]
    assert raised.value.missing_destination == ["Default -> Absent"]
    assert str(raised.value) == (
        "unknown source workspace: Missing; missing destination workspace: Default -> Absent"
    )


def test_empty_source_maps_nothing() -> None:
    """A source without workspaces needs no destination workspaces."""
    assert map_workspaces([], [], None).workspaces == ()


def test_omitted_mappings_preserve_special_character_names() -> None:
    """Auto-mapping matches names verbatim, including delimiters and quotes."""
    names = ["Lab:A", "a, b", 'Say "hi"', "x/y", "Ünïcødé"]

    mapping = map_workspaces(_workspaces("s", names), _workspaces("d", names), None)

    assert [(w.source_name, w.destination_id) for w in mapping.workspaces] == [
        (name, f"d-{name}") for name in sorted(names)
    ]

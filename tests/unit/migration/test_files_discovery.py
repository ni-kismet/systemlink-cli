"""Tests for SLS file discovery policy."""

import re
from typing import Dict, Iterator, List, Optional

import pytest

from slcli.migration.files.client import SourceFile
from slcli.migration.files.discovery import discover_files
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.schema import SCHEMA_VERSION
from slcli.migration.testmonitor.models import WorkspaceFailure
from slcli.migration.workspace_client import Workspace
from slcli.migration.workspaces import DiscoveredWorkspaces

WORKSPACES = {"Lab": "lab-id", "Default": "default-id", "Broken": "broken-id"}


def _discovered_workspaces(selected: Optional[List[str]] = None) -> DiscoveredWorkspaces:
    source = {
        name: Workspace(id=workspace_id, name=name) for name, workspace_id in WORKSPACES.items()
    }
    selected_names = tuple(sorted(source if selected is None else selected))
    return DiscoveredWorkspaces(source=source, selected=selected_names)


class FakeFiles:
    """Serves files per workspace ID; raises for workspaces listed in ``failing``."""

    def __init__(
        self,
        files: Dict[str, List[SourceFile]],
        failing: Optional[Dict[str, Exception]] = None,
    ) -> None:
        """Store the files and the failures to raise per workspace."""
        self._files = files
        self._failing = failing or {}
        self.queried: List[str] = []

    def query_files(self, workspace_id: str) -> Iterator[SourceFile]:
        self.queried.append(workspace_id)
        if workspace_id in self._failing:
            raise self._failing[workspace_id]
        return iter(self._files.get(workspace_id, []))


def _file(file_id: str, name: Optional[str] = "a.txt", size64: Optional[int] = 3) -> SourceFile:
    properties = {} if name is None else {"Name": name}
    return SourceFile(id=file_id, properties=properties, size=-1, size64=size64)


def test_files_are_attributed_to_the_queried_workspace() -> None:
    """Each file carries the workspace it was queried from, sorted deterministically."""
    client = FakeFiles({"lab-id": [_file("f2"), _file("f1")], "default-id": [_file("f3")]})

    discovery = discover_files(client, _discovered_workspaces(["Lab", "Default"]))

    assert discovery.workspaces == ("Default", "Lab")
    assert discovery.files == (
        DiscoveredFile(id="f3", workspace="Default", name="a.txt", size_bytes=3),
        DiscoveredFile(id="f1", workspace="Lab", name="a.txt", size_bytes=3),
        DiscoveredFile(id="f2", workspace="Lab", name="a.txt", size_bytes=3),
    )
    assert discovery.failures == ()


def test_all_workspaces_are_discovered_by_default() -> None:
    """Omitting the selection queries every accessible workspace."""
    client = FakeFiles({})

    discovery = discover_files(client, _discovered_workspaces())

    assert discovery.workspaces == ("Broken", "Default", "Lab")
    assert sorted(client.queried) == ["broken-id", "default-id", "lab-id"]


def test_unknown_selected_workspace_is_reported_as_a_workspace_failure() -> None:
    """An invalid manually constructed selection is isolated like a workspace lookup error."""
    client = FakeFiles({})
    discovery = discover_files(client, _discovered_workspaces(["Missing"]))

    assert discovery.failures == (WorkspaceFailure(workspace="Missing", error_type="KeyError"),)
    assert client.queried == []


def test_failed_workspace_is_isolated_and_contributes_no_files() -> None:
    """A failing workspace is reported while other workspaces still discover files."""
    client = FakeFiles(
        {"lab-id": [_file("f1")]},
        failing={"broken-id": RuntimeError("boom")},
    )

    discovery = discover_files(client, _discovered_workspaces(["Broken", "Lab"]))

    assert [file.id for file in discovery.files] == ["f1"]
    assert discovery.failures == (WorkspaceFailure(workspace="Broken", error_type="RuntimeError"),)


def test_mid_pagination_failure_contributes_no_partial_files() -> None:
    """A workspace that fails after yielding some files contributes nothing."""

    class PartialThenFail(FakeFiles):
        def query_files(self, workspace_id: str) -> Iterator[SourceFile]:
            if workspace_id == "lab-id":
                yield _file("partial")
                raise RuntimeError("page 2 failed")
            yield from super().query_files(workspace_id)

    discovery = discover_files(PartialThenFail({}), _discovered_workspaces(["Lab"]))

    assert discovery.files == ()
    assert discovery.failures == (WorkspaceFailure(workspace="Lab", error_type="RuntimeError"),)


def test_missing_name_and_size_stay_optional() -> None:
    """Files without a name or a usable size keep None rather than placeholders."""
    client = FakeFiles(
        {"lab-id": [_file("f1", name=None, size64=None)]},
    )

    discovery = discover_files(client, _discovered_workspaces(["Lab"]))

    assert discovery.files == (
        DiscoveredFile(id="f1", workspace="Lab", name=None, size_bytes=None),
    )


def test_size_falls_back_to_32_bit_field_when_64_bit_is_absent() -> None:
    """The 32-bit size is used only when size64 is missing and not the -1 sentinel."""
    assert SourceFile(id="a", size=42).size_bytes == 42
    assert SourceFile(id="b", size=-1).size_bytes is None
    assert SourceFile(id="c", size=-1, size64=5_000_000_000).size_bytes == 5_000_000_000


def test_every_discovered_file_maps_to_a_unique_objectid_shaped_valinor_id() -> None:
    """Each SLS file ID maps to a distinct 24-hex ID that never reuses an SLS ID."""
    client = FakeFiles({"lab-id": [_file("f1"), _file("f2")], "default-id": [_file("f3")]})

    discovery = discover_files(client, _discovered_workspaces(["Lab", "Default"]))

    assert set(discovery.file_id_map) == {"f1", "f2", "f3"}
    new_ids = list(discovery.file_id_map.values())
    assert len(set(new_ids)) == 3
    assert all(re.fullmatch(r"[0-9a-f]{24}", new_id) for new_id in new_ids)
    assert set(new_ids).isdisjoint({"f1", "f2", "f3"})


def test_empty_discovery_has_an_empty_file_id_map() -> None:
    """With no files, no IDs are allocated."""
    discovery = discover_files(FakeFiles({}), _discovered_workspaces(["Lab"]))

    assert discovery.files == ()
    assert discovery.file_id_map == {}


def test_failed_workspace_files_get_no_id_mapping() -> None:
    """Only files from successfully queried workspaces are mapped."""
    client = FakeFiles(
        {"lab-id": [_file("f1")]},
        failing={"broken-id": RuntimeError("boom")},
    )

    discovery = discover_files(client, _discovered_workspaces(["Broken", "Lab"]))

    assert set(discovery.file_id_map) == {"f1"}


def test_duplicate_sls_file_ids_are_rejected() -> None:
    """The same SLS file ID appearing twice is a source error, not silently merged."""
    client = FakeFiles({"lab-id": [_file("f1")], "default-id": [_file("f1")]})

    with pytest.raises(ValueError, match="Duplicate SLS file IDs found: f1"):
        discover_files(client, _discovered_workspaces(["Lab", "Default"]))


def test_allocation_regenerates_when_a_candidate_is_already_taken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate that equals an SLS ID is discarded and another is drawn."""
    candidates = iter(["f1", "ab" * 12])
    monkeypatch.setattr(
        "slcli.migration.files.discovery.secrets.token_hex",
        lambda _nbytes: next(candidates),
    )
    client = FakeFiles({"lab-id": [_file("f1")]})

    discovery = discover_files(client, _discovered_workspaces(["Lab"]))

    assert discovery.file_id_map == {"f1": "ab" * 12}


def test_file_id_map_survives_a_json_round_trip() -> None:
    """The map is persisted as JSON by Prefect, so it must load back unchanged."""
    client = FakeFiles({"lab-id": [_file("f1"), _file("f2")]})
    discovery = discover_files(client, _discovered_workspaces(["Lab"]))

    restored = FileDiscovery.model_validate_json(discovery.model_dump_json())

    assert restored == discovery
    assert restored.file_id_map == discovery.file_id_map


def test_discovery_result_is_a_versioned_model() -> None:
    """The persisted result carries the schema version for compatibility checks."""
    assert FileDiscovery().schema_version == SCHEMA_VERSION

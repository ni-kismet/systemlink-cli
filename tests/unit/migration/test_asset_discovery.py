"""Tests for pure Asset Service discovery and planning policy."""

from slcli.migration.assets.discovery import discover_assets


def _asset(asset_id: str, minion_id: str = "minion-1", **overrides: object) -> dict[str, object]:
    asset = {
        "id": asset_id,
        "name": "DAQ",
        "discoveryType": "MANUAL",
        "supportsSelfCalibration": True,
        "fileIds": ["file-1"],
        "keywords": ["production"],
        "properties": {"Owner": "Engineering", "Migration.SourceId": "old"},
        "location": {"minionId": minion_id, "slotNumber": 2},
    }
    asset.update(overrides)
    return asset


def test_discovery_maps_supported_asset_to_destination_workspace() -> None:
    """System ownership determines source and destination workspace placement."""
    discovery = discover_assets(
        [_asset("asset-1")],
        source_system_workspaces={"minion-1": "Source"},
        destination_minion_ids={"minion-1"},
        destination_file_ids_by_source_id={"file-1": "destination-file-1"},
        workspace_mappings={"Source": "Target"},
    )

    assert len(discovery.assets) == 1
    asset = discovery.assets[0]
    assert (asset.workspace, asset.destination_workspace, asset.decision) == (
        "Source",
        "Target",
        "include",
    )
    assert asset.location.minion_id == "minion-1"
    assert asset.is_calibration_capable is True
    assert asset.properties == {"Owner": "Engineering"}


def test_discovery_preserves_numeric_metadata_and_external_calibration_capability() -> None:
    """Asset number fields and either calibration capability are retained."""
    discovery = discover_assets(
        [
            _asset(
                "asset-1",
                modelNumber=42,
                vendorNumber=7,
                supportsSelfCalibration=False,
                supportsExternalCalibration=True,
            )
        ],
        source_system_workspaces={"minion-1": "Source"},
        destination_minion_ids={"minion-1"},
        destination_file_ids_by_source_id={"file-1": "destination-file-1"},
    )

    asset = discovery.assets[0]
    assert (asset.model_number, asset.vendor_number) == (42, 7)
    assert asset.is_calibration_capable is True


def test_discovery_falls_back_to_default_for_unknown_system() -> None:
    """Assets without a known owning system are placed in Default."""
    discovery = discover_assets(
        [_asset("asset-1", minion_id="unknown", fileIds=[])],
        source_system_workspaces={},
        destination_minion_ids={"unknown"},
        destination_file_ids_by_source_id={},
    )

    asset = discovery.assets[0]
    assert (asset.workspace, asset.destination_workspace, asset.decision) == (
        "Default",
        "Default",
        "include",
    )


def test_discovery_does_not_require_a_system_for_empty_minion_id() -> None:
    """A physical asset with no owning minion is eligible without a destination system."""
    discovery = discover_assets(
        [_asset("asset-1", minion_id="", fileIds=[])],
        source_system_workspaces={},
        destination_minion_ids=set(),
        destination_file_ids_by_source_id={},
    )

    asset = discovery.assets[0]
    assert (asset.workspace, asset.decision, asset.block_reason) == ("Default", "include", None)


def test_discovery_omits_assets_outside_selected_workspaces() -> None:
    """Workspace mappings select the source asset scope."""
    discovery = discover_assets(
        [_asset("in"), _asset("out", minion_id="minion-2")],
        source_system_workspaces={"minion-1": "Selected", "minion-2": "Other"},
        destination_minion_ids={"minion-1", "minion-2"},
        destination_file_ids_by_source_id={"file-1": "destination-file-1"},
        workspace_mappings={"Selected": "Target"},
    )

    assert [asset.id for asset in discovery.assets] == ["in"]
    assert discovery.out_of_scope_count == 1


def test_discovery_blocks_missing_destination_system() -> None:
    """System-located assets wait for their matching destination minion."""
    discovery = discover_assets(
        [_asset("asset-1")],
        source_system_workspaces={"minion-1": "Source"},
        destination_minion_ids=set(),
        destination_file_ids_by_source_id={"file-1": "destination-file-1"},
    )

    asset = discovery.assets[0]
    assert asset.decision == "block"
    assert asset.block_reason == "missing destination system for minion minion-1"


def test_discovery_blocks_missing_destination_file() -> None:
    """Assets wait until every linked source file has been uploaded."""
    discovery = discover_assets(
        [_asset("asset-1")],
        source_system_workspaces={"minion-1": "Source"},
        destination_minion_ids={"minion-1"},
        destination_file_ids_by_source_id={},
    )

    asset = discovery.assets[0]
    assert asset.decision == "block"
    assert asset.block_reason == "missing destination files: file-1"

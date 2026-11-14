"""Pure Asset Service discovery and planning policy."""

from collections.abc import Collection, Iterable, Mapping
from typing import Any, Dict, Optional, Tuple

from slcli.migration.assets.models import AssetDiscovery, AssetLocation, DiscoveredAsset
from slcli.migration.testmonitor.discovery import DEFAULT_WORKSPACE


def _string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _integer(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _strings(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _location(record: Mapping[str, Any]) -> AssetLocation:
    raw_location = record.get("location")
    if not isinstance(raw_location, Mapping):
        return AssetLocation()
    state = raw_location.get("state")
    return AssetLocation(
        minion_id=_string(raw_location.get("minionId")),
        physical_location=_string(raw_location.get("physicalLocation")),
        parent=_string(raw_location.get("parent")),
        resource_uri=_string(raw_location.get("resourceUri")),
        slot_number=(
            raw_location.get("slotNumber")
            if isinstance(raw_location.get("slotNumber"), int)
            else None
        ),
        asset_presence=_string(state.get("assetPresence")) if isinstance(state, Mapping) else None,
    )


def _properties(record: Mapping[str, Any]) -> Dict[str, str]:
    raw_properties = record.get("properties")
    if not isinstance(raw_properties, Mapping):
        return {}
    return {
        name: value
        for name, value in raw_properties.items()
        if isinstance(name, str) and isinstance(value, str) and not name.startswith("Migration.")
    }


def _block_reason(
    location: AssetLocation,
    destination_minion_ids: Collection[str],
    file_ids: Collection[str],
    destination_file_ids_by_source_id: Mapping[str, str],
) -> Optional[str]:
    if location.minion_id and location.minion_id not in destination_minion_ids:
        return f"missing destination system for minion {location.minion_id}"
    missing_file_ids = sorted(set(file_ids).difference(destination_file_ids_by_source_id))
    if missing_file_ids:
        return f"missing destination files: {', '.join(missing_file_ids)}"
    return None


def discover_assets(
    records: Iterable[Mapping[str, Any]],
    source_system_workspaces: Mapping[str, str],
    destination_minion_ids: Collection[str],
    destination_file_ids_by_source_id: Mapping[str, str],
    workspace_mappings: Optional[Mapping[str, str]] = None,
) -> AssetDiscovery:
    """Create compact asset discovery results from source Asset Service records.

    The source workspace is determined from the owning system's minion ID. Assets
    whose system is unknown fall back to Default. When workspace mappings are
    supplied, only mapped source workspaces are retained.
    """
    assets = []
    out_of_scope_count = 0
    for record in records:
        location = _location(record)
        workspace = source_system_workspaces.get(location.minion_id or "", DEFAULT_WORKSPACE)
        if workspace_mappings is not None and workspace not in workspace_mappings:
            out_of_scope_count += 1
            continue

        file_ids = _strings(record.get("fileIds"))
        block_reason = _block_reason(
            location, destination_minion_ids, file_ids, destination_file_ids_by_source_id
        )
        assets.append(
            DiscoveredAsset(
                id=str(record["id"]),
                workspace=workspace,
                decision="block" if block_reason else "include",
                discovery_type=_string(record.get("discoveryType")),
                name=_string(record.get("name")),
                model_name=_string(record.get("modelName")),
                model_number=_integer(record.get("modelNumber")),
                serial_number=_string(record.get("serialNumber")),
                vendor_name=_string(record.get("vendorName")),
                vendor_number=_integer(record.get("vendorNumber")),
                part_number=_string(record.get("partNumber")),
                location=location,
                is_calibration_capable=bool(
                    record.get("supportsSelfCalibration", False)
                    or record.get("supportsExternalCalibration", False)
                ),
                file_ids=file_ids,
                updated_at=record.get("updatedAt"),
                keywords=_strings(record.get("keywords")),
                properties=_properties(record),
                destination_workspace=(
                    workspace_mappings[workspace] if workspace_mappings is not None else workspace
                ),
                block_reason=block_reason,
            )
        )
    return AssetDiscovery(
        assets=tuple(sorted(assets, key=lambda asset: asset.id)),
        out_of_scope_count=out_of_scope_count,
    )

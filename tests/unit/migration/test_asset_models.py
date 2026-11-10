"""Tests for persisted Asset Service discovery models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from slcli.migration.assets.models import AssetDiscovery, AssetLocation, DiscoveredAsset
from slcli.migration.schema import SCHEMA_VERSION


def test_asset_discovery_serializes_compact_asset_metadata() -> None:
    """Persisted discovery contains only the fields needed by later stages."""
    discovery = AssetDiscovery(
        assets=(
            DiscoveredAsset(
                id="asset-1",
                workspace="Source",
                decision="include",
                discovery_type="MANUAL",
                name="DAQ",
                serial_number="serial-1",
                location=AssetLocation(minion_id="minion-1", slot_number=2),
                is_calibration_capable=True,
                file_ids=("file-1",),
                updated_at=datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
                keywords=("production",),
                properties={"Owner": "Engineering"},
                destination_workspace="Target",
            ),
        )
    )

    assert discovery.model_dump(mode="json") == {
        "schema_version": SCHEMA_VERSION,
        "assets": [
            {
                "id": "asset-1",
                "workspace": "Source",
                "decision": "include",
                "discovery_type": "MANUAL",
                "name": "DAQ",
                "model_name": None,
                "model_number": None,
                "serial_number": "serial-1",
                "vendor_name": None,
                "vendor_number": None,
                "part_number": None,
                "location": {
                    "minion_id": "minion-1",
                    "physical_location": None,
                    "parent": None,
                    "resource_uri": None,
                    "slot_number": 2,
                    "asset_presence": None,
                },
                "is_calibration_capable": True,
                "file_ids": ["file-1"],
                "updated_at": "2026-01-01T00:00:00Z",
                "keywords": ["production"],
                "properties": {"Owner": "Engineering"},
                "destination_workspace": "Target",
                "block_reason": None,
                "exclusion_reason": None,
            }
        ],
    }


@pytest.mark.parametrize("decision", ["include", "exclude", "block"])
def test_asset_decision_accepts_planning_outcomes(decision: str) -> None:
    """Discovery persists each supported terminal planning outcome."""
    asset = DiscoveredAsset(id="asset-1", workspace="Source", decision=decision)

    assert asset.decision == decision


def test_asset_discovery_rejects_unknown_decision() -> None:
    """Discovery cannot persist an unsupported planning outcome."""
    with pytest.raises(ValidationError, match="Input should be"):
        DiscoveredAsset(id="asset-1", workspace="Source", decision="retry")  # type: ignore[arg-type]

"""Versioned compact models for Asset Service discovery."""

from typing import Dict, Literal, Optional, Tuple

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from slcli.migration.schema import VersionedModel

AssetDecision = Literal["include", "exclude", "block"]


class _Persisted(BaseModel):
    model_config = ConfigDict(frozen=True)


class AssetLocation(_Persisted):
    """Supported source location fields needed to transform an asset."""

    minion_id: Optional[str] = None
    physical_location: Optional[str] = None
    parent: Optional[str] = None
    resource_uri: Optional[str] = None
    slot_number: Optional[int] = None
    asset_presence: Optional[str] = None


class DiscoveredAsset(_Persisted):
    """Compact source asset metadata and its migration planning decision."""

    id: str
    workspace: str
    decision: AssetDecision
    discovery_type: Optional[str] = None
    name: Optional[str] = None
    model_name: Optional[str] = None
    model_number: Optional[int] = None
    serial_number: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_number: Optional[int] = None
    part_number: Optional[str] = None
    location: AssetLocation = Field(default_factory=AssetLocation)
    is_calibration_capable: bool = False
    file_ids: Tuple[str, ...] = ()
    updated_at: Optional[AwareDatetime] = None
    keywords: Tuple[str, ...] = ()
    properties: Dict[str, str] = Field(default_factory=dict)
    destination_workspace: Optional[str] = None
    block_reason: Optional[str] = None
    exclusion_reason: Optional[str] = None


class AssetDiscovery(_Persisted, VersionedModel):
    """Persisted asset discovery results for later migration stages."""

    __test__ = False

    assets: Tuple[DiscoveredAsset, ...] = ()
    out_of_scope_count: int = 0

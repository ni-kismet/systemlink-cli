"""Versioned compact models for Test Monitor discovery."""

from typing import Optional, Tuple

from pydantic import AwareDatetime, BaseModel, ConfigDict

from slcli.migration.schema import VersionedModel


class _Persisted(BaseModel):
    model_config = ConfigDict(frozen=True)


class DiscoveredResult(_Persisted):
    """Compact terminal result metadata needed by later migration stages."""

    id: str
    product_id: Optional[str]
    workspace: str
    status: str
    updated_at: AwareDatetime


class DiscoveredProduct(_Persisted):
    """Compact product metadata with its inferred source workspace."""

    id: str
    workspace: str


class WorkspaceFailure(_Persisted):
    """A workspace-scoped discovery failure safe for summary output."""

    workspace: str
    error_type: str


class TestMonitorDiscovery(_Persisted, VersionedModel):
    """Successful partial discovery plus isolated workspace failures."""

    __test__ = False

    workspaces: Tuple[str, ...] = ()
    """Names of the workspaces that discovery queried."""
    products: Tuple[DiscoveredProduct, ...] = ()
    results: Tuple[DiscoveredResult, ...] = ()
    failures: Tuple[WorkspaceFailure, ...] = ()


class MigratedItem(_Persisted):
    """A source resource and the destination resource created for it."""

    source_id: str
    destination_id: str
    steps: int = 0
    """Steps migrated with a result."""


class FailedItem(_Persisted):
    """A source resource that did not migrate completely, safe for summary output."""

    source_id: str
    stage: str
    """Migration stage that failed, such as ``create`` or ``steps``."""
    error_type: str
    detail: Optional[str] = None
    destination_id: Optional[str] = None
    """Incomplete destination resource left behind, if any."""


class ProductConflict(_Persisted):
    """A source product skipped because its part number exists on the destination."""

    source_id: str
    part_number: str
    expected_workspace: str
    """Destination workspace name the product would have migrated to."""
    existing_id: str
    existing_workspace_id: Optional[str] = None
    existing_migration_id: Optional[str] = None
    existing_source_id: Optional[str] = None


class BatchResult(_Persisted, VersionedModel):
    """Outcome of migrating one batch; partial success is a normal outcome."""

    resource: str
    batch: int
    migrated: Tuple[MigratedItem, ...] = ()
    failed: Tuple[FailedItem, ...] = ()
    conflicts: Tuple[ProductConflict, ...] = ()

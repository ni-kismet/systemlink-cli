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

    products: Tuple[DiscoveredProduct, ...] = ()
    results: Tuple[DiscoveredResult, ...] = ()
    failures: Tuple[WorkspaceFailure, ...] = ()

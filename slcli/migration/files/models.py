"""Versioned compact models for SLS file discovery."""

from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.models import WorkspaceFailure


class _Persisted(BaseModel):
    model_config = ConfigDict(frozen=True)


class DiscoveredFile(_Persisted):
    """Compact file metadata needed by later migration stages."""

    id: str
    workspace: str
    name: Optional[str] = None
    size_bytes: Optional[int] = None


class FileDiscovery(_Persisted, VersionedModel):
    """Successful partial file discovery plus isolated workspace failures."""

    workspaces: Tuple[str, ...] = ()
    files: Tuple[DiscoveredFile, ...] = ()
    file_id_map: Dict[str, str] = Field(default_factory=dict)
    failures: Tuple[WorkspaceFailure, ...] = ()

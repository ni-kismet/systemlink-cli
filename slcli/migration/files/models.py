"""Versioned compact models for SLS file discovery and transfer."""

from typing import Any, Dict, Optional, Tuple

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
    properties: Dict[str, Any] = Field(default_factory=dict)


class FileDiscovery(_Persisted, VersionedModel):
    """Successful partial file discovery plus isolated workspace failures."""

    workspaces: Tuple[str, ...] = ()
    files: Tuple[DiscoveredFile, ...] = ()
    source_to_destination_id_map: Dict[str, str] = Field(default_factory=dict)
    failures: Tuple[WorkspaceFailure, ...] = ()


class FileFailure(_Persisted):
    """A source file that could not be transferred."""

    id: str
    workspace: str
    error_type: str


class FileTransfer(_Persisted, VersionedModel):
    """Transferred files and isolated per-file failures."""

    transferred: int = 0
    already_present: int = 0
    failures: Tuple[FileFailure, ...] = ()

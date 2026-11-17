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
    """Transferred files, their reassigned IDs, and isolated per-file failures.

    ``reassigned_ids`` maps an intended ID from discovery's ``source_to_destination_id_map``
    to the ID the file actually has on the destination, for files whose IDs differ.
    References to the intended ID must be rewritten to the actual ID.
    """

    transferred: int = 0
    already_present: int = 0
    reassigned_ids: Dict[str, str] = Field(default_factory=dict)
    failures: Tuple[FileFailure, ...] = ()

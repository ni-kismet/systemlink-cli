"""Migration identity and user-scoped run state."""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from slcli._version import __version__
from slcli.migration.schema import VersionedModel
from slcli.paths import get_state_dir

STATE_DIR_ENV = "SLCLI_MIGRATION_STATE_DIR"


class RunMetadata(VersionedModel):
    """Immutable, non-secret identity and inputs of one migration run.

    Mutable lifecycle state lives in Prefect flow and task runs, not here.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, frozen=True)

    migration_id: str
    cli_version: str = __version__
    source_profile: str
    workspace_mappings: Optional[Dict[str, str]]
    created_at: datetime


@dataclass(frozen=True)
class MigrationRun:
    """Paths for one migration run directory."""

    migration_id: str
    directory: Path

    @property
    def metadata_path(self) -> Path:
        """Return the run metadata path."""
        return self.directory / "metadata.json"

    @property
    def results_path(self) -> Path:
        """Return the Prefect result storage, the source of truth for completed tasks."""
        return self.directory / "results"

    @property
    def client_home(self) -> Path:
        """Return the Prefect home for the slcli process running the flow."""
        return self.directory / "prefect-client"

    @property
    def server_home(self) -> Path:
        """Return the home of a Prefect server managed by slcli for this run."""
        return self.directory / "prefect-server"

    def read_metadata(self) -> RunMetadata:
        """Read and validate this run's metadata."""
        metadata = RunMetadata.model_validate_json(self.metadata_path.read_text(encoding="utf-8"))
        if metadata.migration_id != self.migration_id:
            raise ValueError(f"Migration '{self.migration_id}' metadata has a different identity")
        return metadata

    def write_metadata(self, metadata: RunMetadata) -> None:
        """Atomically write this run's metadata."""
        temporary_path = self.metadata_path.with_suffix(".json.tmp")
        temporary_path.write_text(metadata.model_dump_json(by_alias=True, indent=2), "utf-8")
        temporary_path.replace(self.metadata_path)


def get_migration_root() -> Path:
    """Return the per-user directory that contains migration runs."""
    override = os.environ.get(STATE_DIR_ENV)
    return Path(override) if override else get_state_dir() / "migrations"


def _validate_created_migration_id(migration_id: str) -> None:
    """Require the canonical UUIDv4 text emitted by :func:`create_migration_run`."""
    try:
        parsed_id = uuid.UUID(migration_id)
    except ValueError as exc:
        raise ValueError(f"Migration ID '{migration_id}' is invalid") from exc
    if parsed_id.version != 4 or str(parsed_id) != migration_id:
        raise ValueError(f"Migration ID '{migration_id}' is invalid")


def create_migration_run(
    source_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    root: Optional[Path] = None,
) -> MigrationRun:
    """Create a new run directory, readable only by the current user."""
    root = root or get_migration_root()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    migration_id = str(uuid.uuid4())
    run = MigrationRun(migration_id, root / migration_id)
    run.directory.mkdir(mode=0o700)
    run.results_path.mkdir()
    run.client_home.mkdir()
    run.write_metadata(
        RunMetadata(
            migration_id=migration_id,
            source_profile=source_profile,
            workspace_mappings=workspace_mappings,
            created_at=datetime.now(timezone.utc),
        )
    )
    return run


def open_migration_run(
    migration_id: str, root: Optional[Path] = None
) -> Tuple[MigrationRun, RunMetadata]:
    """Open an existing run and its metadata."""
    _validate_created_migration_id(migration_id)
    run = MigrationRun(migration_id, (root or get_migration_root()) / migration_id)
    if not run.metadata_path.is_file():
        raise ValueError(f"Migration '{migration_id}' was not found")
    return run, run.read_metadata()

"""Tests for migration identity and run state."""

import json
import stat
import sys
import uuid
from pathlib import Path

import pytest

from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.schema import SCHEMA_VERSION
from slcli.migration.state import (
    STATE_DIR_ENV,
    MigrationDiscovery,
    MigrationPlan,
    create_migration_run,
    get_migration_root,
    open_migration_run,
)
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspaces import DiscoveredWorkspaces
from slcli.paths import get_state_dir


def test_new_run_persists_non_secret_versioned_metadata(tmp_path: Path) -> None:
    """Metadata holds identity and inputs only, never credentials."""
    run = create_migration_run("source", "destination", {"Lab": "Destination"}, tmp_path)

    assert run.directory == tmp_path / run.migration_id
    assert run.results_path.is_dir()
    assert run.client_home.is_dir()
    assert not run.server_home.exists()
    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert set(metadata) == {
        "schemaVersion",
        "migrationId",
        "cliVersion",
        "sourceProfile",
        "destinationProfile",
        "workspaceMappings",
        "productBatchSize",
        "resultBatchSize",
        "userReviewCheckpoint",
        "createdAt",
    }
    assert metadata["schemaVersion"] == SCHEMA_VERSION
    assert metadata["migrationId"] == run.migration_id
    assert metadata["sourceProfile"] == "source"
    assert metadata["workspaceMappings"] == {"Lab": "Destination"}


@pytest.mark.skipif(sys.platform == "win32", reason="Windows relies on per-user profile ACLs")
def test_run_directory_is_private_to_user(tmp_path: Path) -> None:
    """Only the invoking user can read migration state."""
    run = create_migration_run("source", "destination", None, tmp_path / "root")

    for directory in (tmp_path / "root", run.directory):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_opens_existing_run(tmp_path: Path) -> None:
    """An existing run restores its persisted inputs."""
    created = create_migration_run("source", "destination", {"Lab": "Destination"}, tmp_path)

    run, metadata = open_migration_run(created.migration_id, tmp_path)

    assert run == created
    assert metadata.workspace_mappings == {"Lab": "Destination"}


def test_old_metadata_does_not_claim_user_review_checkpoint(tmp_path: Path) -> None:
    """Runs created before user checkpoints must not be treated as new runs."""
    created = create_migration_run("source", "destination", None, tmp_path)
    metadata = json.loads(created.metadata_path.read_text(encoding="utf-8"))
    del metadata["userReviewCheckpoint"]
    created.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    _, reopened = open_migration_run(created.migration_id, tmp_path)
    assert not reopened.user_review_checkpoint


def test_saved_plan_preserves_file_ids_and_cannot_be_used_by_another_run(tmp_path: Path) -> None:
    """Reopening a run keeps the planned file IDs and validates the run identity."""
    created = create_migration_run("source", "destination", None, tmp_path)
    other = create_migration_run("source", "destination", None, tmp_path)
    with pytest.raises(FileNotFoundError):
        created.read_plan()

    plan = MigrationPlan(
        migration_id=created.migration_id,
        discovery=MigrationDiscovery(
            workspaces=DiscoveredWorkspaces(),
            files=FileDiscovery(
                files=(DiscoveredFile(id="source-file", workspace="Lab"),),
                source_to_destination_id_map={"source-file": "ef" * 12},
            ),
            test_monitor=TestMonitorDiscovery(),
        ),
    )
    created.write_plan(plan)
    reopened, _ = open_migration_run(created.migration_id, tmp_path)
    assert reopened.read_plan() == plan

    with pytest.raises(ValueError, match="different migration"):
        other.write_plan(plan)
    assert not other.plan_path.exists()
    other.plan_path.write_bytes(created.plan_path.read_bytes())
    with pytest.raises(ValueError, match="different migration"):
        other.read_plan()


def test_rejects_unknown_migration_id(tmp_path: Path) -> None:
    """An ID without a run directory is reported as not found."""
    with pytest.raises(ValueError, match="was not found"):
        open_migration_run(str(uuid.uuid4()), tmp_path)


@pytest.mark.parametrize(
    "migration_id",
    [
        "../outside",
        "/absolute/path",
        "no-such-run",
        str(uuid.uuid4()).upper(),
        str(uuid.uuid1()),
    ],
)
def test_rejects_ids_not_created_by_create_migration_run(migration_id: str, tmp_path: Path) -> None:
    """Only canonical UUIDv4 IDs emitted for migration runs can become paths."""
    with pytest.raises(ValueError, match="Migration ID .* is invalid"):
        open_migration_run(migration_id, tmp_path)


def test_rejects_metadata_for_another_run(tmp_path: Path) -> None:
    """A run directory cannot impersonate another migration."""
    created = create_migration_run("source", "destination", None, tmp_path)
    metadata = json.loads(created.metadata_path.read_text(encoding="utf-8"))
    metadata["migrationId"] = str(uuid.uuid4())
    created.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="different identity"):
        open_migration_run(created.migration_id, tmp_path)


def test_rejects_metadata_from_another_schema_version(tmp_path: Path) -> None:
    """Runs written by an incompatible CLI fail clearly instead of loading partially."""
    created = create_migration_run("source", "destination", None, tmp_path)
    metadata = json.loads(created.metadata_path.read_text(encoding="utf-8"))
    metadata["schemaVersion"] = SCHEMA_VERSION + 1
    created.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported schema version"):
        open_migration_run(created.migration_id, tmp_path)


def test_migration_root_defaults_to_user_state_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs live under the OS-standard slcli state directory unless overridden."""
    monkeypatch.delenv(STATE_DIR_ENV, raising=False)
    assert get_migration_root() == get_state_dir() / "migrations"

    monkeypatch.setenv(STATE_DIR_ENV, "/custom/root")
    assert get_migration_root() == Path("/custom/root")

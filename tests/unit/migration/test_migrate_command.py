"""Tests for the migrate command surface and run composition."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from unittest.mock import MagicMock

import click
import pytest
import requests
from click.testing import CliRunner, Result

from slcli import migrate_click
from slcli.migrate_click import register_migrate_command
from slcli.migration import command
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.flows.discover import MigrationDiscovery
from slcli.migration.flows.migrate import MigrationOutcome
from slcli.migration.state import STATE_DIR_ENV, MigrationRun, RunMetadata, create_migration_run
from slcli.migration.testmonitor.models import (
    DiscoveredProduct,
    DiscoveredResult,
    BatchResult,
    FailedItem,
    MigratedItem,
    ProductConflict,
    TestMonitorDiscovery,
    WorkspaceFailure,
)
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.workspace_client import Workspace
from slcli.migration.workspace_task import synchronize_workspaces_task
from slcli.migration.workspaces import discover_workspaces, synchronize_workspaces
from slcli.utils import ExitCodes

TEST_MONITOR_DISCOVERY = TestMonitorDiscovery(
    products=(DiscoveredProduct(id="p", workspace="Lab"),),
    results=(
        DiscoveredResult(
            id="r",
            product_id="p",
            workspace="Lab",
            status="PASSED",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ),
    failures=(WorkspaceFailure(workspace="Broken", error_type="HTTPError"),),
    workspaces=("Broken", "Lab"),
)
FILES_DISCOVERY = FileDiscovery(
    files=(DiscoveredFile(id="f", workspace="Lab", name="a.txt", size_bytes=3),),
    workspaces=("Broken", "Lab"),
)


def _migrate(*args: str) -> Result:
    @click.group()
    def cli() -> None:
        pass

    register_migrate_command(cli)
    return CliRunner().invoke(cli, ["migrate", *args])


def _named(names: Iterable[str]) -> List[Workspace]:
    return [Workspace(id=f"{name}-id", name=name) for name in names]


@dataclass
class FakeDiscovery:
    """Records discovery requests in place of a Prefect server and flow."""

    test_monitor_outcome: Optional[TestMonitorDiscovery] = TEST_MONITOR_DISCOVERY
    files_outcome: FileDiscovery = FILES_DISCOVERY
    calls: List[Dict[str, object]] = field(default_factory=list)
    state_root: Path = Path()
    source_workspaces: Tuple[str, ...] = ("Lab", "Default")
    destination_workspaces: Tuple[str, ...] = ("Lab", "Default", "Dest")
    created_destination_workspaces: List[str] = field(default_factory=list)
    migration: TestMonitorMigration = TestMonitorMigration()
    metadata: List[RunMetadata] = field(default_factory=list)
    destination_error: Optional[Exception] = None

    def runs(self) -> List[MigrationRun]:
        """Return the runs created under the state root."""
        return [MigrationRun(path.name, path) for path in self.state_root.iterdir()]


@pytest.fixture
def fake_discovery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeDiscovery:
    """Arrange profiles and state on disk and replace Prefect execution with a recorder."""
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "source": {"server": "https://source", "api-key": "key"},
                    "destination": {"server": "https://destination", "api-key": "key"},
                    "insecure": {"server": "http://source", "api-key": "k", "ssl-verify": False},
                }
            }
        ),
        encoding="utf-8",
    )
    fake = FakeDiscovery(state_root=tmp_path / "state")
    monkeypatch.setenv("SLCLI_CONFIG", str(config_path))
    monkeypatch.setenv(STATE_DIR_ENV, str(fake.state_root))

    @contextmanager
    def prefect_server(run: MigrationRun, api_url: Optional[str]) -> Generator[str, None, None]:
        yield api_url or "http://managed/api"

    def run_migration(run: MigrationRun, metadata: RunMetadata, api_url: str) -> MigrationOutcome:
        mappings = metadata.workspace_mappings
        workspaces = list(mappings) if mappings is not None else None
        fake.calls.append(
            {
                "run": run,
                "profile": metadata.source_profile,
                "workspaces": workspaces,
                "api_url": api_url,
            }
        )
        fake.metadata.append(metadata)
        discovered = discover_workspaces(_named(fake.source_workspaces), workspaces)
        if fake.test_monitor_outcome is None:
            raise RuntimeError("discovery failed")
        if fake.destination_error is not None:
            raise fake.destination_error

        def create_destination_workspace(name: str) -> Workspace:
            fake.created_destination_workspaces.append(name)
            return Workspace(id=f"{name}-created-id", name=name)

        mapping = synchronize_workspaces(
            discovered,
            _named(fake.destination_workspaces),
            create_destination_workspace,
            mappings,
        )
        return MigrationOutcome(
            mapping=mapping,
            discovery=MigrationDiscovery(
                workspaces=discovered,
                files=fake.files_outcome,
                test_monitor=fake.test_monitor_outcome,
            ),
            test_monitor=fake.migration,
        )

    monkeypatch.setattr(command, "prefect_server", prefect_server)
    monkeypatch.setattr(command, "run_migration", run_migration)
    return fake


def test_unknown_mapped_workspace_fails_discovery(fake_discovery: FakeDiscovery) -> None:
    """Mapping a workspace the source lacks fails the run during discovery."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab,Missing",
    )

    assert result.exit_code == 1
    assert "unknown source workspace: Missing" in result.output
    [run] = fake_discovery.runs()
    assert "WorkspaceMappingError" in (run.directory / "migration.log").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Lab", {"Lab": "Lab"}),
        (" Lab : Dest , Default ", {"Lab": "Dest", "Default": "Default"}),
        ("Lab\\:A:Dest", {"Lab:A": "Dest"}),
        ("Lab\\:A:Dest\\,B", {"Lab:A": "Dest,B"}),
        ("a\\, b:c\\:d", {"a, b": "c:d"}),
        ('Say "hi":/x/y', {'Say "hi"': "/x/y"}),
    ],
)
def test_workspace_mappings_support_escaping(value: str, expected: Dict[str, str]) -> None:
    """Escaped delimiters are part of names; quotes and slashes are literal."""
    assert migrate_click._parse_workspace_mappings(None, None, value) == expected  # type: ignore[arg-type]


def test_mapping_name_with_colon_reaches_discovery(fake_discovery: FakeDiscovery) -> None:
    """An escaped source name containing ':' resolves against discovered workspaces."""
    fake_discovery.source_workspaces = ("Lab:A", "Default")
    fake_discovery.destination_workspaces = ("Dest",)

    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab\\:A:Dest",
    )

    assert result.exit_code == 0, result.output
    assert fake_discovery.calls[0]["workspaces"] == ["Lab:A"]


def test_missing_mapped_destination_workspace_is_created(
    fake_discovery: FakeDiscovery,
) -> None:
    """A mapping to an absent destination workspace is created during synchronization."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab:Absent",
    )

    assert result.exit_code == 0, result.output
    assert fake_discovery.created_destination_workspaces == ["Absent"]


def test_failed_workspace_query_uses_api_exit_code(fake_discovery: FakeDiscovery) -> None:
    """A workspace query error raised by the run uses the API exit code."""
    fake_discovery.destination_error = requests.ConnectionError("unreachable")

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == ExitCodes.NETWORK_ERROR
    assert "unreachable" in result.output


def test_omitted_mappings_create_missing_same_named_destinations(
    fake_discovery: FakeDiscovery,
) -> None:
    """Without explicit mappings, missing destinations are created by source name."""
    fake_discovery.destination_workspaces = ("Lab",)

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output
    assert fake_discovery.created_destination_workspaces == ["Default"]


def test_workspace_mappings_are_persisted_for_the_run(fake_discovery: FakeDiscovery) -> None:
    """The requested workspace mapping is persisted as a migration input."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab:Dest",
    )

    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()
    assert run.read_metadata().destination_profile == "destination"
    assert run.read_metadata().workspace_mappings == {"Lab": "Dest"}


def test_run_log_records_inputs_without_secrets(fake_discovery: FakeDiscovery) -> None:
    """The run log identifies migration inputs without exposing credentials."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab",
    )

    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert f"migration={run.migration_id}" in log
    assert "profile=source endpoint=https://source workspaces=['Lab']" in log
    assert "key" not in log.replace("api-key", "")


def test_success_reports_log_path(fake_discovery: FakeDiscovery) -> None:
    """A successful run prints where its log was written."""
    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()
    assert f"Log: {run.directory / 'migration.log'}" in result.output


def test_every_workspace_failing_is_an_error(fake_discovery: FakeDiscovery) -> None:
    """Test Monitor discovery with no successful workspace exits non-zero after the summary."""
    fake_discovery.test_monitor_outcome = TEST_MONITOR_DISCOVERY.model_copy(
        update={"workspaces": ("Broken",)}
    )

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 1
    assert "Failed workspaces: 1" in result.output
    assert "Discovery failed for every workspace." in result.output


def test_no_workspaces_is_not_a_failure(fake_discovery: FakeDiscovery) -> None:
    """A source with no workspaces discovers nothing without erroring."""
    fake_discovery.test_monitor_outcome = TestMonitorDiscovery()

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output


def test_new_migration_discovers_selected_workspaces(fake_discovery: FakeDiscovery) -> None:
    """A new run shows the source and ID before invoking discovery."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab:Dest,Default",
    )

    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()
    assert result.output.index("Source: source (https://source)") < result.output.index(
        f"Migration ID: {run.migration_id}"
    )
    assert fake_discovery.calls == [
        {
            "run": run,
            "profile": "source",
            "workspaces": ["Lab", "Default"],
            "api_url": "http://managed/api",
        }
    ]
    metadata = run.read_metadata()
    assert metadata.workspace_mappings == {"Lab": "Dest", "Default": "Default"}


def test_omitted_mappings_discover_all_workspaces(fake_discovery: FakeDiscovery) -> None:
    """Without mappings the flow receives no workspace restriction."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--prefect-api-url",
        "http://external/api",
    )

    assert result.exit_code == 0, result.output
    assert fake_discovery.calls[0]["workspaces"] is None
    assert fake_discovery.calls[0]["api_url"] == "http://external/api"
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "prefect_server=external" in log


def test_insecure_source_is_warned(fake_discovery: FakeDiscovery) -> None:
    """Plain HTTP and disabled certificate verification are called out."""
    result = _migrate("--source-profile", "insecure", "--destination-profile", "destination")

    assert "does not use HTTPS" in result.output
    assert "verification is disabled" in result.output


def test_destination_profile_is_reused_by_migration_id(fake_discovery: FakeDiscovery) -> None:
    """A missing destination profile for an existing run fails before discovery."""
    run = create_migration_run("source", "gone", None, fake_discovery.state_root)

    result = _migrate("--migration-id", run.migration_id)

    assert result.exit_code == 1
    assert "Profile 'gone' not found" in result.output
    assert not fake_discovery.calls


def test_missing_profile_creates_no_run(fake_discovery: FakeDiscovery) -> None:
    """Profile errors happen before any migration state exists."""
    result = _migrate("--source-profile", "missing", "--destination-profile", "destination")

    assert result.exit_code != 0
    assert "Profile 'missing' not found" in result.output
    assert not fake_discovery.state_root.exists()


def test_failed_discovery_is_logged(fake_discovery: FakeDiscovery) -> None:
    """A run-level failure is logged; Prefect holds the failed flow-run state."""
    fake_discovery.test_monitor_outcome = None

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code != 0
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "Migration failed: RuntimeError: discovery failed" in log
    assert f"Log: {run.directory / 'migration.log'}" in result.output


def test_existing_migration_reuses_persisted_inputs(fake_discovery: FakeDiscovery) -> None:
    """A migration ID restores the original profile and workspace selection."""
    run = create_migration_run("source", "destination", {"Lab": "Dest"}, fake_discovery.state_root)

    result = _migrate("--migration-id", run.migration_id)

    assert result.exit_code == 0, result.output
    assert fake_discovery.calls[0]["profile"] == "source"
    assert fake_discovery.calls[0]["workspaces"] == ["Lab"]


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("readonly", [False, True])
@pytest.mark.parametrize("destination_exists", [False, True])
def test_destination_readonly_applies_to_workspace_creation(
    fake_discovery: FakeDiscovery,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    resume: bool,
    readonly: bool,
    destination_exists: bool,
) -> None:
    """New and resumed runs use the selected destination's current read-only setting."""
    run = create_migration_run("source", "destination", {"Lab": "New"}, fake_discovery.state_root)
    config_path = tmp_path / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["current-profile"] = "source"
    config["profiles"]["source"]["readonly"] = not readonly
    config["profiles"]["destination"]["readonly"] = readonly
    config_path.write_text(json.dumps(config), encoding="utf-8")

    session = MagicMock()
    session.get.return_value.json.return_value = {
        "workspaces": ([{"id": "existing-id", "name": "New"}] if destination_exists else [])
    }
    session.post.return_value.json.return_value = {"id": "created-id"}
    monkeypatch.setattr(
        "slcli.migration.connection.MigrationConnection.create_session",
        MagicMock(return_value=session),
    )

    def run_migration(run: MigrationRun, metadata: RunMetadata, api_url: str) -> MigrationOutcome:
        discovered = discover_workspaces([Workspace(id="lab-id", name="Lab")], None)
        mapping = synchronize_workspaces_task.fn(
            run.migration_id, metadata.destination_profile, discovered, metadata.workspace_mappings
        )
        return MigrationOutcome(
            discovery=MigrationDiscovery(
                workspaces=discovered, files=FileDiscovery(), test_monitor=TEST_MONITOR_DISCOVERY
            ),
            mapping=mapping,
            test_monitor=fake_discovery.migration,
        )

    monkeypatch.setattr(command, "run_migration", run_migration)
    if resume:
        result = _migrate("--migration-id", run.migration_id)
    else:
        result = _migrate(
            "--source-profile",
            "source",
            "--destination-profile",
            "destination",
            "--workspace-mappings",
            "Lab:New",
        )

    if readonly and not destination_exists:
        assert result.exit_code != 0
        assert "profile 'destination' is in readonly mode" in result.output
    else:
        assert result.exit_code == 0, result.output
    assert session.post.call_count == int(not readonly and not destination_exists)


def test_unknown_migration_id_is_reported(fake_discovery: FakeDiscovery) -> None:
    """Invalid IDs are a user error, not a traceback."""
    result = _migrate("--migration-id", "not-a-uuid")

    assert result.exit_code == 1
    assert "Migration ID 'not-a-uuid' is invalid" in result.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "Provide --source-profile and --destination-profile"),
        (["--source-profile", "source"], "Provide --source-profile and --destination-profile"),
        (["--migration-id", "id", "--source-profile", "source"], "cannot be combined"),
        (["--migration-id", "id", "--destination-profile", "d"], "cannot be combined"),
        (["--source-profile", "s", "--prefect-api-url", "not-a-url"], "HTTP or HTTPS URL"),
        (["--source-profile", "s", "--workspace-mappings", ""], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", ":Dest"], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", "Lab:"], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", "Lab,Lab:X"], "mapped more than once"),
        (["--source-profile", "s", "--workspace-mappings", "A:B:C"], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", "Lab\\"], "end with an escape"),
    ],
)
def test_rejects_invalid_usage(args: List[str], message: str) -> None:
    """Invalid option combinations fail before any migration work."""
    result = _migrate(*args)

    assert result.exit_code == 2
    assert message in result.output


MIGRATION = TestMonitorMigration(
    products=(
        BatchResult(
            resource="products",
            batch=0,
            migrated=(MigratedItem(source_id="p1", destination_id="d1"),),
            conflicts=(
                ProductConflict(
                    source_id="p2",
                    part_number="PN-2",
                    expected_workspace="Dest-id",
                ),
            ),
        ),
    ),
    results=(
        BatchResult(
            resource="results",
            batch=0,
            migrated=(MigratedItem(source_id="r1", destination_id="dr1", steps=3),),
            failed=(
                FailedItem(
                    source_id="r2",
                    stage="steps",
                    error_type="HTTPError",
                    destination_id="dr2",
                ),
            ),
        ),
    ),
)


def test_failed_items_exit_non_zero_after_summary(fake_discovery: FakeDiscovery) -> None:
    """Item failures fail the command; conflicts alone do not."""
    fake_discovery.migration = MIGRATION

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 1
    assert "Results failed: 1" in result.output
    assert "1 items failed to migrate." in result.output


def test_conflicts_alone_succeed(fake_discovery: FakeDiscovery) -> None:
    """A part-number conflict is reported without failing the run."""
    fake_discovery.migration = MIGRATION.model_copy(update={"results": ()})

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output
    assert "Product conflicts: 1" in result.output


def test_batch_sizes_are_persisted(fake_discovery: FakeDiscovery) -> None:
    """Hidden batch-size options are stored with the run and reused on resume."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--product-batch-size",
        "7",
        "--result-batch-size",
        "3",
    )
    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()

    resumed = _migrate("--migration-id", run.migration_id)

    assert resumed.exit_code == 0, resumed.output
    assert [(m.product_batch_size, m.result_batch_size) for m in fake_discovery.metadata] == [
        (7, 3),
        (7, 3),
    ]

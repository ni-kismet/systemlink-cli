"""Tests for the migrate command surface and run composition."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import click
import pytest
from click.testing import CliRunner, Result

from slcli import migrate_click
from slcli.migrate_click import register_migrate_command
from slcli.migration import command
from slcli.migration.flows.discover import MigrationDiscovery
from slcli.migration.state import STATE_DIR_ENV, MigrationRun, create_migration_run
from slcli.migration.testmonitor.models import (
    DiscoveredProduct,
    DiscoveredResult,
    TestMonitorDiscovery,
    WorkspaceFailure,
)
from slcli.migration.workspace_client import Workspace, WorkspaceClient

DISCOVERY = TestMonitorDiscovery(
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


def _migrate(*args: str) -> Result:
    @click.group()
    def cli() -> None:
        pass

    register_migrate_command(cli)
    return CliRunner().invoke(cli, ["migrate", *args])


@dataclass
class FakeDiscovery:
    """Records discovery requests in place of a Prefect server and flow."""

    outcome: Optional[TestMonitorDiscovery] = DISCOVERY
    calls: List[Dict[str, object]] = field(default_factory=list)
    state_root: Path = Path()
    source_workspaces: Tuple[str, ...] = ("Lab", "Default")
    destination_workspaces: Tuple[str, ...] = ("Lab", "Default", "Dest")

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

    def run_discovery(
        run: MigrationRun, source_profile: str, workspaces: Optional[List[str]], api_url: str
    ) -> MigrationDiscovery:
        fake.calls.append(
            {"run": run, "profile": source_profile, "workspaces": workspaces, "api_url": api_url}
        )
        if fake.outcome is None:
            raise RuntimeError("discovery failed")
        return MigrationDiscovery(test_monitor=fake.outcome)

    monkeypatch.setattr(command, "prefect_server", prefect_server)
    monkeypatch.setattr(command, "run_discovery", run_discovery)

    def query_workspaces(self: WorkspaceClient) -> Iterator[Workspace]:
        names = (
            fake.destination_workspaces if "destination" in self._url else fake.source_workspaces
        )
        return iter(Workspace(id=f"{name}-id", name=name) for name in names)

    monkeypatch.setattr(WorkspaceClient, "query_workspaces", query_workspaces)
    return fake


def test_unknown_mapped_workspace_fails_before_run(fake_discovery: FakeDiscovery) -> None:
    """Mapping a workspace the source lacks fails and creates no run."""
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
    assert not fake_discovery.state_root.exists()


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
    assert "Workspace mapping:\n  Lab:A -> Dest\n" in result.output
    assert fake_discovery.calls[0]["workspaces"] == ["Lab:A"]


def test_missing_destination_workspace_fails_before_run(fake_discovery: FakeDiscovery) -> None:
    """A mapping to a workspace the destination lacks fails without creating it."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab:Absent",
    )

    assert result.exit_code == 1
    assert "missing destination workspace: Lab -> Absent" in result.output
    assert "not created by migration" in result.output
    assert not fake_discovery.state_root.exists()


def test_omitted_mappings_require_every_same_named_destination(
    fake_discovery: FakeDiscovery,
) -> None:
    """Without mappings every source workspace needs a same-named destination."""
    fake_discovery.destination_workspaces = ("Lab",)

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 1
    assert "missing destination workspace: Default -> Default" in result.output
    assert "--workspace-mappings" in result.output
    assert not fake_discovery.calls


def test_mapping_is_shown_and_logged(fake_discovery: FakeDiscovery) -> None:
    """The resolved mapping is shown by name and logged with IDs."""
    result = _migrate(
        "--source-profile",
        "source",
        "--destination-profile",
        "destination",
        "--workspace-mappings",
        "Lab:Dest",
    )

    assert result.exit_code == 0, result.output
    assert "Workspace mapping:\n  Lab -> Dest\n" in result.output
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "Workspace mapping: ['Lab(Lab-id) -> Dest(Dest-id)']" in log
    assert run.read_metadata().destination_profile == "destination"


def test_run_log_records_lifecycle_without_secrets(fake_discovery: FakeDiscovery) -> None:
    """The run log identifies the migration, source, scope, and counts."""
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
    assert "products=1 results=1 failed_workspaces=['Broken']" in log
    assert "key" not in log.replace("api-key", "")


def test_summary_is_deterministic() -> None:
    """The summary reports counts and each failed workspace."""
    assert command.format_summary(DISCOVERY) == (
        "Test Monitor discovery:\n"
        "  Products: 1\n"
        "  Terminal results: 1\n"
        "  Failed workspaces: 1\n"
        "    Broken: HTTPError\n"
        "  Product workspaces were inferred without the failed workspaces."
    )


def test_summary_omits_failure_note_without_failures() -> None:
    """The inference caveat appears only when a workspace failed."""
    summary = command.format_summary(DISCOVERY.model_copy(update={"failures": ()}))

    assert summary.endswith("  Failed workspaces: 0")


def test_success_reports_log_path(fake_discovery: FakeDiscovery) -> None:
    """A successful run prints where its log was written."""
    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output
    [run] = fake_discovery.runs()
    assert f"Log: {run.directory / 'migration.log'}" in result.output


def test_every_workspace_failing_is_an_error(fake_discovery: FakeDiscovery) -> None:
    """Discovery with no successful workspace exits non-zero after the summary."""
    fake_discovery.outcome = DISCOVERY.model_copy(update={"workspaces": ("Broken",)})

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 1
    assert "Failed workspaces: 1" in result.output
    assert "Discovery failed for every workspace." in result.output


def test_no_workspaces_is_not_a_failure(fake_discovery: FakeDiscovery) -> None:
    """A source with no workspaces discovers nothing without erroring."""
    fake_discovery.outcome = TestMonitorDiscovery()

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code == 0, result.output


def test_new_migration_discovers_selected_workspaces(fake_discovery: FakeDiscovery) -> None:
    """A new run shows the source and ID before discovery, then the summary."""
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
    assert "Products: 1" in result.output
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
    fake_discovery.outcome = None

    result = _migrate("--source-profile", "source", "--destination-profile", "destination")

    assert result.exit_code != 0
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "Discovery failed: RuntimeError: discovery failed" in log
    assert f"Log: {run.directory / 'migration.log'}" in result.output


def test_existing_migration_reuses_persisted_inputs(fake_discovery: FakeDiscovery) -> None:
    """A migration ID restores the original profile and workspace selection."""
    run = create_migration_run("source", "destination", {"Lab": "Dest"}, fake_discovery.state_root)

    result = _migrate("--migration-id", run.migration_id)

    assert result.exit_code == 0, result.output
    assert fake_discovery.calls[0]["profile"] == "source"
    assert fake_discovery.calls[0]["workspaces"] == ["Lab"]


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

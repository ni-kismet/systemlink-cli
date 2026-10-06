"""Tests for the migrate command surface and run composition."""

import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import click
import pytest
from click.testing import CliRunner, Result

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
    monkeypatch.setattr(
        WorkspaceClient,
        "query_workspaces",
        lambda self: iter([Workspace(id="1", name="Lab"), Workspace(id="2", name="Default")]),
    )
    return fake


def test_unknown_mapped_workspace_fails_before_run(fake_discovery: FakeDiscovery) -> None:
    """Mapping a workspace the source lacks is a usage error and creates no run."""
    result = _migrate("--source-profile", "source", "--workspace-mappings", "Lab,Missing")

    assert result.exit_code == 2
    assert "unknown source workspace: Missing" in result.output
    assert not fake_discovery.state_root.exists()


def test_run_log_records_lifecycle_without_secrets(fake_discovery: FakeDiscovery) -> None:
    """The run log identifies the migration, source, scope, and counts."""
    result = _migrate("--source-profile", "source", "--workspace-mappings", "Lab")

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
        "    Broken: HTTPError"
    )


def test_new_migration_discovers_selected_workspaces(fake_discovery: FakeDiscovery) -> None:
    """A new run shows the source and ID before discovery, then the summary."""
    result = _migrate("--source-profile", "source", "--workspace-mappings", "Lab:Dest,Default")

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
    result = _migrate("--source-profile", "source", "--prefect-api-url", "http://external/api")

    assert result.exit_code == 0, result.output
    assert fake_discovery.calls[0]["workspaces"] is None
    assert fake_discovery.calls[0]["api_url"] == "http://external/api"
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "prefect_server=external" in log


def test_insecure_source_is_warned(fake_discovery: FakeDiscovery) -> None:
    """Plain HTTP and disabled certificate verification are called out."""
    result = _migrate("--source-profile", "insecure")

    assert "does not use HTTPS" in result.output
    assert "verification is disabled" in result.output


def test_missing_profile_creates_no_run(fake_discovery: FakeDiscovery) -> None:
    """Profile errors happen before any migration state exists."""
    result = _migrate("--source-profile", "missing")

    assert result.exit_code != 0
    assert "Profile 'missing' not found" in result.output
    assert not fake_discovery.state_root.exists()


def test_failed_discovery_is_logged(fake_discovery: FakeDiscovery) -> None:
    """A run-level failure is logged; Prefect holds the failed flow-run state."""
    fake_discovery.outcome = None

    result = _migrate("--source-profile", "source")

    assert result.exit_code != 0
    [run] = fake_discovery.runs()
    log = (run.directory / "migration.log").read_text(encoding="utf-8")
    assert "Discovery failed: RuntimeError" in log


def test_existing_migration_reuses_persisted_inputs(fake_discovery: FakeDiscovery) -> None:
    """A migration ID restores the original profile and workspace selection."""
    run = create_migration_run("source", {"Lab": "Dest"}, fake_discovery.state_root)

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
        ([], "Provide --source-profile"),
        (["--migration-id", "id", "--source-profile", "source"], "cannot be combined"),
        (["--source-profile", "s", "--prefect-api-url", "not-a-url"], "HTTP or HTTPS URL"),
        (["--source-profile", "s", "--workspace-mappings", ""], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", ":Dest"], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", "Lab:"], "SOURCE:DESTINATION"),
        (["--source-profile", "s", "--workspace-mappings", "Lab,Lab:X"], "mapped more than once"),
    ],
)
def test_rejects_invalid_usage(args: List[str], message: str) -> None:
    """Invalid option combinations fail before any migration work."""
    result = _migrate(*args)

    assert result.exit_code == 2
    assert message in result.output


def _run_python(code: str) -> "subprocess.CompletedProcess[str]":
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "COLUMNS": "200"}
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", env=environment
    )


@pytest.mark.slow
def test_cli_startup_does_not_import_migration_dependencies() -> None:
    """Normal CLI use does not pay for the optional migration extra."""
    result = _run_python(
        "import sys, slcli.main\n"
        "loaded = {'prefect', 'psutil', 'pydantic', 'slcli.migration'} & set(sys.modules)\n"
        "assert not loaded, loaded"
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.slow
@pytest.mark.parametrize("package", ["prefect", "psutil", "pydantic"])
def test_missing_migration_extra_is_actionable(package: str) -> None:
    """Without the migration extra the command explains how to install it."""
    result = _run_python(
        f"import sys; sys.modules[{package!r}] = None\n"
        "from click.testing import CliRunner\n"
        "from slcli.main import cli\n"
        "result = CliRunner().invoke(cli, ['migrate', '--source-profile', 'source'])\n"
        "print(result.output)\n"
        "sys.exit(result.exit_code)"
    )

    assert result.returncode == 1
    assert "systemlink-cli[migration]" in result.stdout


@pytest.mark.slow
@pytest.mark.parametrize(("missing", "visible"), [("", True), ("prefect", False)])
def test_help_lists_migrate_only_with_migration_extra(missing: str, visible: bool) -> None:
    """The command is a dev feature toggle: hidden from help unless the extra is installed."""
    result = _run_python(
        f"import sys; sys.modules.update({{{missing!r}: None}} if {missing!r} else {{}})\n"
        "from click.testing import CliRunner\n"
        "from slcli.main import cli\n"
        "print(CliRunner().invoke(cli, ['--help']).output)"
    )

    assert result.returncode == 0, result.stderr
    assert ("migrate" in result.stdout) is visible

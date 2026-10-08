"""Source-only E2E tests for migration discovery against SystemLink Server.

One seeded dataset in two fixture-owned workspaces is shared by every test:

=========  ==============================================  ==================
Product    Results                                         Owner workspace
=========  ==============================================  ==================
states     every status type, all in PRIMARY               PRIMARY
spanning   older PASSED in PRIMARY, newer FAILED in OTHER  OTHER
orphan     none                                            Default (unmapped)
=========  ==============================================  ==================

Mapped runs see only fixture workspaces, so they assert exact contents. Runs over
all workspaces assert exact contents of the fixture workspaces and tolerate
unrelated data elsewhere on the server.
"""

import os
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Dict, FrozenSet, Iterable, List, Optional, Sequence

import pytest
from click.testing import CliRunner

from slcli.main import cli
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.orchestration import run_discovery
from slcli.migration.state import STATE_DIR_ENV, create_migration_run
from slcli.migration.testmonitor.client import Product, Result, TestMonitorClient
from slcli.migration.testmonitor.discovery import DEFAULT_WORKSPACE, discover_test_monitor
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspace_client import WorkspaceClient
from slcli.ssl_trust import inject_os_trust
from tests.e2e.testmonitor_fixture import OwnedTestMonitorResources

PRIMARY = "e2e-slcli-migration-source"
OTHER = "e2e-slcli-migration-source-other"
FIXTURE_WORKSPACES = frozenset({PRIMARY, OTHER})
TERMINAL_STATES = ["DONE", "PASSED", "FAILED", "SKIPPED", "TERMINATED", "ERRORED", "TIMEDOUT"]
NON_TERMINAL_STATES = ["RUNNING", "CUSTOM"]

# Migration spans platforms through named profiles, so it has no sls/sle platform marker.
pytestmark = [pytest.mark.e2e_migration, pytest.mark.testmonitor]


@dataclass(frozen=True)
class Seeded:
    """IDs of the seeded dataset."""

    connection: MigrationConnection
    workspace_ids: Dict[str, str]
    states_product: str
    states_terminal_results: FrozenSet[str]
    spanning_product: str
    spanning_older_result: str
    spanning_newer_result: str
    orphan_product: str

    @property
    def primary_results(self) -> FrozenSet[str]:
        """Return the terminal results seeded in PRIMARY."""
        return self.states_terminal_results | {self.spanning_older_result}


def _result(part_number: str, status: str) -> Dict[str, object]:
    return {
        "programName": f"{part_number} {status}",
        "partNumber": part_number,
        "status": {"statusType": status, "statusName": status.title()},
    }


def _get_or_create_workspace(connection: MigrationConnection, name: str) -> str:
    existing = {w.name: w.id for w in WorkspaceClient(connection).query_workspaces()}
    if name in existing:
        return existing[name]
    response = connection.create_session().post(
        f"{connection.base_url}/niuser/v1/workspaces",
        json={"name": name, "enabled": True},
        timeout=30,
    )
    response.raise_for_status()
    return str(response.json()["id"])


@pytest.fixture(scope="module")
def seeded() -> Generator[Seeded, None, None]:
    """Seed the dataset once in fixture-owned workspaces and clean it up afterward."""
    profile = os.getenv("SLCLI_E2E_SOURCE_PROFILE")
    if not profile:
        pytest.skip("SLCLI_E2E_SOURCE_PROFILE is not configured")
    inject_os_trust()
    connection = resolve_migration_connection(profile)
    workspace_ids = {name: _get_or_create_workspace(connection, name) for name in (PRIMARY, OTHER)}
    resources = OwnedTestMonitorResources(connection, workspace_ids)
    resources.clean()
    try:
        run_id = uuid.uuid4().hex
        states, spanning, orphan = (
            f"migration-e2e-{n}-{run_id}" for n in ("states", "spanning", "orphan")
        )
        states_id, spanning_id, orphan_id = resources.create_products(
            [{"name": part, "partNumber": part} for part in (states, spanning, orphan)], PRIMARY
        )
        # Create a result for every state. Only results terminal states will be discovered.
        state_results = resources.create_results(
            [_result(states, status) for status in TERMINAL_STATES + NON_TERMINAL_STATES], PRIMARY
        )
        # The same product has results in 2 workspaces; the newer one decides its workspace.
        [older] = resources.create_results([_result(spanning, "PASSED")], PRIMARY)
        [newer] = resources.create_results([_result(spanning, "FAILED")], OTHER)
        yield Seeded(
            connection=connection,
            workspace_ids=workspace_ids,
            states_product=states_id,
            states_terminal_results=frozenset(state_results[: len(TERMINAL_STATES)]),
            spanning_product=spanning_id,
            spanning_older_result=older,
            spanning_newer_result=newer,
            orphan_product=orphan_id,
        )
    finally:
        resources.clean()


def _discover(
    seeded: Seeded, workspaces: Optional[List[str]], prefect_api_url: str, state_root: Path
) -> TestMonitorDiscovery:
    """Run the production discovery flow as ``slcli migrate`` would for a new run."""
    profile = seeded.connection.profile_name
    mappings = {name: name for name in workspaces} if workspaces is not None else None
    run = create_migration_run(profile, mappings, state_root)
    return run_discovery(run, profile, workspaces, prefect_api_url).test_monitor


def _products(discovery: TestMonitorDiscovery, workspaces: AbstractSet[str]) -> Dict[str, str]:
    return {p.id: p.workspace for p in discovery.products if p.workspace in workspaces}


def _results(discovery: TestMonitorDiscovery, workspace: str) -> FrozenSet[str]:
    return frozenset(r.id for r in discovery.results if r.workspace == workspace)


def test_all_workspaces(seeded: Seeded, test_prefect_server: str, tmp_path: Path) -> None:
    """Without mappings, fixture workspaces hold exactly the seeded terminal results."""
    discovery = _discover(seeded, None, test_prefect_server, tmp_path)

    assert discovery.failures == ()
    assert _results(discovery, PRIMARY) == seeded.primary_results
    assert _results(discovery, OTHER) == {seeded.spanning_newer_result}
    assert _products(discovery, FIXTURE_WORKSPACES) == {
        seeded.states_product: PRIMARY,
        seeded.spanning_product: OTHER,
    }
    assert _products(discovery, {DEFAULT_WORKSPACE})[seeded.orphan_product] == DEFAULT_WORKSPACE


def test_mapped_workspace(seeded: Seeded, test_prefect_server: str, tmp_path: Path) -> None:
    """A mapped workspace yields only its terminal results and the products it owns."""
    discovery = _discover(seeded, [PRIMARY], test_prefect_server, tmp_path)

    assert discovery.failures == ()
    assert {r.id for r in discovery.results} == seeded.primary_results
    # The service stores the TIMEDOUT input as TIMED_OUT.
    assert {r.status for r in discovery.results} == {
        "PASSED",
        "FAILED",
        "TERMINATED",
        "ERRORED",
        "TIMED_OUT",
    }
    assert {r.id: r.product_id for r in discovery.results} == {
        **{result: seeded.states_product for result in seeded.states_terminal_results},
        seeded.spanning_older_result: seeded.spanning_product,
    }
    assert _products(discovery, FIXTURE_WORKSPACES) == {seeded.states_product: PRIMARY}
    assert {p.workspace for p in discovery.products} == {PRIMARY}


def test_mapped_default_excludes_products_without_results(
    seeded: Seeded, test_prefect_server: str, tmp_path: Path
) -> None:
    """Products without results are only migrated when all workspaces are discovered."""
    discovery = _discover(seeded, [DEFAULT_WORKSPACE], test_prefect_server, tmp_path)

    assert seeded.orphan_product not in {p.id for p in discovery.products}


class _FailingWorkspace:
    """Delegate to live Test Monitor queries except for one failing workspace."""

    def __init__(self, client: TestMonitorClient, failing_workspace_id: str) -> None:
        self._client = client
        self._failing_workspace_id = failing_workspace_id

    def query_products(self) -> Iterable[Product]:
        """Return live products."""
        return self._client.query_products()

    def query_results(
        self, filter_expr: Optional[str] = None, substitutions: Optional[Sequence[str]] = None
    ) -> Iterable[Result]:
        """Fail the configured workspace and delegate every other query."""
        if substitutions and substitutions[0] == self._failing_workspace_id:
            raise ConnectionError("injected workspace failure")
        return self._client.query_results(filter_expr, substitutions)


def test_workspace_failure_preserves_other_workspaces(seeded: Seeded) -> None:
    """A failed workspace is reported while other workspaces are still discovered.

    Failure injection needs a seam below the Prefect task, so this calls the
    discovery policy directly with live queries.
    """
    client = _FailingWorkspace(TestMonitorClient(seeded.connection), seeded.workspace_ids[OTHER])
    workspaces = {w.name: w.id for w in WorkspaceClient(seeded.connection).query_workspaces()}

    discovery = discover_test_monitor(client, workspaces)

    assert [(f.workspace, f.error_type) for f in discovery.failures] == [(OTHER, "ConnectionError")]
    assert _results(discovery, PRIMARY) == seeded.primary_results
    assert _results(discovery, OTHER) == frozenset()
    assert seeded.orphan_product not in {p.id for p in discovery.products}


def test_migrate_cli(
    seeded: Seeded, test_prefect_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``slcli migrate`` summarizes the mapped workspace and records the run."""
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))

    result = CliRunner().invoke(
        cli,
        [
            "migrate",
            "--source-profile",
            seeded.connection.profile_name,
            "--workspace-mappings",
            PRIMARY,
            "--prefect-api-url",
            test_prefect_server,
        ],
    )

    assert result.exit_code == 0, result.output
    assert (
        f"  Products: 1\n  Terminal results: {len(seeded.primary_results)}\n"
        "  Failed workspaces: 0"
    ) in result.output
    [run_directory] = tmp_path.iterdir()
    assert f"Migration ID: {run_directory.name}" in result.output
    assert "Discovery completed" in (run_directory / "migration.log").read_text("utf-8")
    assert any((run_directory / "results").iterdir())

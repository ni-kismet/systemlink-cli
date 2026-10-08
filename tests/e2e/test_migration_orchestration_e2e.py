"""Prefect-backed tests for persisted migration discovery."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from slcli.migration.orchestration import prefect_server, run_discovery
from slcli.migration.state import create_migration_run
from slcli.migration.testmonitor.discovery_task import discover_test_monitor_task
from slcli.migration.testmonitor.models import DiscoveredProduct, TestMonitorDiscovery

# Uses a real Prefect server, so too slow for unit tests.
pytestmark = pytest.mark.e2e_migration

DISCOVERY = TestMonitorDiscovery(products=(DiscoveredProduct(id="p", workspace="Lab"),))


@dataclass
class FakeSource:
    """Records task executions in place of querying a source server."""

    fail: bool = False
    calls: List[Dict[str, object]] = field(default_factory=list)


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch) -> FakeSource:
    """Replace the Test Monitor task body; Prefect still persists and caches it."""
    fake = FakeSource()

    def discover(
        migration_id: str, source_profile: str, workspaces: Optional[List[str]]
    ) -> TestMonitorDiscovery:
        fake.calls.append(
            {"migration_id": migration_id, "profile": source_profile, "workspaces": workspaces}
        )
        if fake.fail:
            raise RuntimeError("source unavailable")
        return DISCOVERY

    monkeypatch.setattr(discover_test_monitor_task, "fn", discover)
    return fake


def test_discovery_persists_typed_task_result(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """The flow returns typed results and persists them in the run's storage."""
    run = create_migration_run("source", {"Lab": "Lab"}, tmp_path)

    discovery = run_discovery(run, "source", ["Lab"], test_prefect_server)

    assert discovery.test_monitor == DISCOVERY
    assert fake_source.calls == [
        {"migration_id": run.migration_id, "profile": "source", "workspaces": ["Lab"]}
    ]
    assert len(list(run.results_path.iterdir())) == 2
    assert not run.server_home.exists()


def test_discovery_is_cached_per_input(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """Repeating the same inputs reuses the persisted task; new inputs recompute."""
    run = create_migration_run("source", None, tmp_path)

    first = run_discovery(run, "source", ["Lab"], test_prefect_server)
    second = run_discovery(run, "source", ["Lab"], test_prefect_server)
    run_discovery(run, "source", ["Other"], test_prefect_server)

    assert second == first
    assert [call["workspaces"] for call in fake_source.calls] == [["Lab"], ["Other"]]


def test_failed_run_does_not_affect_later_runs(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """A run-level failure surfaces and leaves the shared server usable."""
    fake_source.fail = True
    with pytest.raises(RuntimeError, match="source unavailable"):
        run_discovery(
            create_migration_run("source", None, tmp_path), "source", None, test_prefect_server
        )

    fake_source.fail = False
    run = create_migration_run("source", None, tmp_path)

    assert run_discovery(run, "source", None, test_prefect_server).test_monitor == DISCOVERY


# Restarting over the same database exercises OS process and file-lock handling.
@pytest.mark.full_os_client_matrix
def test_managed_server_restart_reuses_persisted_discovery(
    fake_source: FakeSource, tmp_path: Path
) -> None:
    """A new managed server over the same run restores discovery without recomputing."""
    run = create_migration_run("source", None, tmp_path)

    with prefect_server(run) as api_url:
        first = run_discovery(run, "source", None, api_url)
    with prefect_server(run) as api_url:
        second = run_discovery(run, "source", None, api_url)

    assert second == first
    assert len(fake_source.calls) == 1
    assert (run.server_home / "prefect.db").is_file()


def test_cached_discovery_does_not_depend_on_server_history(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """Result storage alone restores a run; any server can serve the next flow."""
    run = create_migration_run("source", None, tmp_path)
    first = run_discovery(run, "source", None, test_prefect_server)

    with prefect_server(run) as fresh_server_url:
        second = run_discovery(run, "source", None, fresh_server_url)

    assert second == first
    assert len(fake_source.calls) == 1

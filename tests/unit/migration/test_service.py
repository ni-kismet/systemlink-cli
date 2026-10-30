"""Tests for migration service tasks and the flow's thread pool."""

import sys
from typing import List, Optional

import pytest
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.transactions import CommitMode, get_transaction

from slcli.migration.flows import service
from slcli.migration.flows.migrate import migrate_flow
from slcli.migration.testmonitor.pipeline import migrate_test_monitor_task


def _max_workers(runner: object) -> int:
    assert isinstance(runner, ThreadPoolTaskRunner)
    return runner._max_workers


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> List[object]:
    """Isolate the service registry from the services the application declares."""
    tasks: List[object] = []
    monkeypatch.setattr(service, "SERVICE_TASKS", tasks)
    return tasks


def test_service_body_runs_in_an_eager_transaction(registry: List[object]) -> None:
    """Batch results commit when each batch finishes, not when the service does."""

    @service.service_task("probe")
    def probe() -> Optional[CommitMode]:
        txn = get_transaction()
        return txn.commit_mode if txn else None

    assert probe.fn() == CommitMode.EAGER
    assert registry == [probe]


def test_pool_reserves_a_worker_per_service(registry: List[object]) -> None:
    """A bounded pool leaves room for batches while every service waits."""
    registry.extend([object(), object()])

    assert _max_workers(service.migration_task_runner(3)) == 5


def test_unbounded_pool_ignores_prefect_thread_pool_setting(
    registry: List[object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Prefect-wide worker limit cannot starve batches behind waiting services."""
    monkeypatch.setenv("PREFECT_TASKS_RUNNER_THREAD_POOL_MAX_WORKERS", "1")

    assert _max_workers(service.migration_task_runner()) == sys.maxsize


def test_batch_workers_must_be_positive(registry: List[object]) -> None:
    """Zero batch workers would leave services waiting forever."""
    with pytest.raises(ValueError):
        service.migration_task_runner(0)


def test_application_services_are_registered() -> None:
    """Every service task the migration flow submits reserves a worker."""
    assert migrate_test_monitor_task in service.SERVICE_TASKS
    assert _max_workers(migrate_flow.task_runner) > len(service.SERVICE_TASKS)

"""Service tasks: one Prefect task per resource type that runs its own batch tasks."""

import functools
import sys
from typing import Any, Callable, List, Optional, ParamSpec, TypeVar, cast

from prefect import Task, task
from prefect.cache_policies import NO_CACHE
from prefect.futures import PrefectFuture
from prefect.task_runners import TaskRunner, ThreadPoolTaskRunner
from prefect.transactions import CommitMode, transaction

_P = ParamSpec("_P")
_R = TypeVar("_R")

SERVICE_TASKS: List[Task] = []  # type: ignore[type-arg]


def service_task(name: str) -> Callable[[Callable[_P, _R]], Task[_P, _R]]:
    """Declare the task that migrates one resource type through batch tasks.

    The body runs in an eager transaction. By default, nested task results are
    staged in the parent task's transaction and discarded if the parent does not
    finish, so a resumed run would migrate completed batches again. Eager commits
    persist each batch result as soon as that batch finishes.

    Service tasks are registered so :func:`migration_task_runner` can reserve a
    worker for each one while it waits for its batches.

    Args:
        name: Prefect task name.
    """

    def decorate(fn: Callable[_P, _R]) -> Task[_P, _R]:
        @functools.wraps(fn)
        def run_eagerly(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with transaction(commit_mode=CommitMode.EAGER):
                return fn(*args, **kwargs)

        # Batch tasks are the unit of caching; the service only composes them.
        service: Task[_P, _R] = task(name=name, cache_policy=NO_CACHE)(run_eagerly)
        SERVICE_TASKS.append(service)
        return service

    return decorate


def migration_task_runner(batch_workers: Optional[int] = None) -> TaskRunner[PrefectFuture[Any]]:
    """Return the thread pool for the migration flow.

    Each running service task holds a worker while it waits for its batches, so
    a pool no larger than the number of services deadlocks. The pool reserves a
    worker per registered service on top of ``batch_workers``.

    Args:
        batch_workers: Batch tasks that may run at once; unbounded when None,
            regardless of Prefect's thread pool setting.
    """
    if batch_workers is None:
        max_workers = sys.maxsize
    elif batch_workers < 1:
        raise ValueError("batch_workers must be at least 1")
    else:
        max_workers = len(SERVICE_TASKS) + batch_workers
    # The flow decorator's annotation does not accept ThreadPoolTaskRunner's future type.
    return cast(TaskRunner[PrefectFuture[Any]], ThreadPoolTaskRunner(max_workers=max_workers))

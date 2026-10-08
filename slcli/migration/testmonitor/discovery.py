"""Test Monitor discovery and workspace assignment policy."""

import logging
from dataclasses import dataclass, field
from typing import (
    AbstractSet,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
)

from slcli.migration.testmonitor.client import Product, Result
from slcli.migration.testmonitor.models import (
    DiscoveredProduct,
    DiscoveredResult,
    TestMonitorDiscovery,
    WorkspaceFailure,
)

DEFAULT_WORKSPACE = "Default"
_logger = logging.getLogger(__name__)
# Terminal values of the Test Monitor StatusType enum. The service accepts TIMEDOUT
# on write and stores TIMED_OUT, so both are recognized.
TERMINAL_RESULT_STATES = frozenset(
    {"PASSED", "FAILED", "TERMINATED", "ERRORED", "TIMEDOUT", "TIMED_OUT"}
)


class TestMonitorQuery(Protocol):
    """Queries required by Test Monitor discovery."""

    def query_products(self) -> Iterable[Product]:
        """Return all Test Monitor products."""
        ...

    def query_results(
        self,
        filter_expr: Optional[str] = None,
        substitutions: Optional[Sequence[str]] = None,
    ) -> Iterable[Result]:
        """Return Test Monitor results matching a parameterized filter."""
        ...


WorkspacedResult = Tuple[str, Result]
"""A result paired with the name of the workspace it was discovered in."""


@dataclass
class _ResultScan:
    """Results gathered from every workspace that could be queried."""

    selected_terminal: List[WorkspacedResult] = field(default_factory=list)
    newest_by_part_number: Dict[str, WorkspacedResult] = field(default_factory=dict)
    failures: List[WorkspaceFailure] = field(default_factory=list)

    def add_workspace(self, workspace: str, results: Iterable[Result], selected: bool) -> None:
        for result in results:
            if selected and result.status.status_type in TERMINAL_RESULT_STATES:
                self.selected_terminal.append((workspace, result))
            if result.part_number:
                current = self.newest_by_part_number.get(result.part_number)
                if current is None or result.updated_at > current[1].updated_at:
                    self.newest_by_part_number[result.part_number] = (workspace, result)


def _scan_results(
    client: TestMonitorQuery, workspaces: Mapping[str, str], selected: AbstractSet[str]
) -> _ResultScan:
    scan = _ResultScan()
    for workspace, workspace_id in workspaces.items():
        try:
            # Materialize per workspace so a mid-pagination failure contributes nothing.
            results = list(client.query_results("workspace == @0", [workspace_id]))
        except Exception as exc:
            _logger.warning("Workspace %s discovery failed: %s", workspace, type(exc).__name__)
            scan.failures.append(
                WorkspaceFailure(workspace=workspace, error_type=type(exc).__name__)
            )
            continue
        scan.add_workspace(workspace, results, workspace in selected)
    return scan


def infer_product_workspace(
    part_number: str,
    newest_by_part_number: Mapping[str, WorkspacedResult],
    selected: AbstractSet[str],
    migrate_products_with_no_results: bool,
) -> Optional[str]:
    """Infer the source workspace that owns a product, if it is selected.

    A product belongs to the workspace of its most recently updated result across
    all workspaces, even when only a subset is selected. A product with no results
    belongs to Default and is included only when ``migrate_products_with_no_results``.
    """
    newest = newest_by_part_number.get(part_number)
    if newest is not None:
        workspace = newest[0]
    elif migrate_products_with_no_results:
        workspace = DEFAULT_WORKSPACE
    else:
        return None
    return workspace if workspace in selected else None


def discover_test_monitor(
    client: TestMonitorQuery,
    all_workspaces: Mapping[str, str],
    selected_workspaces: Optional[Collection[str]] = None,
) -> TestMonitorDiscovery:
    """Discover products and terminal results owned by the selected workspaces.

    Products with no results are included only when all workspaces are discovered
    without failures, since a failed workspace could hide a product's results.

    Args:
        client: Test Monitor queries for the source server.
        all_workspaces: Every accessible source workspace, by name to ID.
        selected_workspaces: Workspace names to discover; all workspaces when None.
    """
    selected = set(all_workspaces if selected_workspaces is None else selected_workspaces)
    unknown = selected.difference(all_workspaces)
    if unknown:
        raise ValueError(f"Unknown selected workspace: {', '.join(sorted(unknown))}")

    scan = _scan_results(client, all_workspaces, selected)
    migrate_products_with_no_results = selected_workspaces is None and not scan.failures
    products: List[DiscoveredProduct] = []
    product_ids_by_part_number: Dict[str, str] = {}
    for product in client.query_products():
        product_ids_by_part_number[product.part_number] = product.id
        workspace = infer_product_workspace(
            product.part_number,
            scan.newest_by_part_number,
            selected,
            migrate_products_with_no_results,
        )
        if workspace is not None:
            products.append(DiscoveredProduct(id=product.id, workspace=workspace))

    results = [
        DiscoveredResult(
            id=result.id,
            product_id=product_ids_by_part_number.get(result.part_number or ""),
            workspace=workspace,
            status=result.status.status_type,
            updated_at=result.updated_at,
        )
        for workspace, result in scan.selected_terminal
    ]
    return TestMonitorDiscovery(
        products=tuple(sorted(products, key=lambda item: (item.workspace, item.id))),
        results=tuple(sorted(results, key=lambda item: (item.workspace, item.id))),
        failures=tuple(sorted(scan.failures, key=lambda item: item.workspace)),
    )

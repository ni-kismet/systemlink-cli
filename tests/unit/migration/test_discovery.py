"""Tests for Test Monitor discovery and workspace assignment policy."""

from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Set, Union

import pytest

from slcli.migration.testmonitor.client import Product, Result, ResultStatus
from slcli.migration.testmonitor.discovery import (
    DEFAULT_WORKSPACE,
    discover_test_monitor,
    infer_product_workspace,
)
from slcli.migration.testmonitor.models import TestMonitorDiscovery


class FakeTestMonitor:
    """Serve products and per-workspace results; an exception fails that workspace."""

    def __init__(
        self,
        products: List[Product],
        results_by_workspace_id: Dict[str, Union[List[Result], Exception]],
    ) -> None:
        """Store the source data."""
        self._products = products
        self._results = results_by_workspace_id

    def query_products(self) -> Iterable[Product]:
        """Return every product."""
        return self._products

    def query_results(
        self, filter_expr: Optional[str] = None, substitutions: Optional[Sequence[str]] = None
    ) -> Iterable[Result]:
        """Return results for the workspace ID in the parameterized filter."""
        assert filter_expr == "workspace == @0" and substitutions is not None
        results = self._results[substitutions[0]]
        if isinstance(results, Exception):
            raise results
        return results


def _product(part_number: str) -> Product:
    return Product(id=f"product-{part_number}", part_number=part_number)


def _result(
    result_id: str,
    part_number: str,
    updated_at: str = "2026-01-01T00:00:00Z",
    status: str = "PASSED",
) -> Result:
    return Result(
        id=result_id,
        part_number=part_number,
        status=ResultStatus(status_type=status),
        updated_at=datetime.fromisoformat(updated_at),
    )


def _workspaces(*names: str) -> Dict[str, str]:
    return {name: f"{name}-id" for name in names}


def _product_workspaces(discovery: TestMonitorDiscovery) -> Dict[str, str]:
    return {product.id: product.workspace for product in discovery.products}


def test_product_belongs_to_workspace_of_newest_result() -> None:
    """A product spanning workspaces belongs to its most recently updated result."""
    source = FakeTestMonitor(
        [_product("p")],
        {
            "Alpha-id": [_result("old", "p", "2026-01-01T00:00:00Z")],
            "Beta-id": [_result("new", "p", "2026-02-01T00:00:00Z", "FAILED")],
        },
    )

    discovery = discover_test_monitor(source, _workspaces("Alpha", "Beta"))

    assert _product_workspaces(discovery) == {"product-p": "Beta"}
    assert [(r.id, r.workspace, r.product_id) for r in discovery.results] == [
        ("old", "Alpha", "product-p"),
        ("new", "Beta", "product-p"),
    ]


def test_newest_result_compares_instants_across_offsets() -> None:
    """08:00:01-05:00 is newer than 12:00Z even though its wall-clock time is earlier."""
    source = FakeTestMonitor(
        [_product("p")],
        {
            "Alpha-id": [_result("utc", "p", "2026-01-01T12:00:00Z")],
            "Beta-id": [_result("offset", "p", "2026-01-01T08:00:01-05:00")],
        },
    )

    discovery = discover_test_monitor(source, _workspaces("Alpha", "Beta"))

    assert _product_workspaces(discovery) == {"product-p": "Beta"}


def test_only_api_terminal_states_are_discovered() -> None:
    """Both TIMEDOUT forms are terminal; running and custom states are not."""
    states = ["DONE", "PASSED", "FAILED", "SKIPPED", "TERMINATED", "ERRORED"]
    states += ["TIMEDOUT", "TIMED_OUT", "RUNNING", "WAITING", "MY_CUSTOM_STATE"]
    source = FakeTestMonitor(
        [_product("p")],
        {"Alpha-id": [_result(state, "p", status=state) for state in states]},
    )

    discovery = discover_test_monitor(source, _workspaces("Alpha"))

    assert {result.id for result in discovery.results} == set(states[:8])


def test_non_terminal_results_still_assign_product_workspace() -> None:
    """Ownership comes from any associated result, not only migrated ones."""
    source = FakeTestMonitor(
        [_product("p")], {"Alpha-id": [_result("running", "p", status="RUNNING")]}
    )

    discovery = discover_test_monitor(source, _workspaces("Alpha"))

    assert discovery.results == ()
    assert _product_workspaces(discovery) == {"product-p": "Alpha"}


def test_omitted_selection_discovers_all_workspaces() -> None:
    """Without mappings, every workspace including Default is in scope."""
    source = FakeTestMonitor(
        [_product("p"), _product("orphan")],
        {"Alpha-id": [_result("r", "p")], "Default-id": []},
    )

    discovery = discover_test_monitor(source, _workspaces("Alpha", DEFAULT_WORKSPACE))

    assert _product_workspaces(discovery) == {
        "product-p": "Alpha",
        "product-orphan": DEFAULT_WORKSPACE,
    }


def test_no_result_products_require_all_workspaces() -> None:
    """Products without results are included only when no workspaces are mapped."""
    source = FakeTestMonitor([_product("orphan")], {"Alpha-id": [], "Default-id": []})
    workspaces = _workspaces("Alpha", DEFAULT_WORKSPACE)

    mapped_default = discover_test_monitor(source, workspaces, [DEFAULT_WORKSPACE])
    all_workspaces = discover_test_monitor(source, workspaces)

    assert mapped_default.products == ()
    assert _product_workspaces(all_workspaces) == {"product-orphan": DEFAULT_WORKSPACE}


def test_selection_excludes_products_owned_by_unselected_workspace() -> None:
    """A product whose newest result is in an unselected workspace is skipped."""
    source = FakeTestMonitor(
        [_product("outside"), _product("inside")],
        {"Lab-id": [_result("r1", "inside")], "Other-id": [_result("r2", "outside")]},
    )

    discovery = discover_test_monitor(source, _workspaces("Lab", "Other"), ["Lab"])

    assert _product_workspaces(discovery) == {"product-inside": "Lab"}
    assert [result.id for result in discovery.results] == ["r1"]


def test_workspace_failure_preserves_partial_results() -> None:
    """A failed workspace is reported by type only and others are still discovered."""
    source = FakeTestMonitor(
        [_product("p")],
        {"Broken-id": RuntimeError("sensitive response"), "Working-id": [_result("r", "p")]},
    )

    discovery = discover_test_monitor(source, _workspaces("Broken", "Working"))

    assert [result.id for result in discovery.results] == ["r"]
    assert [(f.workspace, f.error_type) for f in discovery.failures] == [("Broken", "RuntimeError")]


def test_failed_workspace_contributes_no_partial_pages() -> None:
    """Results yielded before a mid-pagination failure are discarded."""

    def failing_pages() -> Iterable[Result]:
        yield _result("partial", "p")
        raise ConnectionError("page 2 failed")

    class PartiallyFailing(FakeTestMonitor):
        def query_results(
            self, filter_expr: Optional[str] = None, substitutions: Optional[Sequence[str]] = None
        ) -> Iterable[Result]:
            return failing_pages()

    discovery = discover_test_monitor(PartiallyFailing([], {}), _workspaces("Alpha"))

    assert discovery.results == ()
    assert [f.workspace for f in discovery.failures] == ["Alpha"]


def test_failure_skips_products_with_no_results() -> None:
    """A failed workspace could hide a product's results, so it is not migrated."""
    # Products with no results are rare and easy to manually migrate. Skipping is
    # relatively harmless. Workspace-specific results query failures may-or-may-not
    # be rare (or transient, or user specific), but incorrectly migrating their products
    # Default could cause problems on future migrations.
    source = FakeTestMonitor(
        [_product("p")], {"Default-id": [], "Broken-id": RuntimeError("unavailable")}
    )

    discovery = discover_test_monitor(source, _workspaces(DEFAULT_WORKSPACE, "Broken"))

    assert discovery.products == ()


def test_rejects_unknown_selected_workspace() -> None:
    """Selected names must be existing source workspaces."""
    with pytest.raises(ValueError, match="Unknown selected workspace: Missing"):
        discover_test_monitor(FakeTestMonitor([], {}), _workspaces("Alpha"), ["Missing"])


@pytest.mark.parametrize(
    ("newest_workspace", "selected", "migrate_no_results", "expected"),
    [
        ("Other", {"Other"}, False, "Other"),
        ("Other", {DEFAULT_WORKSPACE}, True, None),
        (None, {DEFAULT_WORKSPACE}, True, DEFAULT_WORKSPACE),
        (None, {DEFAULT_WORKSPACE}, False, None),
    ],
)
def test_infer_product_workspace(
    newest_workspace: Optional[str],
    selected: Set[str],
    migrate_no_results: bool,
    expected: Optional[str],
) -> None:
    """Ownership follows the newest result; products with no results go to Default."""
    newest = {"p": (newest_workspace, _result("r", "p"))} if newest_workspace else {}

    assert infer_product_workspace("p", newest, selected, migrate_no_results) == expected

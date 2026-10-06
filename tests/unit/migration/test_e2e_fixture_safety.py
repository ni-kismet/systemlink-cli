"""Tests for the owned Test Monitor E2E fixture."""

from typing import Any, Dict, List

import pytest

from slcli.migration.connection import MigrationConnection
from slcli.migration.testmonitor.client import Product, Result, ResultStatus
from tests.e2e import testmonitor_fixture
from tests.e2e.owned_resource_helpers import (
    MIGRATION_DISCOVERY_OWNER,
    OWNER_PROPERTY,
    owner_properties,
)
from tests.e2e.testmonitor_fixture import OwnedTestMonitorResources, plan_cleanup

OWNED = owner_properties(MIGRATION_DISCOVERY_OWNER)


class FakeResponse:
    """A successful response with a JSON body."""

    def __init__(self, body: Dict[str, Any]) -> None:
        """Store the body."""
        self._body = body
        self.content = b"{}"

    def raise_for_status(self) -> None:
        """Succeed."""

    def json(self) -> Dict[str, Any]:
        """Return the body."""
        return self._body


class FakeSession:
    """Record POSTs and answer with configured bodies."""

    def __init__(self, *bodies: Dict[str, Any]) -> None:
        """Store pending bodies."""
        self.bodies = list(bodies)
        self.posted: List[Dict[str, Any]] = []

    def post(self, url: str, json: Dict[str, Any], **kwargs: Any) -> FakeResponse:
        """Record a POST."""
        self.posted.append(json)
        return FakeResponse(self.bodies.pop(0))


def _resources(session: FakeSession) -> OwnedTestMonitorResources:
    connection = MigrationConnection("profile", "https://example", {})
    return OwnedTestMonitorResources(
        connection, {"primary": "primary-id", "other": "other-id"}, session  # type: ignore[arg-type]
    )


def _product(product_id: str, workspace: str = "", owned: bool = True) -> Product:
    return Product(
        id=product_id,
        part_number="part",
        workspace=workspace or None,
        properties=OWNED if owned else {},
    )


def _result(result_id: str, owned: bool = True) -> Result:
    return Result(
        id=result_id,
        status=ResultStatus(status_type="PASSED"),
        updated_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
        properties=OWNED if owned else {},
    )


def test_create_marks_ownership_and_targets_named_workspace() -> None:
    """Created resources carry the owner property and the managed workspace ID."""
    session = FakeSession({"results": [{"id": "result-id"}]})

    ids = _resources(session).create_results([{"programName": "Result"}], "other")

    assert ids == ["result-id"]
    assert session.posted == [
        {
            "results": [
                {
                    "programName": "Result",
                    "workspace": "other-id",
                    "properties": {OWNER_PROPERTY: MIGRATION_DISCOVERY_OWNER},
                }
            ]
        }
    ]


def test_create_rejects_unmanaged_workspace() -> None:
    """Scenarios cannot create resources outside managed workspaces."""
    with pytest.raises(ValueError, match="not managed"):
        _resources(FakeSession()).create_results([], "unknown")


def test_create_retries_only_unknown_workspace_propagation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new workspace may reach Test Monitor after the workspace service."""
    monkeypatch.setattr(testmonitor_fixture.time, "sleep", lambda seconds: None)
    pending = {"results": [], "error": {"innerErrors": [{"name": "Skyline.UnknownWorkspace"}]}}
    session = FakeSession(pending, {"results": [{"id": "result-id"}]})

    assert _resources(session).create_results([{}], "primary") == ["result-id"]
    assert len(session.posted) == 2


def test_create_fails_on_other_errors() -> None:
    """Errors other than workspace propagation are not retried."""
    session = FakeSession({"results": [], "error": {"innerErrors": [{"name": "Other"}]}})

    with pytest.raises(RuntimeError, match="did not create all requested results"):
        _resources(session).create_results([{}], "primary")


def test_cleanup_selects_only_owned_resources() -> None:
    """Owned results and globally owned products are deleted; others are left."""
    plan = plan_cleanup(
        [_product("owned-product"), _product("unrelated-product", owned=False)],
        [_result("owned-result")],
        ["primary-id"],
    )

    assert (plan.product_ids, plan.result_ids, plan.unowned_ids) == (
        ["owned-product"],
        ["owned-result"],
        [],
    )


def test_cleanup_refuses_unowned_workspace_contents() -> None:
    """Unowned results, or products exposing a managed workspace, block cleanup."""
    plan = plan_cleanup(
        [_product("foreign-product", workspace="primary-id", owned=False)],
        [_result("foreign-result", owned=False)],
        ["primary-id"],
    )

    assert plan.unowned_ids == ["foreign-product", "foreign-result"]

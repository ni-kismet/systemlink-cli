"""Owned Test Monitor resources for migration E2E tests."""

import time
from dataclasses import dataclass
from typing import Collection, Dict, List, Mapping, Optional

import requests

from slcli.migration.connection import MigrationConnection
from slcli.migration.testmonitor.client import Product, Result, TestMonitorClient
from tests.e2e.owned_resource_helpers import (
    MIGRATION_DISCOVERY_OWNER,
    owner_properties,
    split_owned_resource_ids,
)

_WORKSPACE_PROPAGATION_TIMEOUT_SECONDS = 30.0
WORKSPACE_PROPAGATION_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True)
class CleanupPlan:
    """Resource IDs classified before any fixture cleanup occurs."""

    product_ids: List[str]
    result_ids: List[str]
    unowned_ids: List[str]


def plan_cleanup(
    products: Collection[Product], results: Collection[Result], workspace_ids: Collection[str]
) -> CleanupPlan:
    """Classify owned resources and refuse unowned contents of managed workspaces.

    ``results`` must be queried from the managed workspaces. SLS products are
    global, so only owned products are deleted and only products that expose a
    managed workspace are checked for foreign ownership.
    """
    owner = MIGRATION_DISCOVERY_OWNER
    products_in_workspaces = [p for p in products if p.workspace in workspace_ids]
    result_ids = split_owned_resource_ids(results, owner)
    return CleanupPlan(
        product_ids=split_owned_resource_ids(products, owner).owned,
        result_ids=result_ids.owned,
        unowned_ids=[
            *split_owned_resource_ids(products_in_workspaces, owner).unowned,
            *result_ids.unowned,
        ],
    )


class OwnedTestMonitorResources:
    """Create and clean up owned Test Monitor resources in dedicated workspaces."""

    def __init__(
        self,
        connection: MigrationConnection,
        workspaces: Mapping[str, str],
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize the manager for dedicated workspaces, by name to ID."""
        self._base_url = f"{connection.base_url}/nitestmonitor/v2"
        self._session = session or connection.create_session()
        self._client = TestMonitorClient(connection, self._session)
        self._workspaces = dict(workspaces)

    def clean(self) -> None:
        """Delete owned resources after refusing unowned workspace contents."""
        products = list(self._client.query_products())
        results = [
            result
            for workspace_id in self._workspaces.values()
            for result in self._client.query_results("workspace == @0", [workspace_id])
        ]
        plan = plan_cleanup(products, results, self._workspaces.values())
        if plan.unowned_ids:
            raise RuntimeError(
                f"Workspaces {sorted(self._workspaces)} contain unowned Test Monitor "
                f"resources: {', '.join(sorted(plan.unowned_ids))}"
            )
        if plan.result_ids:
            self._post("delete-results", {"ids": plan.result_ids, "deleteSteps": True})
        if plan.product_ids:
            self._post("delete-products", {"ids": plan.product_ids})

    def create_products(self, products: List[Dict[str, object]], workspace: str) -> List[str]:
        """Create owned products in a managed workspace and return their IDs."""
        return self._create("products", products, workspace)

    def create_results(self, results: List[Dict[str, object]], workspace: str) -> List[str]:
        """Create owned results in a managed workspace and return their IDs."""
        return self._create("results", results, workspace)

    def _create(
        self, collection: str, resources: List[Dict[str, object]], workspace: str
    ) -> List[str]:
        if workspace not in self._workspaces:
            raise ValueError(f"Workspace '{workspace}' is not managed by this fixture")
        owned = [
            {
                **resource,
                "workspace": self._workspaces[workspace],
                "properties": owner_properties(MIGRATION_DISCOVERY_OWNER),
            }
            for resource in resources
        ]
        # A new workspace can reach Test Monitor after the workspace service.
        deadline = time.monotonic() + _WORKSPACE_PROPAGATION_TIMEOUT_SECONDS
        while True:
            body = self._post(collection, {collection: owned})
            ids = [item.get("id") for item in body.get(collection, [])]
            if len(ids) == len(owned) and all(isinstance(item_id, str) for item_id in ids):
                return [str(item_id) for item_id in ids]
            if not _is_unknown_workspace_failure(body) or time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Test Monitor did not create all requested {collection}: "
                    f"failed={body.get('failed')!r}, error={body.get('error')!r}"
                )
            time.sleep(WORKSPACE_PROPAGATION_INTERVAL_SECONDS)

    def _post(
        self, endpoint: str, payload: Dict[str, object]
    ) -> Dict[str, List[Dict[str, object]]]:
        response = self._session.post(f"{self._base_url}/{endpoint}", json=payload, timeout=30)
        response.raise_for_status()
        return response.json() if response.content else {}


def _is_unknown_workspace_failure(body: Mapping[str, object]) -> bool:
    error = body.get("error")
    inner_errors = error.get("innerErrors", []) if isinstance(error, dict) else []
    return any(inner.get("name") == "Skyline.UnknownWorkspace" for inner in inner_errors)

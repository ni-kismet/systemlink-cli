from typing import Any, Dict
from unittest.mock import patch, MagicMock

from slcli.example_provisioner import (
    ExampleProvisioner,
    ProvisioningAction,
)


def make_min_config() -> Dict[str, Any]:
    return {
        "format_version": "1.0",
        "name": "unit-min-config",
        "title": "Unit Min Config",
        "resources": [
            {
                "type": "location",
                "name": "Demo HQ",
                "id_reference": "loc_hq",
                "properties": {"name": "Demo HQ"},
            },
            {
                "type": "system",
                "name": "Test Stand 1",
                "id_reference": "sys_ts1",
                "properties": {"name": "Test Stand 1", "location_id": "${loc_hq}"},
            },
            {
                "type": "asset",
                "name": "Asset 1",
                "id_reference": "asset_1",
                "properties": {"name": "Asset 1", "system_id": "${sys_ts1}"},
            },
        ],
    }


def test_dry_run_skips_creation() -> None:
    config = make_min_config()
    prov = ExampleProvisioner(dry_run=True)
    results, err = prov.provision(config)
    assert err is None
    assert len(results) == 3
    assert all(r.action == ProvisioningAction.SKIPPED for r in results)
    # No server IDs on dry-run
    assert all(r.server_id is None for r in results)


@patch("slcli.example_provisioner.make_api_request")
def test_provision_creates_in_order_and_assigns_ids(mock_api: Any) -> None:
    # Mock API responses with IDs
    def mock_post(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        # Return appropriate ID based on URL and method
        url = args[1] if len(args) > 1 else ""
        method = str(args[0])
        if "locations" in url and "GET" in method:
            # GET request to check if location exists - return empty list
            resp.json.return_value = {"locations": []}
        elif "query-systems" in url and method == "POST":
            # Systems query returns an array of systems (empty when not found)
            resp.json.return_value = []
        elif "query-assets" in url and method == "POST":
            # Asset query returns { assets: [], totalCount }
            resp.json.return_value = {"assets": [], "totalCount": 0}
        elif "products" in url and "GET" in method:
            # Products API returns { products: [] }
            resp.json.return_value = {"products": []}
        elif "locations" in url and method == "POST":
            # Location create returns { id }
            resp.json.return_value = {"id": "loc-12345"}
        elif ("systems" in url or "virtual" in url) and method == "POST":
            # Virtual system create returns { minionId }
            resp.json.return_value = {"minionId": "sys-67890"}
        elif "assets" in url and method == "POST":
            # Asset create returns { assets: [{ id }] }
            resp.json.return_value = {"assets": [{"id": "asset-11111"}]}
        elif "products" in url and method == "POST":
            # Product create returns { products: [{ id }] }
            resp.json.return_value = {"products": [{"id": "prod-22222"}]}
        else:
            resp.json.return_value = {"id": "unknown-00000"}
        return resp

    mock_api.side_effect = mock_post

    config = make_min_config()
    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    results, err = prov.provision(config)
    assert err is None
    assert len(results) == 3
    # Check actions - all should be CREATED since no duplicates exist
    assert [r.action for r in results] == [
        ProvisioningAction.CREATED,
        ProvisioningAction.CREATED,
        ProvisioningAction.CREATED,
    ]
    # Server IDs present from mocked API
    assert results[0].server_id == "loc-12345"
    assert results[1].server_id == "sys-67890"
    assert results[2].server_id == "asset-11111"
    # Verify API was called 6 times: 3 checks (location/system/asset) + 3 creates
    assert mock_api.call_count == 6


def test_delete_dry_run_skips_deletion() -> None:
    config = make_min_config()
    prov = ExampleProvisioner(dry_run=True)
    results, err = prov.delete(config)
    assert err is None
    # Should have one result per resource
    assert len(results) == 3
    # All skipped in dry-run
    assert all(r.action == ProvisioningAction.SKIPPED for r in results)
    # No server IDs in dry-run
    assert all(r.server_id is None for r in results)


@patch("slcli.example_provisioner.make_api_request")
def test_delete_happens_in_reverse_order_and_reports_ids(mock_api: Any) -> None:
    # Mock API to return empty locations list (resource not found)
    def mock_delete(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        # For location existence check, return empty list
        url = args[1] if len(args) > 1 else ""
        if "locations" in url and "GET" in str(args[0]):
            resp.json.return_value = {"locations": []}
        else:
            # All other API calls succeed but return nothing (resource not found)
            resp.json.return_value = {}
        resp.raise_for_status.return_value = None
        return resp

    mock_api.side_effect = mock_delete

    config = make_min_config()
    prov = ExampleProvisioner(dry_run=False)
    results, err = prov.delete(config)
    assert err is None
    assert len(results) == 3
    # Deletion should be in reverse order of resources definition
    # Original order: location, system, asset -> delete order: asset, system, location
    assert [r.resource_type for r in results] == ["asset", "system", "location"]
    # When resources don't exist (not found), they are SKIPPED, not DELETED
    assert all(r.action == ProvisioningAction.SKIPPED for r in results)
    # No server IDs returned when resources not found
    assert all(r.server_id is None for r in results)

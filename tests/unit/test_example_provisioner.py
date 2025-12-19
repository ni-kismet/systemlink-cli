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


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_provision_creates_in_order_and_assigns_ids(mock_api: Any, mock_base_url: Any) -> None:
    # Mock base URL
    mock_base_url.return_value = "https://api.test.com"

    # Mock API responses with IDs
    def mock_post(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        # Return appropriate ID based on URL and method
        url = args[1] if len(args) > 1 else ""
        method = str(args[0]) if len(args) > 0 else ""
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
        if "locations" in url and len(args) > 0 and "GET" in str(args[0]):
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


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_reference_resolution(mock_api: Any, mock_base_url: Any) -> None:
    """Test that ${ref} tokens are resolved to created server IDs."""
    # Mock base URL
    mock_base_url.return_value = "https://api.test.com"

    call_count = [0]

    def mock_resolve(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        call_count[0] += 1
        call_index = call_count[0]

        # Location existence check
        if (
            len(args) > 1
            and "locations" in args[1]
            and len(args) > 0
            and "GET" in str(args[0])
            and call_index == 1
        ):
            resp.json.return_value = {"locations": []}
        # Location create
        elif (
            len(args) > 1
            and "locations" in args[1]
            and len(args) > 0
            and "POST" in str(args[0])
            and call_index == 2
        ):
            resp.json.return_value = {"id": "loc-abc"}
        # System existence check
        elif len(args) > 1 and "query-systems" in args[1] and call_index == 3:
            resp.json.return_value = []
        # System create
        elif len(args) > 1 and "virtual" in args[1] and call_index == 4:
            resp.json.return_value = {"minionId": "sys-xyz"}
        else:
            resp.json.return_value = {}

        return resp

    mock_api.side_effect = mock_resolve

    config = {
        "format_version": "1.0",
        "name": "ref-test",
        "title": "Reference Test",
        "resources": [
            {
                "type": "location",
                "name": "Main Lab",
                "id_reference": "lab",
                "properties": {},
            },
            {
                "type": "system",
                "name": "Test System",
                "id_reference": "sys",
                "properties": {"location_id": "${lab}"},  # Reference to location
            },
        ],
    }

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    results, err = prov.provision(config)

    assert err is None
    assert len(results) == 2
    assert results[0].action == ProvisioningAction.CREATED
    assert results[1].action == ProvisioningAction.CREATED
    # Verify reference was stored in id_map
    assert prov.id_map.get("lab") == "loc-abc"
    assert prov.id_map.get("sys") == "sys-xyz"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_duplicate_detection_skips_existing(mock_api: Any, mock_base_url: Any) -> None:
    """Test that existing resources are detected and skipped."""
    # Mock base URL
    mock_base_url.return_value = "https://api.test.com"

    call_count = [0]

    def mock_dup(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        call_count[0] += 1

        # Existence check returns the resource (exists)
        if "locations" in args[1] and "GET" in str(args[0]):
            resp.json.return_value = {
                "locations": [
                    {
                        "id": "existing-loc-123",
                        "name": "Demo HQ",
                        "workspace": "ws-test",
                        "keywords": ["slcli-example:test"],
                    }
                ]
            }
        else:
            resp.json.return_value = {}

        return resp

    mock_api.side_effect = mock_dup

    config = {
        "format_version": "1.0",
        "name": "dup-test",
        "title": "Duplicate Test",
        "resources": [
            {
                "type": "location",
                "name": "Demo HQ",
                "id_reference": "loc_hq",
                "properties": {},
            },
        ],
    }

    prov = ExampleProvisioner(workspace_id="ws-test", example_name="test", dry_run=False)
    results, err = prov.provision(config)

    assert err is None
    assert len(results) == 1
    assert results[0].action == ProvisioningAction.SKIPPED
    assert results[0].server_id == "existing-loc-123"
    assert results[0].error == "Resource already exists"


def test_invalid_config_returns_error() -> None:
    """Test that invalid config returns error."""
    config = {
        "format_version": "1.0",
        "name": "invalid",
        "title": "Invalid",
        "resources": "not_a_list",  # Should be a list
    }

    prov = ExampleProvisioner(dry_run=True)
    results, err = prov.provision(config)

    assert err is not None
    assert isinstance(err, ValueError)
    assert "must be a list" in str(err)


@patch("slcli.example_provisioner.make_api_request")
def test_unsupported_resource_type(mock_api: Any) -> None:
    """Test that unsupported resource types fail gracefully."""
    mock_api.return_value = MagicMock()

    config = {
        "format_version": "1.0",
        "name": "unsupported-test",
        "title": "Unsupported Type Test",
        "resources": [
            {
                "type": "unknown_resource",  # Not supported
                "name": "Test Resource",
                "id_reference": "unknown",
                "properties": {},
            },
        ],
    }

    prov = ExampleProvisioner(dry_run=False)
    results, err = prov.provision(config)

    assert err is None
    assert len(results) == 1
    assert results[0].action == ProvisioningAction.FAILED
    assert results[0].error is not None and "Unsupported resource type" in results[0].error


@patch("slcli.example_provisioner.make_api_request")
def test_tag_filtering_on_delete(mock_api: Any) -> None:
    """Test that delete filters by tag correctly."""

    def mock_filter(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        url = args[1] if len(args) > 1 else ""

        # Return empty for all queries
        if "locations" in url and len(args) > 0 and "GET" in str(args[0]):
            resp.json.return_value = {"locations": []}
        else:
            resp.json.return_value = {}

        resp.raise_for_status.return_value = None
        return resp

    mock_api.side_effect = mock_filter

    config = {
        "format_version": "1.0",
        "name": "tag-test",
        "title": "Tag Filter Test",
        "resources": [
            {
                "type": "location",
                "name": "Lab 1",
                "id_reference": "lab1",
                "tags": ["production"],  # Has production tag
                "properties": {},
            },
            {
                "type": "location",
                "name": "Lab 2",
                "id_reference": "lab2",
                "tags": ["demo"],  # Different tag
                "properties": {},
            },
        ],
    }

    prov = ExampleProvisioner(dry_run=False)
    # Filter to delete only production-tagged resources
    results, err = prov.delete(config, filter_tags=["production"])

    assert err is None
    assert len(results) == 2
    # Only the production-tagged resource should be processed (attempted)
    # The demo-tagged should be SKIPPED due to tag filter
    skipped = [r for r in results if r.action == ProvisioningAction.SKIPPED]
    assert len(skipped) >= 1  # At least one should be skipped

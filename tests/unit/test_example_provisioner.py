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


@patch("slcli.example_provisioner.requests")
@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.get_headers")
@patch("builtins.open", create=True)
@patch("pathlib.Path")
def test_notebook_properties_preserved_with_interface(
    mock_path: Any, mock_open: Any, mock_headers: Any, mock_base_url: Any, mock_requests: Any
) -> None:
    """Test that slcli-example property is preserved when adding interface."""
    # Setup mocks
    mock_base_url.return_value = "https://api.test.com"
    mock_headers.return_value = {"Authorization": "Bearer test"}

    # Mock file system
    mock_file_obj = MagicMock()
    mock_file_obj.read.return_value = b'{"cells":[]}'
    mock_open.return_value.__enter__.return_value = mock_file_obj

    mock_notebook_path = MagicMock()
    mock_notebook_path.exists.return_value = True
    mock_path.return_value.__truediv__.return_value.__truediv__.return_value = mock_notebook_path

    # Track PUT request metadata
    put_metadata = None

    def mock_post(url: str, **kwargs: Any) -> Any:
        resp = MagicMock()
        resp.json.return_value = {"id": "nb-12345"}
        resp.raise_for_status.return_value = None
        return resp

    def mock_put(url: str, **kwargs: Any) -> Any:
        nonlocal put_metadata
        # Extract metadata from the files parameter
        if "files" in kwargs and "metadata" in kwargs["files"]:
            import json

            metadata_bytes = kwargs["files"]["metadata"][1]
            put_metadata = json.loads(metadata_bytes.decode("utf-8"))
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        return resp

    mock_requests.post.side_effect = mock_post
    mock_requests.put.side_effect = mock_put

    # Create provisioner and test notebook creation
    prov = ExampleProvisioner(example_name="test-example", workspace_id="ws-test", dry_run=False)
    notebook_id = prov._create_notebook(
        {
            "name": "Test Notebook",
            "file_path": "test.ipynb",
            "notebook_interface": "File Analysis",
        }
    )

    # Verify notebook was created
    assert notebook_id == "nb-12345"
    assert mock_requests.post.called
    assert mock_requests.put.called

    # Verify PUT request preserved slcli-example property and added interface
    assert put_metadata is not None
    assert "properties" in put_metadata
    assert put_metadata["properties"].get("slcli-example") == "test-example"
    # Verify interface property was actually added
    assert put_metadata["properties"].get("interface") == "File Analysis"


# ---------------------------------------------------------------------------
# _create_test_steps unit tests
# ---------------------------------------------------------------------------


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_builds_correct_payload(mock_api: Any, mock_base_url: Any) -> None:
    """POST to /nitestmonitor/v2/steps with correct resultId, stepType, status, and parameters."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [
        {
            "name": "Voltage Check",
            "step_type": "NumericLimitTest",
            "status": "passed",
            "total_time_in_seconds": 1.5,
            "data": {
                "text": "Voltage within range",
                "parameters": [
                    {
                        "name": "Voltage",
                        "measurement": "3.7",
                        "lowLimit": "3.0",
                        "highLimit": "4.2",
                        "units": "V",
                        "status": "Passed",
                        "comparisonType": "GELE",
                    }
                ],
            },
        }
    ]
    prov._create_test_steps("result-abc", steps, [])

    mock_api.assert_called_once()
    call_args = mock_api.call_args
    assert call_args[0][0] == "POST"
    assert call_args[0][1] == "https://api.test.com/nitestmonitor/v2/steps"
    payload = call_args[0][2]

    assert payload["updateResultTotalTime"] is True
    assert len(payload["steps"]) == 1
    step = payload["steps"][0]

    assert step["resultId"] == "result-abc"
    assert step["name"] == "Voltage Check"
    assert step["stepType"] == "NumericLimitTest"
    assert step["status"] == {"statusType": "PASSED", "statusName": "Passed"}
    assert step["totalTimeInSeconds"] == 1.5

    data = step["data"]
    assert data["text"] == "Voltage within range"
    assert len(data["parameters"]) == 1
    param = data["parameters"][0]
    assert param["name"] == "Voltage"
    assert param["measurement"] == "3.7"
    assert param["lowLimit"] == "3.0"
    assert param["highLimit"] == "4.2"
    assert param["units"] == "V"
    assert param["comparisonType"] == "GELE"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_filters_none_parameters(mock_api: Any, mock_base_url: Any) -> None:
    """None values in parameter dicts are excluded from the serialised output."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [
        {
            "name": "Resistance Check",
            "data": {
                "parameters": [
                    {
                        "name": "Resistance",
                        "measurement": "5.2",
                        "lowLimit": None,  # should be excluded
                        "highLimit": "10.0",
                        "units": "Ohm",
                        "status": None,  # should be excluded
                    }
                ]
            },
        }
    ]
    prov._create_test_steps("result-xyz", steps, [])

    payload = mock_api.call_args[0][2]
    param = payload["steps"][0]["data"]["parameters"][0]
    assert "lowLimit" not in param
    assert "status" not in param
    assert param["name"] == "Resistance"
    assert param["highLimit"] == "10.0"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
@patch("slcli.example_provisioner.click")
def test_create_test_steps_invalid_status_warns(
    mock_click: Any, mock_api: Any, mock_base_url: Any
) -> None:
    """Unrecognised status emits a warning and falls back to PASSED."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [{"name": "Mystery Step", "status": "unknown_status"}]
    prov._create_test_steps("result-123", steps, [])

    # Warning must have been emitted to stderr
    mock_click.echo.assert_called_once()
    warning_call = mock_click.echo.call_args
    assert "unrecognized" in warning_call[0][0].lower()
    assert warning_call[1].get("err") is True

    # Step is still POSTed and defaults to PASSED
    payload = mock_api.call_args[0][2]
    assert payload["steps"][0]["status"]["statusType"] == "PASSED"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
@patch("slcli.example_provisioner.click")
def test_create_test_steps_exception_logs_warning(
    mock_click: Any, mock_api: Any, mock_base_url: Any
) -> None:
    """When make_api_request raises, a warning is logged and no exception propagates."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.side_effect = RuntimeError("network failure")

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [{"name": "Any Step"}]
    # Should NOT raise
    prov._create_test_steps("result-fail", steps, [])

    mock_click.echo.assert_called_once()
    warning_call = mock_click.echo.call_args
    assert "Warning" in warning_call[0][0]
    assert "result-fail" in warning_call[0][0]
    assert warning_call[1].get("err") is True


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_keyword_inheritance_and_dedup(mock_api: Any, mock_base_url: Any) -> None:
    """Step keywords inherit from result keywords and are deduplicated."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    result_keywords = ["slcli-provisioner", "slcli-example:my-example"]
    steps = [
        {
            "name": "Step With Extra Keywords",
            "keywords": ["slcli-provisioner", "extra-tag"],  # "slcli-provisioner" is a dupe
        }
    ]
    prov._create_test_steps("result-kw", steps, result_keywords)

    payload = mock_api.call_args[0][2]
    kw = payload["steps"][0]["keywords"]
    # No duplicates
    assert len(kw) == len(set(kw))
    # All expected keywords present
    assert "slcli-provisioner" in kw
    assert "slcli-example:my-example" in kw
    assert "extra-tag" in kw


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_recursive_children(mock_api: Any, mock_base_url: Any) -> None:
    """Nested children are built recursively and share the same resultId."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [
        {
            "name": "Parent Step",
            "children": [
                {"name": "Child Step A", "status": "passed"},
                {"name": "Child Step B", "status": "failed"},
            ],
        }
    ]
    prov._create_test_steps("result-child", steps, [])

    payload = mock_api.call_args[0][2]
    parent = payload["steps"][0]
    assert parent["name"] == "Parent Step"
    assert parent["resultId"] == "result-child"
    assert len(parent["children"]) == 2

    child_a = parent["children"][0]
    child_b = parent["children"][1]
    assert child_a["name"] == "Child Step A"
    assert child_a["resultId"] == "result-child"
    assert child_a["status"]["statusType"] == "PASSED"
    assert child_b["name"] == "Child Step B"
    assert child_b["status"]["statusType"] == "FAILED"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_not_called_when_no_steps(mock_api: Any, mock_base_url: Any) -> None:
    """_create_test_result without steps in props does not POST to the steps endpoint."""
    mock_base_url.return_value = "https://api.test.com"

    steps_url_called = []

    def mock_post(*args: Any, **kwargs: Any) -> Any:
        resp = MagicMock()
        url = args[1] if len(args) > 1 else ""
        if len(args) > 0 and "steps" in url and "POST" in str(args[0]):
            steps_url_called.append(url)
        resp.json.return_value = {"id": "result-789"}
        resp.raise_for_status.return_value = None
        return resp

    mock_api.side_effect = mock_post

    prov = ExampleProvisioner(workspace_id="ws-test", example_name="test", dry_run=False)
    # Call _create_test_result with no 'steps' key in properties
    props = {
        "program_name": "No Steps Test",
        "serial_number": "SN-001",
        "status": "passed",
    }
    prov._create_test_result(props)

    # Steps endpoint must NOT have been hit
    assert steps_url_called == []


# ---------------------------------------------------------------------------
# _build_asset_obj / _create_dut unit tests
# ---------------------------------------------------------------------------


def test_build_asset_obj_description_and_defaults() -> None:
    """_build_asset_obj copies description and applies sensible defaults."""
    prov = ExampleProvisioner(workspace_id="ws-test", example_name="ex1", dry_run=False)
    obj = prov._build_asset_obj(
        {"name": "My Asset", "description": "A test asset"},
        default_name="Fallback",
    )
    assert obj["name"] == "My Asset"
    assert obj["description"] == "A test asset"
    assert obj["busType"] == "ACCESSORY"
    assert obj["modelName"] == "Unknown"
    assert obj["vendorName"] == "Unknown"
    # Location default when no system_id
    assert obj["location"] == {"state": {"assetPresence": "UNKNOWN"}}
    # Keywords include slcli-provisioner and example tag
    assert "slcli-provisioner" in obj["keywords"]
    assert "slcli-example:ex1" in obj["keywords"]


def test_build_asset_obj_system_id_maps_to_location() -> None:
    """system_id in props maps to location.minionId."""
    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    obj = prov._build_asset_obj({"name": "Asset", "system_id": "sys-abc"})
    assert obj["location"]["minionId"] == "sys-abc"
    assert obj["location"]["state"]["assetPresence"] == "UNKNOWN"


def test_build_asset_obj_dut_type_override() -> None:
    """asset_type parameter forces assetType and skips field_map assetType entry."""
    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    obj = prov._build_asset_obj(
        {"name": "DUT", "assetType": "SHOULD_BE_IGNORED"},
        asset_type="DEVICE_UNDER_TEST",
    )
    assert obj["assetType"] == "DEVICE_UNDER_TEST"


def test_build_asset_obj_keyword_dedup() -> None:
    """Keywords from props are merged with provisioner tags and deduplicated."""
    prov = ExampleProvisioner(workspace_id="ws-test", example_name="demo", dry_run=False)
    obj = prov._build_asset_obj(
        {
            "name": "A",
            "keywords": ["slcli-provisioner", "custom-tag"],
            "tags": ["custom-tag", "another"],
        },
    )
    kw = obj["keywords"]
    assert len(kw) == len(set(kw)), "Keywords must not contain duplicates"
    assert "slcli-provisioner" in kw
    assert "custom-tag" in kw
    assert "another" in kw
    assert "slcli-example:demo" in kw


def test_build_asset_obj_snake_case_fields() -> None:
    """Snake_case config props are mapped to camelCase API fields."""
    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    obj = prov._build_asset_obj(
        {
            "name": "Acme Widget",
            "serial_number": "SN-12345",
            "part_number": "PN-99",
            "model_name": "Widget Pro",
            "vendor_name": "Acme Corp",
            "bus_type": "ETHERNET",
        },
    )
    assert obj["serialNumber"] == "SN-12345"
    assert obj["partNumber"] == "PN-99"
    assert obj["modelName"] == "Widget Pro"
    assert obj["vendorName"] == "Acme Corp"
    # ETHERNET is normalised to TCP_IP
    assert obj["busType"] == "TCP_IP"


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_dut_delegates_to_shared_helpers(mock_api: Any, mock_base_url: Any) -> None:
    """_create_dut builds via _build_asset_obj and POSTs via _post_asset."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock(json=MagicMock(return_value={"assets": [{"id": "dut-001"}]}))

    prov = ExampleProvisioner(workspace_id="ws-test", example_name="train", dry_run=False)
    result = prov._create_dut(
        {
            "name": "Battery DUT",
            "serial_number": "BAT-100",
            "description": "Test battery pack",
            "system_id": "sys-xyz",
            "part_number": "PN-BAT",
        }
    )

    assert result == "dut-001"
    mock_api.assert_called_once()
    call_args = mock_api.call_args
    assert call_args[0][0] == "POST"
    assert "/niapm/v1/assets" in call_args[0][1]
    payload = call_args[0][2]
    asset = payload["assets"][0]
    assert asset["assetType"] == "DEVICE_UNDER_TEST"
    assert asset["serialNumber"] == "BAT-100"
    assert asset["description"] == "Test battery pack"
    assert asset["partNumber"] == "PN-BAT"
    assert asset["location"]["minionId"] == "sys-xyz"
    assert "slcli-provisioner" in asset["keywords"]
    assert "slcli-example:train" in asset["keywords"]


# ---------------------------------------------------------------------------
# _create_test_steps — remaining optional-branch coverage
# ---------------------------------------------------------------------------


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_optional_fields(mock_api: Any, mock_base_url: Any) -> None:
    """Covers dataModel, stepId, parentId, startedAt, inputs, outputs, properties."""
    mock_base_url.return_value = "https://api.test.com"
    mock_api.return_value = MagicMock()

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    steps = [
        {
            "name": "Full Step",
            "step_type": "PassFailTest",
            "data_model": "TestStand",
            "step_id": "step-42",
            "parent_id": "step-00",
            "started_at": "2026-02-20T10:00:00Z",
            "total_time_in_seconds": 2.5,
            "status": "failed",
            "inputs": [{"name": "voltage", "value": "3.7"}],
            "outputs": [{"name": "result", "value": "FAIL"}],
            "properties": {"env": "lab", "temp": "25C"},
        }
    ]
    prov._create_test_steps("result-opt", steps, [])

    payload = mock_api.call_args[0][2]
    step = payload["steps"][0]
    assert step["dataModel"] == "TestStand"
    assert step["stepId"] == "step-42"
    assert step["parentId"] == "step-00"
    assert step["startedAt"] == "2026-02-20T10:00:00Z"
    assert step["totalTimeInSeconds"] == 2.5
    assert step["status"]["statusType"] == "FAILED"
    assert step["inputs"] == [{"name": "voltage", "value": "3.7"}]
    assert step["outputs"] == [{"name": "result", "value": "FAIL"}]
    assert step["properties"] == {"env": "lab", "temp": "25C"}


@patch("slcli.example_provisioner.get_base_url")
@patch("slcli.example_provisioner.make_api_request")
def test_create_test_steps_empty_list_skips_post(mock_api: Any, mock_base_url: Any) -> None:
    """When steps list contains no valid dicts, no POST is issued."""
    mock_base_url.return_value = "https://api.test.com"

    prov = ExampleProvisioner(workspace_id="ws-test", dry_run=False)
    prov._create_test_steps("result-empty", ["not-a-dict", 42], [])  # type: ignore[list-item]

    mock_api.assert_not_called()

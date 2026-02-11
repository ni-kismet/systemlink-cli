"""E2E tests for asset commands against dev tier."""

import uuid
from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetListE2E:
    """End-to-end tests for 'asset list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing assets in JSON format."""
        result = cli_runner(["asset", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing assets in table format."""
        result = cli_runner(
            ["asset", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Should show table headers or empty message
        assert "Model" in result.stdout or "No assets found" in result.stdout

    def test_list_with_take(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --take pagination limit (table output)."""
        result = cli_runner(
            ["asset", "list", "--format", "table", "--take", "3"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Table should display results with take=3 per page
        assert "Model" in result.stdout or "No assets found" in result.stdout

    def test_list_with_model_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing assets filtered by model name."""
        # First get a model name to filter by
        result = cli_runner(["asset", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        if not assets:
            pytest.skip("No assets available for testing")

        model_name = assets[0].get("modelName", "")
        if not model_name:
            pytest.skip("First asset has no model name")

        result = cli_runner(
            ["asset", "list", "--format", "json", "--model", model_name, "--take", "10"]
        )
        cli_helper.assert_success(result)

        filtered = cli_helper.get_json_output(result)
        assert isinstance(filtered, list)
        for asset in filtered:
            assert model_name.lower() in asset.get("modelName", "").lower()

    def test_list_with_bus_type_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing assets filtered by bus type."""
        result = cli_runner(
            ["asset", "list", "--format", "json", "--bus-type", "PCI_PXI", "--take", "5"]
        )
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)

    def test_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test listing assets filtered by workspace."""
        result = cli_runner(
            [
                "asset",
                "list",
                "--format",
                "json",
                "--workspace",
                configured_workspace,
                "--take",
                "10",
            ]
        )
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)

    def test_list_connected_only(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing only connected assets."""
        result = cli_runner(["asset", "list", "--format", "json", "--connected", "--take", "5"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)

    def test_list_empty_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with a filter that matches nothing."""
        result = cli_runner(
            [
                "asset",
                "list",
                "--format",
                "json",
                "--serial-number",
                "NONEXISTENT-SERIAL-E2E-99999",
            ]
        )
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)
        assert len(assets) == 0

    def test_list_with_order_by(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with order-by option."""
        result = cli_runner(
            [
                "asset",
                "list",
                "--format",
                "json",
                "--order-by",
                "LAST_UPDATED_TIMESTAMP",
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        assert isinstance(assets, list)

    def test_list_summary(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --summary flag."""
        result = cli_runner(["asset", "list", "--format", "json", "--summary"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetGetE2E:
    """End-to-end tests for 'asset get' command."""

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a specific asset by ID."""
        result = cli_runner(["asset", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        if not assets:
            pytest.skip("No assets available for testing")

        asset_id = assets[0].get("id", "")
        assert asset_id

        result = cli_runner(["asset", "get", asset_id, "--format", "json"])
        cli_helper.assert_success(result)

        asset = cli_helper.get_json_output(result)
        assert isinstance(asset, dict)
        assert asset.get("id") == asset_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting an asset in table format."""
        result = cli_runner(["asset", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        if not assets:
            pytest.skip("No assets available for testing")

        asset_id = assets[0].get("id", "")
        result = cli_runner(["asset", "get", asset_id, "--format", "table"])
        cli_helper.assert_success(result)

        assert "Asset:" in result.stdout

    def test_get_not_found(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a nonexistent asset."""
        result = cli_runner(
            ["asset", "get", "nonexistent-asset-id-e2e-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_get_with_calibration(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting an asset with calibration history."""
        result = cli_runner(["asset", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        if not assets:
            pytest.skip("No assets available for testing")

        asset_id = assets[0].get("id", "")
        result = cli_runner(["asset", "get", asset_id, "--format", "json", "--include-calibration"])
        cli_helper.assert_success(result)

        asset = cli_helper.get_json_output(result)
        assert isinstance(asset, dict)


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetSummaryE2E:
    """End-to-end tests for 'asset summary' command."""

    def test_summary_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test asset summary in JSON format."""
        result = cli_runner(["asset", "summary", "--format", "json"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)

    def test_summary_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test asset summary in table format."""
        result = cli_runner(["asset", "summary", "--format", "table"])
        cli_helper.assert_success(result)

        assert "Asset Summary" in result.stdout or "Total" in result.stdout


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetLifecycleE2E:
    """End-to-end tests for asset create/update/delete lifecycle."""

    def test_create_update_delete(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test full asset lifecycle: create, update, delete."""
        unique_id = uuid.uuid4().hex[:8]
        model = f"E2E-Test-Model-{unique_id}"
        serial = f"E2E-SN-{unique_id}"

        asset_id = None
        try:
            # Create asset
            result = cli_runner(
                [
                    "asset",
                    "create",
                    "--model-name",
                    model,
                    "--serial-number",
                    serial,
                    "--vendor-name",
                    "E2E Test Vendor",
                    "--asset-type",
                    "GENERIC",
                    "--format",
                    "json",
                ],
                check=False,
            )
            if "readonly" in result.stderr.lower():
                pytest.skip("Profile is in readonly mode")
            cli_helper.assert_success(result)

            create_data = cli_helper.get_json_output(result)
            # The create API returns {"assets": [...], "failed": [...]}
            # Extract the first created asset from the response.
            if isinstance(create_data, dict) and "assets" in create_data:
                assets_list = create_data["assets"]
                assert assets_list, "Create response assets list is empty"
                asset_obj = assets_list[0]
            elif isinstance(create_data, list):
                assert create_data, "Create response list is empty"
                asset_obj = create_data[0]
            elif isinstance(create_data, dict):
                asset_obj = create_data
            else:
                raise AssertionError(f"Unexpected create response type: {type(create_data)}")

            asset_id = asset_obj.get("id", "")
            assert asset_id

            # Verify via get
            result = cli_runner(["asset", "get", asset_id, "--format", "json"])
            cli_helper.assert_success(result)

            asset = cli_helper.get_json_output(result)
            assert asset.get("modelName") == model
            assert asset.get("serialNumber") == serial

            # Update asset
            new_name = f"E2E-Updated-{unique_id}"
            result = cli_runner(
                [
                    "asset",
                    "update",
                    asset_id,
                    "--name",
                    new_name,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)

            # Verify update
            result = cli_runner(["asset", "get", asset_id, "--format", "json"])
            cli_helper.assert_success(result)

            updated = cli_helper.get_json_output(result)
            assert updated.get("name") == new_name

        finally:
            # Cleanup: delete asset
            if asset_id:
                cli_runner(
                    ["asset", "delete", asset_id, "--force"],
                    check=False,
                )

    def test_create_with_properties(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test creating an asset with custom properties."""
        unique_id = uuid.uuid4().hex[:8]
        model = f"E2E-Props-{unique_id}"
        serial = f"E2E-SN-P-{unique_id}"

        asset_id = None
        try:
            result = cli_runner(
                [
                    "asset",
                    "create",
                    "--model-name",
                    model,
                    "--serial-number",
                    serial,
                    "--vendor-name",
                    "E2E Test Vendor",
                    "--asset-type",
                    "DEVICE_UNDER_TEST",
                    "--property",
                    f"TestKey=TestValue-{unique_id}",
                    "--format",
                    "json",
                ],
                check=False,
            )
            if "readonly" in result.stderr.lower():
                pytest.skip("Profile is in readonly mode")
            cli_helper.assert_success(result)

            create_data = cli_helper.get_json_output(result)
            # The create API returns {"assets": [...], "failed": [...]}
            if isinstance(create_data, dict) and "assets" in create_data:
                assets_list = create_data["assets"]
                assert assets_list, "Create response assets list is empty"
                asset_obj = assets_list[0]
            elif isinstance(create_data, list):
                assert create_data, "Create response list is empty"
                asset_obj = create_data[0]
            elif isinstance(create_data, dict):
                asset_obj = create_data
            else:
                raise AssertionError(f"Unexpected create response type: {type(create_data)}")

            asset_id = asset_obj.get("id", "")
            assert asset_id

        finally:
            if asset_id:
                cli_runner(["asset", "delete", asset_id, "--force"], check=False)


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetCalibrationE2E:
    """End-to-end tests for 'asset calibration' command."""

    def test_calibration_list(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing calibration history for an asset."""
        # First find an asset
        result = cli_runner(["asset", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        assets = cli_helper.get_json_output(result)
        if not assets:
            pytest.skip("No assets available for testing")

        asset_id = assets[0].get("id", "")
        result = cli_runner(["asset", "calibration", asset_id, "--format", "json"])
        cli_helper.assert_success(result)

        cal_data = cli_helper.get_json_output(result)
        assert isinstance(cal_data, list)


@pytest.mark.e2e
@pytest.mark.asset
class TestAssetHelpE2E:
    """End-to-end tests for asset command help text."""

    def test_asset_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'asset --help' displays correctly."""
        result = cli_runner(["asset", "--help"])
        cli_helper.assert_success(result)

        assert "list" in result.stdout
        assert "get" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout
        assert "summary" in result.stdout

    def test_asset_list_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'asset list --help' displays all options."""
        result = cli_runner(["asset", "list", "--help"])
        cli_helper.assert_success(result)

        assert "--format" in result.stdout
        assert "--take" in result.stdout
        assert "--model" in result.stdout
        assert "--bus-type" in result.stdout
        assert "--workspace" in result.stdout

    def test_asset_create_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'asset create --help' displays required options."""
        result = cli_runner(["asset", "create", "--help"])
        cli_helper.assert_success(result)

        assert "--model-name" in result.stdout
        assert "--serial-number" in result.stdout

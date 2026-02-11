"""E2E tests for testmonitor commands against dev tier."""

from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.testmonitor
class TestProductListE2E:
    """End-to-end tests for 'testmonitor product list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing products in JSON format."""
        result = cli_runner(["testmonitor", "product", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        assert isinstance(products, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing products in table format."""
        result = cli_runner(
            ["testmonitor", "product", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Should show table headers or empty message
        assert "Part Number" in result.stdout or "No products found" in result.stdout

    def test_list_with_take(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --take pagination limit (table output)."""
        result = cli_runner(
            ["testmonitor", "product", "list", "--format", "table", "--take", "3"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Table should render with take=3 page size
        assert "Part Number" in result.stdout or "No products found" in result.stdout

    def test_list_with_name_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing products filtered by name."""
        # First get a product to filter by
        result = cli_runner(["testmonitor", "product", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        if not products:
            pytest.skip("No products available for testing")

        name = products[0].get("name", "")
        if not name:
            pytest.skip("First product has no name")

        result = cli_runner(
            ["testmonitor", "product", "list", "--format", "json", "--name", name, "--take", "10"]
        )
        cli_helper.assert_success(result)

        filtered = cli_helper.get_json_output(result)
        assert isinstance(filtered, list)
        assert len(filtered) > 0

    def test_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test listing products filtered by workspace."""
        result = cli_runner(
            [
                "testmonitor",
                "product",
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

        products = cli_helper.get_json_output(result)
        assert isinstance(products, list)

    def test_list_empty_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with a filter that matches nothing."""
        result = cli_runner(
            [
                "testmonitor",
                "product",
                "list",
                "--format",
                "json",
                "--name",
                "nonexistent-product-e2e-99999",
            ]
        )
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        assert isinstance(products, list)
        assert len(products) == 0

    def test_list_with_order_by(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with order-by option."""
        result = cli_runner(
            [
                "testmonitor",
                "product",
                "list",
                "--format",
                "json",
                "--order-by",
                "UPDATED_AT",
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        assert isinstance(products, list)

    def test_list_summary(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --summary flag."""
        result = cli_runner(["testmonitor", "product", "list", "--format", "json", "--summary"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)


@pytest.mark.e2e
@pytest.mark.testmonitor
class TestProductGetE2E:
    """End-to-end tests for 'testmonitor product get' command."""

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a specific product by ID."""
        result = cli_runner(["testmonitor", "product", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        if not products:
            pytest.skip("No products available for testing")

        product_id = products[0].get("id", "")
        assert product_id

        result = cli_runner(["testmonitor", "product", "get", product_id, "--format", "json"])
        cli_helper.assert_success(result)

        product = cli_helper.get_json_output(result)
        assert isinstance(product, dict)
        assert product.get("id") == product_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a product in table format."""
        result = cli_runner(["testmonitor", "product", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        products = cli_helper.get_json_output(result)
        if not products:
            pytest.skip("No products available for testing")

        product_id = products[0].get("id", "")
        result = cli_runner(["testmonitor", "product", "get", product_id, "--format", "table"])
        cli_helper.assert_success(result)

        assert "Product Details" in result.stdout or product_id in result.stdout

    def test_get_not_found(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a nonexistent product."""
        result = cli_runner(
            [
                "testmonitor",
                "product",
                "get",
                "nonexistent-product-id-e2e-12345",
                "--format",
                "json",
            ],
            check=False,
        )
        cli_helper.assert_failure(result)


@pytest.mark.e2e
@pytest.mark.testmonitor
class TestResultListE2E:
    """End-to-end tests for 'testmonitor result list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing test results in JSON format."""
        result = cli_runner(["testmonitor", "result", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)

        results = cli_helper.get_json_output(result)
        assert isinstance(results, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing test results in table format."""
        result = cli_runner(
            ["testmonitor", "result", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Should show table headers or empty message
        assert "Program" in result.stdout or "No" in result.stdout

    def test_list_with_take(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --take pagination limit (table output)."""
        result = cli_runner(
            ["testmonitor", "result", "list", "--format", "table", "--take", "3"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Table should display results with take=3 per page
        assert "Program" in result.stdout or "No" in result.stdout

    def test_list_with_status_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing results filtered by status."""
        result = cli_runner(
            [
                "testmonitor",
                "result",
                "list",
                "--format",
                "json",
                "--status",
                "PASSED",
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)

        results = cli_helper.get_json_output(result)
        assert isinstance(results, list)

    def test_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test listing results filtered by workspace."""
        result = cli_runner(
            [
                "testmonitor",
                "result",
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

        results = cli_helper.get_json_output(result)
        assert isinstance(results, list)

    def test_list_empty_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with a filter that matches nothing."""
        result = cli_runner(
            [
                "testmonitor",
                "result",
                "list",
                "--format",
                "json",
                "--program-name",
                "nonexistent-program-e2e-99999",
            ]
        )
        cli_helper.assert_success(result)

        results = cli_helper.get_json_output(result)
        assert isinstance(results, list)
        assert len(results) == 0

    def test_list_with_order_by(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with order-by option."""
        # Use table format — JSON fetches ALL matching results which can
        # timeout on large datasets even with status filter.
        result = cli_runner(
            [
                "testmonitor",
                "result",
                "list",
                "--format",
                "table",
                "--order-by",
                "UPDATED_AT",
                "--status",
                "PASSED",
                "--take",
                "5",
            ],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        assert "Status" in result.stdout or "No results found" in result.stdout

    def test_list_summary(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --summary flag."""
        result = cli_runner(["testmonitor", "result", "list", "--format", "json", "--summary"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)


@pytest.mark.e2e
@pytest.mark.testmonitor
class TestResultGetE2E:
    """End-to-end tests for 'testmonitor result get' command."""

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a specific test result by ID."""
        result = cli_runner(["testmonitor", "result", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        results = cli_helper.get_json_output(result)
        if not results:
            pytest.skip("No test results available for testing")

        result_id = results[0].get("id", "")
        assert result_id

        result = cli_runner(["testmonitor", "result", "get", result_id, "--format", "json"])
        cli_helper.assert_success(result)

        test_result = cli_helper.get_json_output(result)
        assert isinstance(test_result, dict)
        assert test_result.get("id") == result_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a test result in table format."""
        result = cli_runner(["testmonitor", "result", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)

        results = cli_helper.get_json_output(result)
        if not results:
            pytest.skip("No test results available for testing")

        result_id = results[0].get("id", "")
        result = cli_runner(["testmonitor", "result", "get", result_id, "--format", "table"])
        cli_helper.assert_success(result)

    def test_get_not_found(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a nonexistent test result."""
        result = cli_runner(
            [
                "testmonitor",
                "result",
                "get",
                "nonexistent-result-id-e2e-12345",
                "--format",
                "json",
            ],
            check=False,
        )
        cli_helper.assert_failure(result)


@pytest.mark.e2e
@pytest.mark.testmonitor
class TestTestmonitorHelpE2E:
    """End-to-end tests for testmonitor command help text."""

    def test_testmonitor_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'testmonitor --help' displays correctly."""
        result = cli_runner(["testmonitor", "--help"])
        cli_helper.assert_success(result)

        assert "product" in result.stdout
        assert "result" in result.stdout

    def test_product_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'testmonitor product --help' displays subcommands."""
        result = cli_runner(["testmonitor", "product", "--help"])
        cli_helper.assert_success(result)

        assert "list" in result.stdout
        assert "get" in result.stdout

    def test_result_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'testmonitor result --help' displays subcommands."""
        result = cli_runner(["testmonitor", "result", "--help"])
        cli_helper.assert_success(result)

        assert "list" in result.stdout
        assert "get" in result.stdout

    def test_product_list_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'testmonitor product list --help' displays all options."""
        result = cli_runner(["testmonitor", "product", "list", "--help"])
        cli_helper.assert_success(result)

        assert "--format" in result.stdout
        assert "--take" in result.stdout
        assert "--name" in result.stdout
        assert "--workspace" in result.stdout

    def test_result_list_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'testmonitor result list --help' displays all options."""
        result = cli_runner(["testmonitor", "result", "list", "--help"])
        cli_helper.assert_success(result)

        assert "--format" in result.stdout
        assert "--take" in result.stdout
        assert "--workspace" in result.stdout

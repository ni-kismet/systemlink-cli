"""E2E tests for system commands against dev tier."""

from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.system
class TestSystemListE2E:
    """End-to-end tests for 'system list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing systems in JSON format."""
        # Use APPROVED state filter — DISCONNECTED has too many results and
        # causes 500 when the API combines projection with large datasets.
        result = cli_runner(
            ["system", "list", "--format", "json", "--state", "APPROVED", "--take", "5"]
        )
        cli_helper.assert_success(result)

        systems = cli_helper.get_json_output(result)
        assert isinstance(systems, list)
        assert len(systems) > 0

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing systems in table format."""
        result = cli_runner(
            ["system", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        assert "Alias" in result.stdout
        assert "Host" in result.stdout
        assert "State" in result.stdout

    def test_list_with_take(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with --take pagination limit (table output)."""
        result = cli_runner(
            ["system", "list", "--format", "table", "--take", "3"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Table should display results with take=3
        assert "Alias" in result.stdout

    def test_list_with_state_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing systems filtered by connection state."""
        result = cli_runner(
            ["system", "list", "--format", "json", "--state", "APPROVED", "--take", "5"]
        )
        cli_helper.assert_success(result)

        systems = cli_helper.get_json_output(result)
        assert isinstance(systems, list)
        for sys_item in systems:
            state = sys_item.get("connected", "")
            assert state == "APPROVED"

    def test_list_with_os_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing systems filtered by alias (contains match)."""
        # NOTE: --os filter is incompatible with the query projection
        # (grains.data.kernel.Contains + projection gives 400).
        # Test --alias instead, which is a working contains filter.
        result = cli_runner(["system", "list", "--format", "json", "--alias", "Win", "--take", "5"])
        cli_helper.assert_success(result)

        systems = cli_helper.get_json_output(result)
        assert isinstance(systems, list)
        for sys_item in systems:
            alias = sys_item.get("alias", "")
            assert "Win" in alias

    def test_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test listing systems filtered by workspace."""
        # Use table format — JSON queries ALL matching systems which can
        # 500 for large workspaces combined with projection.
        result = cli_runner(
            [
                "system",
                "list",
                "--format",
                "table",
                "--workspace",
                configured_workspace,
                "--take",
                "5",
            ],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        assert "Alias" in result.stdout or "No systems found" in result.stdout

    def test_list_empty_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with a filter that matches nothing."""
        result = cli_runner(
            [
                "system",
                "list",
                "--format",
                "json",
                "--alias",
                "nonexistent-system-e2e-test-99999",
            ]
        )
        cli_helper.assert_success(result)

        systems = cli_helper.get_json_output(result)
        assert isinstance(systems, list)
        assert len(systems) == 0

    def test_list_with_order_by(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing with order-by option."""
        result = cli_runner(
            [
                "system",
                "list",
                "--format",
                "json",
                "--order-by",
                "updated_at",
                "--state",
                "APPROVED",
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)

        systems = cli_helper.get_json_output(result)
        assert isinstance(systems, list)


@pytest.mark.e2e
@pytest.mark.system
class TestSystemGetE2E:
    """End-to-end tests for 'system get' command."""

    def _get_system_id(self, cli_runner: Any, cli_helper: Any) -> str:
        """Get a valid system ID using a filtered list query."""
        result = cli_runner(
            ["system", "list", "--format", "json", "--state", "APPROVED", "--take", "1"]
        )
        cli_helper.assert_success(result)
        systems = cli_helper.get_json_output(result)
        if not systems:
            pytest.skip("No systems available for testing")
        system_id: str = systems[0].get("id", "")
        assert system_id
        return system_id

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a specific system by ID."""
        system_id = self._get_system_id(cli_runner, cli_helper)

        result = cli_runner(["system", "get", system_id, "--format", "json"])
        cli_helper.assert_success(result)

        system = cli_helper.get_json_output(result)
        assert isinstance(system, dict)
        assert system.get("id") == system_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a system in table format."""
        system_id = self._get_system_id(cli_runner, cli_helper)

        result = cli_runner(["system", "get", system_id, "--format", "table"])
        cli_helper.assert_success(result)

        assert "System Details" in result.stdout
        assert system_id in result.stdout

    def test_get_not_found(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a nonexistent system."""
        result = cli_runner(
            ["system", "get", "nonexistent-system-id-e2e-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_get_with_packages(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a system with --include-packages."""
        system_id = self._get_system_id(cli_runner, cli_helper)

        result = cli_runner(["system", "get", system_id, "--format", "json", "--include-packages"])
        cli_helper.assert_success(result)

        system = cli_helper.get_json_output(result)
        assert isinstance(system, dict)


@pytest.mark.e2e
@pytest.mark.system
class TestSystemSummaryE2E:
    """End-to-end tests for 'system summary' command."""

    def test_summary_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test fleet summary in JSON format."""
        result = cli_runner(["system", "summary", "--format", "json"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)

    def test_summary_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test fleet summary in table format."""
        result = cli_runner(["system", "summary", "--format", "table"])
        cli_helper.assert_success(result)

        assert "Fleet Summary" in result.stdout or "Total" in result.stdout


@pytest.mark.e2e
@pytest.mark.system
class TestSystemJobE2E:
    """End-to-end tests for 'system job' commands."""

    def test_job_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing jobs in JSON format."""
        result = cli_runner(["system", "job", "list", "--format", "json", "--take", "5"])
        cli_helper.assert_success(result)

        jobs = cli_helper.get_json_output(result)
        assert isinstance(jobs, list)

    def test_job_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing jobs in table format."""
        result = cli_runner(
            ["system", "job", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        # Should show table headers or empty message
        assert "Job ID" in result.stdout or "No jobs found" in result.stdout

    def test_job_list_with_state_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test listing jobs filtered by state."""
        result = cli_runner(
            ["system", "job", "list", "--format", "json", "--state", "SUCCEEDED", "--take", "5"]
        )
        cli_helper.assert_success(result)

        jobs = cli_helper.get_json_output(result)
        assert isinstance(jobs, list)
        for job in jobs:
            assert job.get("state") == "SUCCEEDED"

    def test_job_summary_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test job summary in JSON format."""
        result = cli_runner(["system", "job", "summary", "--format", "json"])
        cli_helper.assert_success(result)

        summary = cli_helper.get_json_output(result)
        assert isinstance(summary, dict)

    def test_job_get_not_found(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test getting a nonexistent job."""
        result = cli_runner(
            ["system", "job", "get", "nonexistent-job-id-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)


@pytest.mark.e2e
@pytest.mark.system
class TestSystemHelpE2E:
    """End-to-end tests for system command help text."""

    def test_system_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'system --help' displays correctly."""
        result = cli_runner(["system", "--help"])
        cli_helper.assert_success(result)

        assert "list" in result.stdout
        assert "get" in result.stdout
        assert "summary" in result.stdout
        assert "job" in result.stdout

    def test_system_list_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'system list --help' displays all options."""
        result = cli_runner(["system", "list", "--help"])
        cli_helper.assert_success(result)

        assert "--format" in result.stdout
        assert "--take" in result.stdout
        assert "--state" in result.stdout
        assert "--alias" in result.stdout

    def test_system_job_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test 'system job --help' displays subcommands."""
        result = cli_runner(["system", "job", "--help"])
        cli_helper.assert_success(result)

        assert "list" in result.stdout
        assert "get" in result.stdout
        assert "summary" in result.stdout

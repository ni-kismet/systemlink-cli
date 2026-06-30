"""E2E tests for state commands against a configured SystemLink instance."""

from pathlib import Path
from typing import Any, Optional

import pytest


@pytest.mark.e2e
@pytest.mark.state
class TestStateE2E:
    """Non-destructive end-to-end coverage for the state command group."""

    def _get_first_state_id(self, cli_runner: Any, cli_helper: Any) -> Optional[str]:
        """Return the first visible state ID, or None when no states exist."""
        result = cli_runner(["state", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        states = cli_helper.get_json_output(result)
        assert isinstance(states, list)
        if not states:
            return None
        return states[0].get("id")

    def test_state_list_basic(self, cli_runner: Any, cli_helper: Any) -> None:
        """State list should return JSON arrays."""
        result = cli_runner(["state", "list", "--format", "json", "--take", "5"])
        cli_helper.assert_success(result)
        states = cli_helper.get_json_output(result)
        assert isinstance(states, list)

    def test_state_list_table_format(self, cli_runner: Any, cli_helper: Any) -> None:
        """State list should render table output or an empty-state message."""
        result = cli_runner(["state", "list", "--format", "table", "--take", "5"])
        cli_helper.assert_success(result)
        assert "Name" in result.stdout or "No states found" in result.stdout

    def test_state_get_first_available(self, cli_runner: Any, cli_helper: Any) -> None:
        """State get should succeed for an existing state when one is available."""
        state_id = self._get_first_state_id(cli_runner, cli_helper)
        if not state_id:
            pytest.skip("No states available to validate state get")

        result = cli_runner(["state", "get", state_id, "--format", "json"])
        cli_helper.assert_success(result)
        state = cli_helper.get_json_output(result)
        assert isinstance(state, dict)
        assert state.get("id") == state_id

    def test_state_history_first_available(self, cli_runner: Any, cli_helper: Any) -> None:
        """State history should return JSON arrays when a state is available."""
        state_id = self._get_first_state_id(cli_runner, cli_helper)
        if not state_id:
            pytest.skip("No states available to validate history")

        result = cli_runner(["state", "history", state_id, "--format", "json", "--take", "5"])
        cli_helper.assert_success(result)
        history = cli_helper.get_json_output(result)
        assert isinstance(history, list)

    def test_state_export_first_available(
        self, cli_runner: Any, cli_helper: Any, tmp_path: Path
    ) -> None:
        """State export should write an .sls file when a state is available."""
        state_id = self._get_first_state_id(cli_runner, cli_helper)
        if not state_id:
            pytest.skip("No states available to validate export")

        output_path = tmp_path / "exported-state.sls"
        result = cli_runner(["state", "export", state_id, "--output", str(output_path)])
        cli_helper.assert_success(result)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_state_help(self, cli_runner: Any, cli_helper: Any) -> None:
        """State commands should expose help text."""
        result = cli_runner(["state", "--help"])
        cli_helper.assert_success(result)
        assert "Manage SystemLink states" in result.stdout

        result = cli_runner(["state", "list", "--help"])
        cli_helper.assert_success(result)
        assert "--architecture" in result.stdout
        assert "--distribution" in result.stdout

"""E2E tests for routine commands against a live SystemLink instance."""

import uuid
from typing import Any, Optional

import pytest


def _extract_routine_id(stdout: str) -> Optional[str]:
    """Parse the routine ID emitted by 'routine create' / 'routine update' success output.

    format_success produces lines like:
        ✓ Routine created
          id: <routine_id>
          name: <name>
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            return stripped.split(":", 1)[1].strip()
    return None


def _make_tag_event_json(trigger_name: str, tag_path: str) -> str:
    """Build a minimal v2 TAG event JSON string."""
    return (
        f'{{"type":"TAG","triggers":[{{"name":"{trigger_name}",'
        f'"configuration":{{"comparator":"GREATER_THAN","path":"{tag_path}",'
        f'"thresholds":["99999"],"type":"DOUBLE"}}}}]}}'
    )


def _make_alarm_actions_json(trigger_name: str, display_name: str) -> str:
    """Build a minimal v2 ALARM actions JSON array string."""
    return (
        f'[{{"type":"ALARM","triggers":["{trigger_name}"],'
        f'"configuration":{{"displayName":"{display_name}",'
        f'"severity":1,"condition":"Greater than 99999"}}}},'
        f'{{"type":"ALARM","triggers":["nisystemlink_no_triggers_breached"],'
        f'"configuration":null}}]'
    )


@pytest.mark.e2e
@pytest.mark.routine
class TestRoutineListE2E:
    """End-to-end tests for 'routine list' command."""

    def test_list_default_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test routine list in default table format."""
        result = cli_runner(["routine", "list", "--format", "table"])
        cli_helper.assert_success(result)
        # Should show table headers or "No routines found"
        assert "Name" in result.stdout or "No routines found" in result.stdout

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test routine list in JSON format returns a list."""
        result = cli_runner(["routine", "list", "--format", "json"])
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)

    def test_list_enabled_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test routine list --enabled only returns enabled routines."""
        result = cli_runner(["routine", "list", "--enabled", "--format", "json"])
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)
        for routine in routines:
            assert (
                routine.get("enabled") is True
            ), f"Routine '{routine.get('name')}' should be enabled but is not"

    def test_list_disabled_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test routine list --disabled only returns disabled routines."""
        result = cli_runner(["routine", "list", "--disabled", "--format", "json"])
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)
        for routine in routines:
            assert (
                routine.get("enabled") is False
            ), f"Routine '{routine.get('name')}' should be disabled but is not"

    def test_list_v1(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test routine list with --api-version v1."""
        result = cli_runner(["routine", "list", "--api-version", "v1", "--format", "json"])
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)

    def test_list_take_limits_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test that --take limits the number of returned routines."""
        result = cli_runner(["routine", "list", "--take", "2", "--format", "json"])
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)
        assert len(routines) <= 2

    def test_list_name_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test list --filter returns only routines whose name contains the substring."""
        unique = uuid.uuid4().hex[:8]
        routine_name = f"e2e-routine-filter-{unique}"
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    routine_name,
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.filter.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E Filter Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            routine_id = _extract_routine_id(result.stdout)

            result = cli_runner(["routine", "list", "--filter", routine_name, "--format", "json"])
            cli_helper.assert_success(result)
            routines = cli_helper.get_json_output(result)
            names = [r.get("name") for r in routines]
            assert (
                routine_name in names
            ), f"Routine '{routine_name}' not found in filtered list: {names}"

        finally:
            if routine_id:
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_list_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test list --workspace returns results for that workspace."""
        result = cli_runner(
            [
                "routine",
                "list",
                "--workspace",
                configured_workspace,
                "--format",
                "json",
            ]
        )
        cli_helper.assert_success(result)
        routines = cli_helper.get_json_output(result)
        assert isinstance(routines, list)


@pytest.mark.e2e
@pytest.mark.routine
class TestRoutineV2LifecycleE2E:
    """End-to-end lifecycle tests for v2 routine commands."""

    def test_v2_full_lifecycle(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test full v2 routine lifecycle: create, list, get, update, enable, disable, delete."""
        unique = uuid.uuid4().hex[:8]
        routine_name = f"e2e-routine-{unique}"
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            # --- CREATE ---
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    routine_name,
                    "--description",
                    "E2E lifecycle test routine",
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.lifecycle.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E Lifecycle Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            assert "Routine created" in result.stdout

            routine_id = _extract_routine_id(result.stdout)
            assert routine_id, f"Could not extract routine ID from output:\n{result.stdout}"

            # --- LIST (verify created, disabled by default) ---
            result = cli_runner(["routine", "list", "--filter", routine_name, "--format", "json"])
            cli_helper.assert_success(result)
            routines = cli_helper.get_json_output(result)
            found = next((r for r in routines if r.get("name") == routine_name), None)
            assert found is not None, f"Created routine '{routine_name}' not found in list"
            assert found.get("enabled") is False, "New routine should default to disabled"

            # --- GET ---
            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            fetched = cli_helper.get_json_output(result)
            assert fetched.get("id") == routine_id
            assert fetched.get("name") == routine_name
            assert fetched.get("description") == "E2E lifecycle test routine"

            # --- UPDATE (rename) ---
            updated_name = f"e2e-routine-updated-{unique}"
            result = cli_runner(["routine", "update", routine_id, "--name", updated_name])
            cli_helper.assert_success(result)
            assert "Routine updated" in result.stdout

            # Verify name changed
            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            updated = cli_helper.get_json_output(result)
            assert updated.get("name") == updated_name

            # --- ENABLE ---
            result = cli_runner(["routine", "enable", routine_id])
            cli_helper.assert_success(result)
            assert "Routine enabled" in result.stdout

            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("enabled") is True

            # --- DISABLE ---
            result = cli_runner(["routine", "disable", routine_id])
            cli_helper.assert_success(result)
            assert "Routine disabled" in result.stdout

            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("enabled") is False

            # --- DELETE ---
            result = cli_runner(["routine", "delete", routine_id, "--yes"])
            cli_helper.assert_success(result)
            assert "Routine deleted" in result.stdout
            routine_id = None  # Mark as deleted so finally block skips it

        finally:
            if routine_id:
                # Best-effort cleanup if test failed mid-way
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_create_disabled_by_default(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test that a newly created routine is disabled by default."""
        unique = uuid.uuid4().hex[:8]
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    f"e2e-disabled-{unique}",
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.disabled.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E Disabled Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            routine_id = _extract_routine_id(result.stdout)
            assert routine_id

            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("enabled") is False

        finally:
            if routine_id:
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_create_enabled_flag(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test that --enabled creates a routine in enabled state."""
        unique = uuid.uuid4().hex[:8]
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    f"e2e-enabled-{unique}",
                    "--enabled",
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.enabled.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E Enabled Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            routine_id = _extract_routine_id(result.stdout)
            assert routine_id

            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("enabled") is True

        finally:
            if routine_id:
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_update_description(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test updating a routine's description."""
        unique = uuid.uuid4().hex[:8]
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    f"e2e-updesc-{unique}",
                    "--description",
                    "Original description",
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.updesc.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E Updesc Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            routine_id = _extract_routine_id(result.stdout)
            assert routine_id

            result = cli_runner(
                [
                    "routine",
                    "update",
                    routine_id,
                    "--description",
                    "Updated description",
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("description") == "Updated description"

        finally:
            if routine_id:
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_delete_requires_confirmation(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test that delete without --yes prompts and aborts when user declines."""
        unique = uuid.uuid4().hex[:8]
        trigger_name = uuid.uuid4().hex[:8]
        routine_id = None

        try:
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--name",
                    f"e2e-delconf-{unique}",
                    "--event",
                    _make_tag_event_json(trigger_name, f"e2e.delconf.{unique}.*"),
                    "--actions",
                    _make_alarm_actions_json(trigger_name, f"E2E DelConf Alarm {unique}"),
                ]
            )
            cli_helper.assert_success(result)
            routine_id = _extract_routine_id(result.stdout)
            assert routine_id

            # Decline confirmation
            result = cli_runner(
                ["routine", "delete", routine_id],
                input_data="n\n",
                check=False,
            )
            assert result.returncode != 0

            # Verify routine still exists
            result = cli_runner(["routine", "get", routine_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("id") == routine_id

        finally:
            if routine_id:
                cli_runner(["routine", "delete", routine_id, "--yes"], check=False)

    def test_get_nonexistent_routine(self, cli_runner: Any) -> None:
        """Test that getting a non-existent routine returns a non-zero exit code."""
        fake_id = "000000000000000000000000"
        result = cli_runner(["routine", "get", fake_id, "--format", "json"], check=False)
        assert result.returncode != 0

    def test_delete_nonexistent_routine(self, cli_runner: Any) -> None:
        """Test that deleting a non-existent routine returns a non-zero exit code."""
        fake_id = "000000000000000000000000"
        result = cli_runner(
            ["routine", "delete", fake_id, "--yes"],
            check=False,
        )
        assert result.returncode != 0


@pytest.mark.e2e
@pytest.mark.routine
class TestRoutineErrorHandlingE2E:
    """End-to-end error handling tests for routine commands."""

    def test_create_v2_missing_event(self, cli_runner: Any) -> None:
        """Test that create fails when --event is missing (server-side or client-side)."""
        result = cli_runner(
            [
                "routine",
                "create",
                "--name",
                f"e2e-bad-{uuid.uuid4().hex[:8]}",
                "--actions",
                '[{"type":"ALARM","triggers":["t1"],"configuration":null}]',
            ],
            check=False,
        )
        assert result.returncode != 0

    def test_create_v2_invalid_event_json(self, cli_runner: Any) -> None:
        """Test that create fails with invalid JSON for --event."""
        result = cli_runner(
            [
                "routine",
                "create",
                "--name",
                f"e2e-badjson-{uuid.uuid4().hex[:8]}",
                "--event",
                "this-is-not-json",
                "--actions",
                '[{"type":"ALARM"}]',
            ],
            check=False,
        )
        assert result.returncode != 0
        assert "Invalid JSON" in result.stdout or "Invalid JSON" in result.stderr

    def test_update_no_fields(self, cli_runner: Any) -> None:
        """Test that update with no fields returns INVALID_INPUT."""
        fake_id = "000000000000000000000000"
        result = cli_runner(
            ["routine", "update", fake_id],
            check=False,
        )
        assert (
            result.returncode == 2
        ), f"Expected exit code 2 (INVALID_INPUT) but got {result.returncode}"

    def test_create_v1_missing_type(self, cli_runner: Any) -> None:
        """Test that create v1 fails when --type is missing."""
        result = cli_runner(
            [
                "routine",
                "create",
                "--api-version",
                "v1",
                "--name",
                f"e2e-v1bad-{uuid.uuid4().hex[:8]}",
                "--notebook-id",
                "fake-notebook-id",
            ],
            check=False,
        )
        assert result.returncode != 0

    def test_create_v1_missing_notebook_id(self, cli_runner: Any) -> None:
        """Test that create v1 fails when --notebook-id is missing."""
        result = cli_runner(
            [
                "routine",
                "create",
                "--api-version",
                "v1",
                "--name",
                f"e2e-v1nonb-{uuid.uuid4().hex[:8]}",
                "--type",
                "SCHEDULED",
            ],
            check=False,
        )
        assert result.returncode != 0


@pytest.mark.e2e
@pytest.mark.routine
class TestRoutineV1LifecycleE2E:
    """E2E lifecycle tests for v1 (notebook scheduling) routines.

    These tests are skipped unless a test_notebook_id is configured in e2e_config.json
    under the 'sle' section.
    """

    def test_v1_scheduled_lifecycle(
        self,
        cli_runner: Any,
        cli_helper: Any,
        sle_test_notebook_id: Any,
    ) -> None:
        """Test full v1 SCHEDULED routine lifecycle: create, list, get, update, delete."""
        if not sle_test_notebook_id:
            pytest.skip("sle.test_notebook_id not configured in e2e_config.json")

        unique = uuid.uuid4().hex[:8]
        routine_name = f"e2e-v1-routine-{unique}"
        routine_id = None

        try:
            # --- CREATE ---
            result = cli_runner(
                [
                    "routine",
                    "create",
                    "--api-version",
                    "v1",
                    "--name",
                    routine_name,
                    "--type",
                    "SCHEDULED",
                    "--notebook-id",
                    sle_test_notebook_id,
                    "--schedule",
                    '{"startTime":"2099-01-01T00:00:00Z","repeat":"DAY"}',
                ]
            )
            cli_helper.assert_success(result)
            assert "Routine created" in result.stdout

            routine_id = _extract_routine_id(result.stdout)
            assert routine_id, f"Could not extract routine ID:\n{result.stdout}"

            # --- LIST (v1) ---
            result = cli_runner(
                [
                    "routine",
                    "list",
                    "--api-version",
                    "v1",
                    "--filter",
                    routine_name,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)
            routines = cli_helper.get_json_output(result)
            found = next((r for r in routines if r.get("name") == routine_name), None)
            assert found is not None, f"Created v1 routine '{routine_name}' not found in list"

            # --- GET ---
            result = cli_runner(
                ["routine", "get", routine_id, "--api-version", "v1", "--format", "json"]
            )
            cli_helper.assert_success(result)
            fetched = cli_helper.get_json_output(result)
            assert fetched.get("id") == routine_id

            # --- UPDATE notebook ID ---
            result = cli_runner(
                [
                    "routine",
                    "update",
                    routine_id,
                    "--api-version",
                    "v1",
                    "--notebook-id",
                    sle_test_notebook_id,
                ]
            )
            cli_helper.assert_success(result)
            assert "Routine updated" in result.stdout

            # --- DELETE ---
            result = cli_runner(["routine", "delete", routine_id, "--api-version", "v1", "--yes"])
            cli_helper.assert_success(result)
            assert "Routine deleted" in result.stdout
            routine_id = None

        finally:
            if routine_id:
                cli_runner(
                    ["routine", "delete", routine_id, "--api-version", "v1", "--yes"],
                    check=False,
                )

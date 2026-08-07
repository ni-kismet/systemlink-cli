"""E2E tests for alarm commands against a configured SystemLink environment."""

import uuid
from typing import Any, Optional

import pytest


@pytest.mark.e2e
@pytest.mark.alarm
class TestAlarmLifecycleE2E:
    """End-to-end tests for alarm creation and lifecycle commands."""

    def test_create_inspect_acknowledge_clear_delete(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test the alarm lifecycle through the public CLI commands."""
        alarm_id = f"slcli-e2e-alarm-{uuid.uuid4().hex}"
        instance_id: Optional[str] = None

        try:
            result = cli_runner(
                [
                    "alarm",
                    "transition",
                    alarm_id,
                    "--workspace",
                    configured_workspace,
                    "--severity",
                    "2",
                    "--channel",
                    "slcli-e2e",
                    "--resource-type",
                    "E2E",
                    "--display-name",
                    "slcli E2E alarm",
                    "--created-by",
                    "slcli-e2e",
                    "--format",
                    "json",
                ],
                check=False,
            )
            if "readonly" in result.stderr.lower():
                pytest.skip("Profile is in readonly mode")
            cli_helper.assert_success(result)

            created = cli_helper.get_json_output(result)
            instance_id = created.get("instanceId") if isinstance(created, dict) else None
            assert instance_id

            result = cli_runner(
                [
                    "alarm",
                    "list",
                    "--alarm-id",
                    alarm_id,
                    "--workspace",
                    configured_workspace,
                    "--state",
                    "all",
                    "--format",
                    "json",
                ]
            )
            alarms = cli_helper.get_json_output(result)
            assert any(item.get("instanceId") == instance_id for item in alarms)

            result = cli_runner(["alarm", "get", instance_id, "--format", "json"])
            alarm = cli_helper.get_json_output(result)
            assert alarm.get("alarmId") == alarm_id

            result = cli_runner(["alarm", "acknowledge", instance_id])
            cli_helper.assert_success(result)

            result = cli_runner(["alarm", "force-clear", instance_id, "--yes", "--format", "json"])
            cli_helper.assert_success(result)

            result = cli_runner(["alarm", "delete", instance_id, "--yes", "--format", "json"])
            cli_helper.assert_success(result)
            instance_id = None
        finally:
            if instance_id:
                cli_runner(["alarm", "delete", instance_id, "--yes"], check=False)

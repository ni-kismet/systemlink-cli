"""E2E tests for workitem commands against a live SystemLink instance."""

import uuid
from typing import Any, Optional

import pytest


def _extract_id(stdout: str) -> Optional[str]:
    """Parse the ID from format_success output.

    format_success produces lines like:
        ✓ Work item created
          id: <id>
          name: <name>
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("id:"):
            return stripped.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# workitem list
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemListE2E:
    """End-to-end tests for 'workitem list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """List work items in JSON format returns a list."""
        result = cli_runner(["workitem", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)

        items = cli_helper.get_json_output(result)
        assert isinstance(items, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """List work items in table format shows headers or empty message."""
        result = cli_runner(
            ["workitem", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)
        assert "ID" in result.stdout or "No work items found" in result.stdout

    def test_list_take_limits_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """--take limits the number of results in JSON output."""
        result = cli_runner(["workitem", "list", "--format", "json", "--take", "3"])
        cli_helper.assert_success(result)
        items = cli_helper.get_json_output(result)
        assert isinstance(items, list)
        assert len(items) <= 3

    def test_list_state_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """--state filters results to the specified state."""
        result = cli_runner(
            ["workitem", "list", "--format", "json", "--state", "NEW", "--take", "10"]
        )
        cli_helper.assert_success(result)
        items = cli_helper.get_json_output(result)
        assert isinstance(items, list)
        for item in items:
            assert item.get("state") == "NEW", f"Expected state NEW, got {item.get('state')}"

    def test_list_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """--workspace filters results to the given workspace."""
        result = cli_runner(
            [
                "workitem",
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
        items = cli_helper.get_json_output(result)
        assert isinstance(items, list)

    def test_list_empty_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Filter that matches nothing returns an empty list in JSON mode."""
        nonexistent_name = f"nonexistent-wi-e2e-{uuid.uuid4().hex}"
        result = cli_runner(
            [
                "workitem",
                "list",
                "--format",
                "json",
                "--filter",
                f'name == "{nonexistent_name}"',
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)
        items = cli_helper.get_json_output(result)
        assert isinstance(items, list)
        assert len(items) == 0

    def test_list_pagination_prompt_declined(self, cli_runner: Any, cli_helper: Any) -> None:
        """Declining the pagination prompt stops fetching without error."""
        result = cli_runner(
            ["workitem", "list", "--format", "table", "--take", "2"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)


# ---------------------------------------------------------------------------
# workitem get
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemGetE2E:
    """End-to-end tests for 'workitem get' command."""

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a work item by ID in JSON format."""
        result = cli_runner(["workitem", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        items = cli_helper.get_json_output(result)
        if not items:
            pytest.skip("No work items available for testing")

        wi_id = items[0].get("id", "")
        assert wi_id

        result = cli_runner(["workitem", "get", wi_id, "--format", "json"])
        cli_helper.assert_success(result)
        fetched = cli_helper.get_json_output(result)
        assert isinstance(fetched, dict)
        assert fetched.get("id") == wi_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a work item in table format."""
        result = cli_runner(["workitem", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        items = cli_helper.get_json_output(result)
        if not items:
            pytest.skip("No work items available for testing")

        wi_id = items[0].get("id", "")
        result = cli_runner(["workitem", "get", wi_id, "--format", "table"])
        cli_helper.assert_success(result)
        assert wi_id in result.stdout

    def test_get_not_found(self, cli_runner: Any) -> None:
        """Getting a nonexistent work item returns a non-zero exit code."""
        result = cli_runner(
            ["workitem", "get", "nonexistent-wi-id-e2e-99999", "--format", "json"],
            check=False,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# workitem full lifecycle (create → update → delete)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemLifecycleE2E:
    """End-to-end lifecycle tests for work item create/update/delete."""

    def test_full_lifecycle(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Create, verify, update, and delete a work item."""
        unique = uuid.uuid4().hex[:8]
        wi_name = f"e2e-wi-{unique}"
        wi_id = None

        try:
            # --- CREATE ---
            result = cli_runner(
                [
                    "workitem",
                    "create",
                    "--name",
                    wi_name,
                    "--type",
                    "testplan",
                    "--state",
                    "NEW",
                    "--part-number",
                    "P-E2E-001",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "table",
                ]
            )
            cli_helper.assert_success(result)
            assert "Work item created" in result.stdout

            wi_id = _extract_id(result.stdout)
            assert wi_id, f"Could not extract work item ID from:\n{result.stdout}"

            # --- LIST (verify it appears) ---
            result = cli_runner(
                [
                    "workitem",
                    "list",
                    "--format",
                    "json",
                    "--filter",
                    f'name == "{wi_name}"',
                    "--take",
                    "10",
                ]
            )
            cli_helper.assert_success(result)
            items = cli_helper.get_json_output(result)
            found = next((i for i in items if i.get("id") == wi_id), None)
            assert found is not None, f"Created work item '{wi_id}' not found in list"

            # --- GET ---
            result = cli_runner(["workitem", "get", wi_id, "--format", "json"])
            cli_helper.assert_success(result)
            fetched = cli_helper.get_json_output(result)
            assert fetched.get("id") == wi_id
            assert fetched.get("name") == wi_name

            # --- UPDATE ---
            updated_name = f"e2e-wi-updated-{unique}"
            result = cli_runner(
                ["workitem", "update", wi_id, "--name", updated_name, "--state", "DEFINED"]
            )
            cli_helper.assert_success(result)

            # Verify update took effect
            result = cli_runner(["workitem", "get", wi_id, "--format", "json"])
            cli_helper.assert_success(result)
            updated = cli_helper.get_json_output(result)
            assert updated.get("name") == updated_name
            assert updated.get("state") == "DEFINED"

            # --- DELETE ---
            result = cli_runner(["workitem", "delete", wi_id, "--yes"])
            cli_helper.assert_success(result)
            wi_id = None  # Mark as deleted

        finally:
            if wi_id:
                cli_runner(["workitem", "delete", wi_id, "--yes"], check=False)

    def test_create_json_format(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Create returns the created work item in JSON when --format json is used."""
        unique = uuid.uuid4().hex[:8]
        wi_id = None

        try:
            result = cli_runner(
                [
                    "workitem",
                    "create",
                    "--name",
                    f"e2e-wi-json-{unique}",
                    "--type",
                    "testplan",
                    "--state",
                    "NEW",
                    "--part-number",
                    "P-E2E-001",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)
            created = cli_helper.get_json_output(result)
            assert isinstance(created, dict)
            wi_id = created.get("id")
            assert wi_id

        finally:
            if wi_id:
                cli_runner(["workitem", "delete", wi_id, "--yes"], check=False)

    def test_delete_requires_confirmation(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Delete without --yes prompts; declining leaves the item intact."""
        unique = uuid.uuid4().hex[:8]
        wi_id = None

        try:
            result = cli_runner(
                [
                    "workitem",
                    "create",
                    "--name",
                    f"e2e-wi-delconf-{unique}",
                    "--type",
                    "testplan",
                    "--state",
                    "NEW",
                    "--part-number",
                    "P-E2E-001",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            wi_id = _extract_id(result.stdout)
            assert wi_id

            # Decline the confirmation
            result = cli_runner(
                ["workitem", "delete", wi_id],
                input_data="n\n",
                check=False,
            )
            # Declining prints "Aborted." and returns cleanly (exit 0)
            assert result.returncode == 0
            assert "Aborted" in result.stdout

            # Verify item still exists
            result = cli_runner(["workitem", "get", wi_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("id") == wi_id

        finally:
            if wi_id:
                cli_runner(["workitem", "delete", wi_id, "--yes"], check=False)


# ---------------------------------------------------------------------------
# workitem template list
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemTemplateListE2E:
    """End-to-end tests for 'workitem template list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """List templates in JSON format returns a list."""
        result = cli_runner(["workitem", "template", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)
        templates = cli_helper.get_json_output(result)
        assert isinstance(templates, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """List templates in table format shows headers or empty message."""
        result = cli_runner(
            ["workitem", "template", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)
        assert "Name" in result.stdout or "No templates found" in result.stdout

    def test_list_take_limits_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """--take limits the number of results in JSON output."""
        result = cli_runner(["workitem", "template", "list", "--format", "json", "--take", "2"])
        cli_helper.assert_success(result)
        templates = cli_helper.get_json_output(result)
        assert isinstance(templates, list)
        assert len(templates) <= 2

    def test_list_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """--workspace filters to the given workspace."""
        result = cli_runner(
            [
                "workitem",
                "template",
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
        templates = cli_helper.get_json_output(result)
        assert isinstance(templates, list)

    def test_list_empty_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Filter matching nothing returns an empty list."""
        bogus = f"nonexistent-tmpl-e2e-{uuid.uuid4().hex}"
        result = cli_runner(
            [
                "workitem",
                "template",
                "list",
                "--format",
                "json",
                "--filter",
                f'name == "{bogus}"',
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)
        templates = cli_helper.get_json_output(result)
        assert isinstance(templates, list)
        assert len(templates) == 0


# ---------------------------------------------------------------------------
# workitem template get
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemTemplateGetE2E:
    """End-to-end tests for 'workitem template get' command."""

    def test_get_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a template by ID in JSON format."""
        result = cli_runner(["workitem", "template", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        templates = cli_helper.get_json_output(result)
        if not templates:
            pytest.skip("No templates available for testing")

        tmpl_id = templates[0].get("id", "")
        assert tmpl_id

        result = cli_runner(["workitem", "template", "get", tmpl_id, "--format", "json"])
        cli_helper.assert_success(result)
        fetched = cli_helper.get_json_output(result)
        assert isinstance(fetched, dict)
        assert fetched.get("id") == tmpl_id

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a template in table format."""
        result = cli_runner(["workitem", "template", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        templates = cli_helper.get_json_output(result)
        if not templates:
            pytest.skip("No templates available for testing")

        tmpl_id = templates[0].get("id", "")
        result = cli_runner(["workitem", "template", "get", tmpl_id, "--format", "table"])
        cli_helper.assert_success(result)
        assert "Work Item Template Details" in result.stdout or tmpl_id in result.stdout

    def test_get_not_found(self, cli_runner: Any) -> None:
        """Getting a nonexistent template returns a non-zero exit code."""
        result = cli_runner(
            ["workitem", "template", "get", "nonexistent-tmpl-id-e2e-99999", "--format", "json"],
            check=False,
        )
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# workitem template full lifecycle (create → update → delete)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemTemplateLifecycleE2E:
    """End-to-end lifecycle tests for work item template create/update/delete."""

    def test_full_lifecycle(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Create, verify, update, and delete a work item template."""
        unique = uuid.uuid4().hex[:8]
        tmpl_name = f"e2e-tmpl-{unique}"
        tmpl_id = None

        try:
            # --- CREATE ---
            result = cli_runner(
                [
                    "workitem",
                    "template",
                    "create",
                    "--name",
                    tmpl_name,
                    "--type",
                    "testplan",
                    "--template-group",
                    f"e2e-group-{unique}",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "table",
                ]
            )
            cli_helper.assert_success(result)
            assert "Template created" in result.stdout

            tmpl_id = _extract_id(result.stdout)
            assert tmpl_id, f"Could not extract template ID from:\n{result.stdout}"

            # --- LIST (verify it appears) ---
            result = cli_runner(
                [
                    "workitem",
                    "template",
                    "list",
                    "--format",
                    "json",
                    "--filter",
                    f'name == "{tmpl_name}"',
                    "--take",
                    "10",
                ]
            )
            cli_helper.assert_success(result)
            templates = cli_helper.get_json_output(result)
            found = next((t for t in templates if t.get("id") == tmpl_id), None)
            assert found is not None, f"Created template '{tmpl_id}' not found in list"

            # --- GET ---
            result = cli_runner(["workitem", "template", "get", tmpl_id, "--format", "json"])
            cli_helper.assert_success(result)
            fetched = cli_helper.get_json_output(result)
            assert fetched.get("id") == tmpl_id
            assert fetched.get("name") == tmpl_name

            # --- UPDATE ---
            updated_name = f"e2e-tmpl-updated-{unique}"
            result = cli_runner(
                [
                    "workitem",
                    "template",
                    "update",
                    tmpl_id,
                    "--name",
                    updated_name,
                    "--description",
                    "Updated by e2e test",
                ]
            )
            cli_helper.assert_success(result)
            assert "updated" in result.stdout.lower()

            # Verify update
            result = cli_runner(["workitem", "template", "get", tmpl_id, "--format", "json"])
            cli_helper.assert_success(result)
            updated = cli_helper.get_json_output(result)
            assert updated.get("name") == updated_name
            assert updated.get("description") == "Updated by e2e test"

            # --- DELETE ---
            result = cli_runner(["workitem", "template", "delete", tmpl_id, "--yes"])
            cli_helper.assert_success(result)
            tmpl_id = None  # Mark as deleted

        finally:
            if tmpl_id:
                cli_runner(["workitem", "template", "delete", tmpl_id, "--yes"], check=False)

    def test_delete_requires_confirmation(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Delete without --yes prompts; declining leaves the template intact."""
        unique = uuid.uuid4().hex[:8]
        tmpl_id = None

        try:
            result = cli_runner(
                [
                    "workitem",
                    "template",
                    "create",
                    "--name",
                    f"e2e-tmpl-delconf-{unique}",
                    "--type",
                    "testplan",
                    "--template-group",
                    f"e2e-group-{unique}",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            tmpl_id = _extract_id(result.stdout)
            assert tmpl_id

            result = cli_runner(
                ["workitem", "template", "delete", tmpl_id],
                input_data="n\n",
                check=False,
            )
            # Declining prints "Aborted." and returns cleanly (exit 0)
            assert result.returncode == 0
            assert "Aborted" in result.stdout

            # Verify template still exists
            result = cli_runner(["workitem", "template", "get", tmpl_id, "--format", "json"])
            cli_helper.assert_success(result)
            assert cli_helper.get_json_output(result).get("id") == tmpl_id

        finally:
            if tmpl_id:
                cli_runner(["workitem", "template", "delete", tmpl_id, "--yes"], check=False)


# ---------------------------------------------------------------------------
# workitem workflow list
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemWorkflowListE2E:
    """End-to-end tests for 'workitem workflow list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """List workflows in JSON format returns a list."""
        result = cli_runner(["workitem", "workflow", "list", "--format", "json", "--take", "10"])
        cli_helper.assert_success(result)
        workflows = cli_helper.get_json_output(result)
        assert isinstance(workflows, list)

    def test_list_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """List workflows in table format shows headers or empty message."""
        result = cli_runner(
            ["workitem", "workflow", "list", "--format", "table", "--take", "5"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)
        assert "Name" in result.stdout or "No workflows found" in result.stdout

    def test_list_take_limits_results(self, cli_runner: Any, cli_helper: Any) -> None:
        """--take limits the number of results in JSON output."""
        result = cli_runner(["workitem", "workflow", "list", "--format", "json", "--take", "2"])
        cli_helper.assert_success(result)
        workflows = cli_helper.get_json_output(result)
        assert isinstance(workflows, list)
        assert len(workflows) <= 2

    def test_list_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """--workspace filters to the given workspace."""
        result = cli_runner(
            [
                "workitem",
                "workflow",
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
        workflows = cli_helper.get_json_output(result)
        assert isinstance(workflows, list)

    def test_list_pagination_prompt_declined(self, cli_runner: Any, cli_helper: Any) -> None:
        """Declining the pagination prompt stops fetching without error."""
        result = cli_runner(
            ["workitem", "workflow", "list", "--format", "table", "--take", "2"],
            input_data="n\n",
        )
        cli_helper.assert_success(result)


# ---------------------------------------------------------------------------
# workitem workflow get
# ---------------------------------------------------------------------------


@pytest.mark.e2e
@pytest.mark.workitem
class TestWorkitemWorkflowGetE2E:
    """End-to-end tests for 'workitem workflow get' command."""

    def test_get_by_id_json(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a workflow by ID in JSON format."""
        result = cli_runner(["workitem", "workflow", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        workflows = cli_helper.get_json_output(result)
        if not workflows:
            pytest.skip("No workflows available for testing")

        wf_id = workflows[0].get("id", "")
        assert wf_id

        result = cli_runner(["workitem", "workflow", "get", "--id", wf_id, "--format", "json"])
        cli_helper.assert_success(result)
        fetched = cli_helper.get_json_output(result)
        assert isinstance(fetched, dict)
        assert fetched.get("id") == wf_id

    def test_get_by_name(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a workflow by name."""
        result = cli_runner(["workitem", "workflow", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        workflows = cli_helper.get_json_output(result)
        if not workflows:
            pytest.skip("No workflows available for testing")

        wf_name = workflows[0].get("name", "")
        if not wf_name:
            pytest.skip("First workflow has no name")

        result = cli_runner(["workitem", "workflow", "get", "--name", wf_name, "--format", "json"])
        cli_helper.assert_success(result)
        fetched = cli_helper.get_json_output(result)
        assert fetched.get("name") == wf_name

    def test_get_table(self, cli_runner: Any, cli_helper: Any) -> None:
        """Get a workflow in table format."""
        result = cli_runner(["workitem", "workflow", "list", "--format", "json", "--take", "1"])
        cli_helper.assert_success(result)
        workflows = cli_helper.get_json_output(result)
        if not workflows:
            pytest.skip("No workflows available for testing")

        wf_id = workflows[0].get("id", "")
        result = cli_runner(["workitem", "workflow", "get", "--id", wf_id, "--format", "table"])
        cli_helper.assert_success(result)
        assert wf_id in result.stdout or "Workflow" in result.stdout

    def test_get_not_found(self, cli_runner: Any) -> None:
        """Getting a nonexistent workflow returns a non-zero exit code."""
        result = cli_runner(
            [
                "workitem",
                "workflow",
                "get",
                "--id",
                "00000000-0000-0000-0000-000000000000",
                "--format",
                "json",
            ],
            check=False,
        )
        assert result.returncode != 0

    def test_get_requires_id_or_name(self, cli_runner: Any) -> None:
        """Get without --id or --name fails with a non-zero exit code."""
        result = cli_runner(
            ["workitem", "workflow", "get", "--format", "json"],
            check=False,
        )
        assert result.returncode != 0

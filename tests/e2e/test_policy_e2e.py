"""E2E tests for Authorization API policy templates."""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.e2e
def test_template_create_lifecycle(cli_runner: Any, cli_helper: Any, tmp_path: Path) -> None:
    """Create, retrieve, update, and clean up a workspace-free template."""
    name = f"slcli-e2e-template-{uuid.uuid4().hex}"
    statements = [{"actions": ["testresult:Read"], "resource": ["*"]}]
    statements_file = tmp_path / "statements.json"
    statements_file.write_text(json.dumps(statements), encoding="utf-8")
    result = cli_runner(
        [
            "auth",
            "template",
            "create",
            "--name",
            name,
            "--type",
            "user",
            "--statements-file",
            str(statements_file),
            "--properties",
            "description=slcli E2E test",
            "--format",
            "json",
        ]
    )
    cli_helper.assert_success(result)
    created = cli_helper.get_json_output(result)
    template_id = created["id"]
    try:
        assert created["name"] == name
        assert created["type"] == "user"
        result = cli_runner(["auth", "template", "get", template_id, "--format", "json"])
        cli_helper.assert_success(result)
        fetched = cli_helper.get_json_output(result)
        assert fetched["id"] == template_id
        assert len(fetched["statements"]) == 1
        assert fetched["statements"][0]["actions"] == statements[0]["actions"]
        assert fetched["statements"][0]["resource"] == statements[0]["resource"]
        assert not fetched["statements"][0].get("workspace")
        assert fetched["properties"]["description"] == "slcli E2E test"

        updated_name = f"{name}-updated"
        result = cli_runner(
            ["auth", "template", "update", template_id, "--name", updated_name, "--format", "json"]
        )
        cli_helper.assert_success(result)
        updated = cli_helper.get_json_output(result)
        assert updated["id"] == template_id
        assert updated["name"] == updated_name

        result = cli_runner(["auth", "template", "get", template_id, "--format", "json"])
        cli_helper.assert_success(result)
        fetched_updated = cli_helper.get_json_output(result)
        assert fetched_updated["name"] == updated_name
        assert fetched_updated["type"] == fetched["type"]
        assert fetched_updated["statements"] == fetched["statements"]
        assert fetched_updated["properties"] == fetched["properties"]
    finally:
        result = cli_runner(["auth", "template", "delete", template_id, "--force"])
        cli_helper.assert_success(result)

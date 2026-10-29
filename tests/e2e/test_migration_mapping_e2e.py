"""E2E tests for two-sided workspace discovery and mapping.

Requires a source profile, a destination profile, and an existing non-Default
destination workspace. See ``tests/e2e/README.md``.
"""

import re
import uuid
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result

from slcli.main import cli
from slcli.migration.state import STATE_DIR_ENV
from slcli.migration.workspace_client import WorkspaceClient
from tests.e2e.migration_endpoints import (
    MigrationEndpoints,
    get_or_create_workspace,
    resolve_endpoints,
)

SOURCE_WORKSPACE = "e2e-slcli-migration-source"

pytestmark = [pytest.mark.e2e_migration]


@pytest.fixture(scope="module")
def endpoints() -> MigrationEndpoints:
    """Resolve endpoints and ensure the fixture-owned source workspace exists."""
    resolved = resolve_endpoints()
    get_or_create_workspace(resolved.source, SOURCE_WORKSPACE)
    return resolved


def _migrate(endpoints: MigrationEndpoints, mapping: str, prefect_api_url: str) -> Result:
    return CliRunner().invoke(
        cli,
        [
            "migrate",
            "--source-profile",
            endpoints.source.profile_name,
            "--destination-profile",
            endpoints.destination.profile_name,
            "--workspace-mappings",
            mapping,
            "--prefect-api-url",
            prefect_api_url,
        ],
    )


def _compact(text: str) -> str:
    return re.sub(r"[\s─-╿]", "", click.unstyle(text))


def test_missing_destination_workspace_fails_without_creating_it(
    endpoints: MigrationEndpoints,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping to an absent destination workspace fails before creating a run.

    AB#4088608 (Synchronize workspaces) will create missing destination
    workspaces; update this test when that lands.
    """
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))
    absent = f"e2e-slcli-migration-absent-{uuid.uuid4().hex[:8]}"

    result = _migrate(endpoints, f"{SOURCE_WORKSPACE}:{absent}", test_prefect_server)

    assert result.exit_code == 1, result.output
    # The error panel may be colored and wrapped at any width, so compare without
    # styling, borders, or whitespace.
    assert _compact(f"missing destination workspace: {SOURCE_WORKSPACE} -> {absent}") in _compact(
        result.output
    )
    assert not tmp_path.exists() or not any(tmp_path.iterdir())
    destination_names = {w.name for w in WorkspaceClient(endpoints.destination).query_workspaces()}
    assert absent not in destination_names


def test_mapping_to_existing_destination_workspace(
    endpoints: MigrationEndpoints,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mapping to an existing non-Default destination workspace is resolved and shown."""
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))

    result = _migrate(
        endpoints, f"{SOURCE_WORKSPACE}:{endpoints.destination_workspace}", test_prefect_server
    )

    assert result.exit_code == 0, result.output
    assert f"  {SOURCE_WORKSPACE} -> {endpoints.destination_workspace}\n" in result.output
    [run_directory] = tmp_path.iterdir()
    log = (run_directory / "migration.log").read_text("utf-8")
    assert f"({endpoints.destination_workspace_id})" in log

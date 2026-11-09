"""E2E tests for two-sided workspace discovery and mapping."""

from collections.abc import Generator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from slcli.main import cli
from slcli.migration.state import STATE_DIR_ENV
from slcli.migration.workspace_client import Workspace, WorkspaceClient
from slcli.migration.workspace_task import discover_workspaces_task
from slcli.migration.workspaces import WorkspaceMappingError
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


@pytest.fixture
def disabled_workspace(
    endpoints: MigrationEndpoints,
    request: pytest.FixtureRequest,
) -> Generator[Workspace, None, None]:
    """Reuse a dedicated disabled workspace and leave it disabled after each test."""
    connection = endpoints.source if request.param == "source" else endpoints.destination
    name = f"e2e-slcli-migration-disabled-{request.param}"
    workspace_id = get_or_create_workspace(connection, name)
    url = f"{connection.base_url}/niuser/v1/workspaces/{workspace_id}"
    with connection.create_session() as session:
        try:
            response = session.put(url, json={"name": name, "enabled": False}, timeout=30)
            response.raise_for_status()
            yield Workspace(id=workspace_id, name=name, enabled=False)
        finally:
            response = session.put(url, json={"name": name, "enabled": False}, timeout=30)
            response.raise_for_status()


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


@pytest.mark.parametrize("disabled_workspace", ["destination"], indirect=True)
def test_mapping_rejects_disabled_destination_workspace(
    endpoints: MigrationEndpoints,
    disabled_workspace: Workspace,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The CLI rejects an existing disabled destination without re-enabling it."""
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))

    result = _migrate(
        endpoints, f"{SOURCE_WORKSPACE}:{disabled_workspace.name}", test_prefect_server
    )

    assert result.exit_code == 1, result.output
    assert f"disabled destination workspace: {disabled_workspace.name}" in result.output
    [workspace] = [
        workspace
        for workspace in WorkspaceClient(endpoints.destination).query_workspaces()
        if workspace.id == disabled_workspace.id
    ]
    assert workspace.enabled is False


@pytest.mark.parametrize("disabled_workspace", ["source"], indirect=True)
def test_source_discovery_excludes_disabled_workspace(
    endpoints: MigrationEndpoints,
    disabled_workspace: Workspace,
) -> None:
    """Live source queries include disabled workspaces but discovery excludes them."""
    source_workspaces = list(WorkspaceClient(endpoints.source).query_workspaces())
    assert disabled_workspace in source_workspaces

    discovered = discover_workspaces_task.fn(
        "disabled-source-e2e", endpoints.source.profile_name, None
    )

    assert SOURCE_WORKSPACE in discovered.selected
    assert disabled_workspace.name not in discovered.selected
    assert disabled_workspace.id not in {workspace.id for workspace in discovered.source}
    assert all(workspace.enabled for workspace in discovered.source)

    with pytest.raises(WorkspaceMappingError) as raised:
        discover_workspaces_task.fn(
            "disabled-source-selection-e2e",
            endpoints.source.profile_name,
            [disabled_workspace.name],
        )

    assert raised.value.missing_source == [disabled_workspace.name]

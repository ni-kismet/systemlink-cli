"""Opt-in E2E coverage for persistent destination workspace creation.

See ``tests/e2e/README.md` ("Manually Test Destination Workspace Creation") for details.
"""

import os
import uuid
from pathlib import Path
from typing import Tuple

import pytest
from click.testing import CliRunner

from slcli.main import cli
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.state import STATE_DIR_ENV
from slcli.migration.workspace_client import WorkspaceClient
from slcli.ssl_trust import inject_os_trust
from tests.e2e.migration_endpoints import (
    DESTINATION_PROFILE_ENV,
    SOURCE_PROFILE_ENV,
    get_or_create_workspace,
)

SOURCE_WORKSPACE = "e2e-slcli-migration-source"
WORKSPACE_CREATE_ACK = "DESTINATION_VALINOR_IS_TEMPORARY_AND_DISPOSABLE"

pytestmark = [pytest.mark.e2e_migration_manual]


@pytest.fixture(scope="module")
def migration_connections() -> Tuple[MigrationConnection, MigrationConnection]:
    """Resolve the two profiles only after explicit persistent-write acknowledgement."""
    if os.getenv("SLCLI_E2E_ENABLE_WORKSPACE_CREATION_TESTS") != WORKSPACE_CREATE_ACK:
        pytest.skip("Skipping manual workspace creation test.")
    source_profile = os.getenv(SOURCE_PROFILE_ENV)
    destination_profile = os.getenv(DESTINATION_PROFILE_ENV)
    if not source_profile or not destination_profile:
        pytest.skip(f"configure {SOURCE_PROFILE_ENV} and {DESTINATION_PROFILE_ENV}")

    inject_os_trust()
    source = resolve_migration_connection(source_profile)
    destination = resolve_migration_connection(destination_profile)
    get_or_create_workspace(source, SOURCE_WORKSPACE)
    return source, destination


def test_migration_creates_missing_destination_workspace(
    migration_connections: Tuple[MigrationConnection, MigrationConnection],
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit mapping creates and records a previously absent destination."""
    source, destination = migration_connections
    target_name = f"e2e-slcli-workspace-sync-{uuid.uuid4().hex}"
    destination_client = WorkspaceClient(destination)
    assert target_name not in {
        workspace.name for workspace in destination_client.query_workspaces()
    }
    monkeypatch.setenv(STATE_DIR_ENV, str(tmp_path))

    result = CliRunner().invoke(
        cli,
        [
            "migrate",
            "--source-profile",
            source.profile_name,
            "--destination-profile",
            destination.profile_name,
            "--workspace-mappings",
            f"{SOURCE_WORKSPACE}:{target_name}",
            "--prefect-api-url",
            test_prefect_server,
        ],
    )

    assert result.exit_code == 0, result.output
    [created_workspace] = [
        workspace
        for workspace in destination_client.query_workspaces()
        if workspace.name == target_name
    ]
    [run_directory] = tmp_path.iterdir()
    log = (run_directory / "migration.log").read_text("utf-8")
    assert f"({created_workspace.id})" in log

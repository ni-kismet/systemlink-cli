"""End-to-end tests for the locally managed Prefect server process."""

from pathlib import Path

import psutil
import pytest

from slcli.migration.prefect_server import ManagedPrefectServer


# Tests that start a prefect server are slow (10-30s), so are included with e2e tests
# instead of unit tests.
@pytest.mark.e2e_migration
# Server management relies on a lot of OS interaction, so schedule on the CI's full os matrix.
@pytest.mark.full_os_client_matrix
def test_managed_server_lifecycle(tmp_path: Path) -> None:
    """A real child becomes ready on a dynamic port, persists its database, and stops."""
    server = ManagedPrefectServer(tmp_path)

    with server as api_url:
        process_id = server.process_id
        assert process_id is not None and psutil.pid_exists(process_id)
        assert api_url.startswith("http://127.0.0.1:")

    assert server.database_path.is_file()
    assert not psutil.pid_exists(process_id)

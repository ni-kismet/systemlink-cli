"""Fixtures shared by unit and E2E tests."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest

PREFECT_API_URL_ENV = "SLCLI_TEST_PREFECT_API_URL"


@pytest.fixture(scope="session")
def test_prefect_server(tmp_path_factory: pytest.TempPathFactory) -> Generator[str, None, None]:
    """Provide one Prefect server for the test session.

    Set ``SLCLI_TEST_PREFECT_API_URL`` to reuse an externally managed server
    across pytest invocations.
    """
    existing_api_url = os.getenv(PREFECT_API_URL_ENV)
    if existing_api_url:
        yield existing_api_url
        return

    from slcli.migration.prefect_server import ManagedPrefectServer

    with ManagedPrefectServer(Path(tmp_path_factory.mktemp("prefect-home"))) as api_url:
        yield api_url

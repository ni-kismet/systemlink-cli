"""Live SLS-to-Valinor file transfer tests using fixture-owned files only."""

import json
import secrets
import uuid
from typing import NamedTuple, Sequence
from urllib.parse import quote

import pytest

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.client import FilesClient, SourceFile
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.files.transfer import MIGRATED_SOURCE_ID, split_into_batches, transfer_batch
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping
from tests.e2e.migration_endpoints import (
    MigrationEndpoints,
    get_or_create_workspace,
    resolve_endpoints,
)
from tests.e2e.workspaces import E2EWorkspace
from tests.replay.pytest_plugin import SIDES

# The test seeds a uniquely named file on the source, so it cannot be replayed.
pytestmark = [
    pytest.mark.e2e_migration,
    pytest.mark.file,
    pytest.mark.skipif(
        SIDES["source"].mode() != "live",
        reason="File migration E2E seeds unique source data and needs a live source",
    ),
]

SOURCE_WORKSPACE = E2EWorkspace.FILES_SOURCE.value
DESTINATION_WORKSPACE = E2EWorkspace.DESTINATION.value
OWNER_PROPERTY = "slcliMigrationFileTestOwner"


class TestContext(NamedTuple):
    """Test context for file migration."""

    endpoints: MigrationEndpoints
    source: FilesClient
    destination: FilesClient
    source_workspace: str
    owner: str
    properties: dict[str, str]
    file: SourceFile
    file_data: bytes


def test_file_transfer() -> None:
    """Verify upload and resume avoid re-uploading a file."""
    (
        endpoints,
        source,
        destination,
        source_workspace,
        owner,
        properties,
        file,
        file_data,
    ) = _setup()
    try:
        intended_id = secrets.token_hex(12)
        discovery = FileDiscovery(
            workspaces=(SOURCE_WORKSPACE,),
            files=(
                DiscoveredFile(
                    id=file.id,
                    workspace=SOURCE_WORKSPACE,
                    name=file.name,
                    size_bytes=file.size_bytes,
                    properties=file.properties,
                ),
            ),
            source_to_destination_id_map={file.id: intended_id},
        )
        (batch,) = split_into_batches(discovery)
        destination_workspace = endpoints.destination_workspace_id
        mapping = WorkspaceMapping(
            workspaces=(
                MappedWorkspace(
                    source_name=SOURCE_WORKSPACE,
                    source_id=source_workspace,
                    destination_name=DESTINATION_WORKSPACE,
                    destination_id=destination_workspace,
                ),
            )
        )

        result = transfer_batch(
            source,
            destination,
            batch,
            discovery.source_to_destination_id_map,
            mapping,
        )
        assert result.failures == ()
        assert result.transferred == 1
        _validate_upload(
            destination, destination_workspace, owner, intended_id, file.id, file_data, properties
        )

        resumed = transfer_batch(
            source,
            destination,
            batch,
            discovery.source_to_destination_id_map,
            mapping,
        )
        assert resumed.failures == ()
        assert resumed.transferred == 0
        assert resumed.already_present == 1
        assert [
            item.id for item in _query_owned_files(destination, destination_workspace, owner)
        ] == [intended_id]
    finally:
        source_files = _query_owned_files(source, source_workspace, owner)
        destination_files = _query_owned_files(
            destination, endpoints.destination_workspace_id, owner
        )
        _delete_files(endpoints.destination, [file.id for file in destination_files])
        _delete_files(endpoints.source, [file.id for file in source_files])


def _setup() -> TestContext:
    endpoints = resolve_endpoints()
    if endpoints.source.readonly or endpoints.destination.readonly:
        pytest.skip("File migration E2E requires writable source and destination profiles")
    source_workspace = get_or_create_workspace(endpoints.source, E2EWorkspace.FILES_SOURCE)
    owner = uuid.uuid4().hex
    filename = f"slcli-migration-{owner}.bin"
    properties = {"Name": filename, OWNER_PROPERTY: owner, "Description": "Migration E2E"}
    payload = bytes(range(256)) * 8193
    return TestContext(
        endpoints=endpoints,
        source=FilesClient(endpoints.source),
        destination=FilesClient(endpoints.destination),
        source_workspace=source_workspace,
        owner=owner,
        properties=properties,
        file=_seed_source_with_one_file(
            endpoints.source, source_workspace, filename, payload, properties
        ),
        file_data=payload,
    )


def _seed_source_with_one_file(
    source: MigrationConnection,
    source_workspace: str,
    filename: str,
    payload: bytes,
    properties: dict[str, str],
) -> SourceFile:
    owner = properties[OWNER_PROPERTY]
    with source.create_session() as session:
        response = session.post(
            f"{source.base_url}/nifile/v1/service-groups/Default/upload-files",
            params={"workspace": source_workspace},
            data={"metadata": json.dumps(properties)},
            files={"file": (filename, payload, "application/octet-stream")},
            timeout=30,
        )
        response.raise_for_status()
    seeded = [
        file
        for file in FilesClient(source).query_files(source_workspace)
        if file.properties.get(OWNER_PROPERTY) == owner
    ]
    assert len(seeded) == 1
    return seeded[0]


def _validate_upload(
    destination: FilesClient,
    workspace: str,
    owner: str,
    file_id: str,
    source_file_id: str,
    expected_content: bytes,
    properties: dict[str, str],
) -> None:
    uploaded = _query_owned_files(destination, workspace, owner)
    assert len(uploaded) == 1
    assert uploaded[0].id == file_id
    assert uploaded[0].name == properties["Name"]
    assert uploaded[0].properties[MIGRATED_SOURCE_ID] == source_file_id
    for key, value in properties.items():
        assert uploaded[0].properties[key] == value
    with destination.download_file(file_id) as file_content:
        assert b"".join(file_content.chunks) == expected_content


def _query_owned_files(client: FilesClient, workspace_id: str, owner: str) -> list[SourceFile]:
    return [
        item
        for item in client.query_files(workspace_id)
        if item.properties.get(OWNER_PROPERTY) == owner
    ]


def _delete_files(connection: MigrationConnection, file_ids: Sequence[str]) -> None:
    with connection.create_session() as session:
        for file_id in file_ids:
            response = session.delete(
                f"{connection.base_url}/nifile/v1/service-groups/Default/files/"
                f"{quote(file_id, safe='')}",
                timeout=30,
            )
            response.raise_for_status()

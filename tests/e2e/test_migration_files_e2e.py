"""Live SLS-to-Valinor file transfer tests using fixture-owned files only."""

import json
import secrets
import uuid
from urllib.parse import quote

import pytest

from slcli.migration.files.client import FilesClient
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.files.transfer import (
    MIGRATED_SOURCE_ID,
    split_into_batches,
    transfer_batch,
)
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping
from tests.e2e.migration_endpoints import (
    DESTINATION_WORKSPACE,
    get_or_create_workspace,
    resolve_endpoints,
)

pytestmark = [pytest.mark.e2e_migration, pytest.mark.file]

SOURCE_WORKSPACE = "e2e-slcli-migration-files-source"
OWNER_PROPERTY = "slcliMigrationFileTestOwner"


def test_live_file_transfer_preserves_bytes_metadata_and_resumes() -> None:
    """Verify live uploads under planned IDs and that a resumed batch skips them."""
    endpoints = resolve_endpoints()
    if endpoints.source.readonly or endpoints.destination.readonly:
        pytest.skip("File migration E2E requires writable source and destination profiles")
    source_workspace = get_or_create_workspace(endpoints.source, SOURCE_WORKSPACE)
    owner = uuid.uuid4().hex
    filename = f"slcli-migration-{owner}.bin"
    payload = bytes(range(256)) * 8193
    properties = {"Name": filename, OWNER_PROPERTY: owner, "Description": "Migration E2E"}
    source = FilesClient(endpoints.source)
    destination = FilesClient(endpoints.destination)
    try:
        # Seed SLS directly: unlike Valinor, it need not assign a 24-hex ID.
        with endpoints.source.create_session() as session:
            response = session.post(
                f"{endpoints.source.base_url}/nifile/v1/service-groups/Default/upload-files",
                params={"workspace": source_workspace},
                data={"metadata": json.dumps(properties)},
                files={"file": (filename, payload, "application/octet-stream")},
                timeout=30,
            )
            response.raise_for_status()
        seeded = [
            file
            for file in source.query_files(source_workspace)
            if file.properties.get(OWNER_PROPERTY) == owner
        ]
        assert len(seeded) == 1
        file = seeded[0]
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
        uploaded = [
            item
            for item in destination.query_files(destination_workspace)
            if item.properties.get(OWNER_PROPERTY) == owner
        ]
        assert len(uploaded) == 1
        assert uploaded[0].id == intended_id
        assert uploaded[0].name == filename
        assert uploaded[0].properties[MIGRATED_SOURCE_ID] == file.id
        for key, value in properties.items():
            assert uploaded[0].properties[key] == value
        with destination.download_file(intended_id) as content:
            assert b"".join(content.chunks) == payload

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
            item.id
            for item in destination.query_files(destination_workspace)
            if item.properties.get(OWNER_PROPERTY) == owner
        ] == [intended_id]
    finally:
        # Query before deleting to avoid skip/take pagination moving underneath cleanup.
        for connection, client, workspace_id in (
            (endpoints.destination, destination, endpoints.destination_workspace_id),
            (endpoints.source, source, source_workspace),
        ):
            owned = [
                item.id
                for item in client.query_files(workspace_id)
                if item.properties.get(OWNER_PROPERTY) == owner
            ]
            with connection.create_session() as session:
                for file_id in owned:
                    response = session.delete(
                        f"{connection.base_url}/nifile/v1/service-groups/Default/files/"
                        f"{quote(file_id, safe='')}",
                        timeout=30,
                    )
                    response.raise_for_status()

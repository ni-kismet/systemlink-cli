"""Source feed package listing and download, replayed from a tape with saved package files."""

import hashlib
import os

import pytest

from slcli.migration.connection import resolve_migration_connection
from slcli.ssl_trust import inject_os_trust
from tests.e2e.migration_endpoints import SOURCE_PROFILE_ENV

pytestmark = [pytest.mark.e2e_migration]

# An ni-linux-rt feed with two small .ipk packages on the SLS VM the tape was recorded from.
FEED_ID = "6afe3e981301180055661766"


def test_feed_packages_download_with_listed_size_and_md5() -> None:
    """Every package the feed lists downloads with the size and MD5 the listing reports."""
    profile = os.getenv(SOURCE_PROFILE_ENV)
    if not profile:
        pytest.skip(f"{SOURCE_PROFILE_ENV} is not configured")
    inject_os_trust()
    source = resolve_migration_connection(profile)

    with source.create_session() as session:
        listing = session.get(f"{source.base_url}/nirepo/v1/feeds/{FEED_ID}/packages", timeout=30)
        listing.raise_for_status()
        packages = listing.json()["packages"]
        assert len(packages) == 2

        for package in packages:
            metadata = package["metadata"]
            assert metadata["fileName"].endswith(".ipk")
            download = session.get(f"{source.base_url}{package['fileUri']}", timeout=30)
            download.raise_for_status()
            assert download.content.startswith(b"!<arch>\n")
            assert len(download.content) == metadata["size"]
            assert hashlib.md5(download.content).hexdigest() == metadata["attributes"]["MD5sum"]

"""Source feed package listing and download, replayed from a tape with saved package files.

A module fixture creates a feed in a fixture-owned source workspace, uploads the
small ``.ipk`` packages in ``tests/e2e/packages``, and deletes the feed afterward,
so the tape can be recorded against any SystemLink Server.
"""

import hashlib
import os
import time
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

import pytest
import requests

from slcli.migration.connection import resolve_migration_connection
from slcli.ssl_trust import inject_os_trust
from tests.e2e.migration_endpoints import SOURCE_PROFILE_ENV, get_or_create_workspace
from tests.e2e.workspaces import E2EWorkspace

pytestmark = [pytest.mark.e2e_migration]

FEED_NAME = "e2e-slcli-migration-feeds"
PACKAGES = sorted((Path(__file__).parent / "packages").glob("*.ipk"))
TIMEOUT_SECONDS = 300
POLL_SECONDS = 1.0

T = TypeVar("T")


def _poll(description: str, check: Callable[[], Optional[T]]) -> T:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    while True:
        result = check()
        if result is not None:
            return result
        if time.monotonic() > deadline:
            raise TimeoutError(f"Timed out waiting for {description}")
        time.sleep(POLL_SECONDS)


@dataclass(frozen=True)
class Repo:
    """The SystemLink Server feed API (``/nirepo/v1``) on an authenticated session."""

    base_url: str
    session: requests.Session

    def request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        """Send a request and return its JSON body, or ``{}`` when it has none."""
        response = self.session.request(
            method, f"{self.base_url}/nirepo/v1{path}", timeout=30, **kwargs
        )
        response.raise_for_status()
        return response.json() if response.content else {}

    def wait_for_job(self, job_id: str) -> Dict[str, Any]:
        """Return a job once it succeeds.

        Raises:
            AssertionError: If the job fails.
        """

        def check() -> Optional[Dict[str, Any]]:
            data = self.request("GET", f"/jobs/{job_id}")
            job: Dict[str, Any] = data.get("job", data)
            status = str(job.get("status", "")).upper()
            if status in ("FAILED", "ERROR"):
                raise AssertionError(f"Job {job_id} failed: {job.get('error')}")
            return job if status in ("SUCCEEDED", "SUCCESS", "COMPLETED") else None

        return _poll(f"job {job_id}", check)

    def run(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        """Send a request and return the job it starts once done, or its body if none."""
        data = self.request(method, path, **kwargs)
        job_id = data.get("jobId") or data.get("job", {}).get("id")
        return self.wait_for_job(str(job_id)) if job_id else data

    def packages(self, feed_id: str) -> List[Dict[str, Any]]:
        """Return the packages a feed lists."""
        return list(self.request("GET", f"/feeds/{feed_id}/packages").get("packages", []))


@dataclass(frozen=True)
class SeededFeed:
    """A source feed holding every package in ``PACKAGES``."""

    repo: Repo
    feed_id: str


@pytest.fixture(scope="module")
def seeded() -> Generator[SeededFeed, None, None]:
    """Create the feed and upload the packages, then delete the feed afterward.

    Uploads overwrite, so the fixed packages never accumulate in the package pool.
    """
    profile = os.getenv(SOURCE_PROFILE_ENV)
    if not profile:
        pytest.skip(f"{SOURCE_PROFILE_ENV} is not configured")
    assert PACKAGES, "tests/e2e/packages has no .ipk files"
    inject_os_trust()
    connection = resolve_migration_connection(profile)
    workspace_id = get_or_create_workspace(connection, E2EWorkspace.SOURCE)

    with connection.create_session() as session:
        repo = Repo(connection.base_url, session)
        # A failed earlier run may have left the feed behind. The server ignores the
        # workspace filter, so check each feed's workspace before deleting it.
        for feed in repo.request("GET", "/feeds", params={"workspace": workspace_id}).get(
            "feeds", []
        ):
            if feed.get("feedName") == FEED_NAME and feed.get("workspace") == workspace_id:
                repo.run("DELETE", f"/feeds/{feed['id']}")

        created = repo.request(
            "POST",
            "/feeds",
            json={"feedName": FEED_NAME, "platform": "ni-linux-rt", "workspace": workspace_id},
        )
        job_id = created.get("jobId") or created.get("job", {}).get("id")
        feed_id = str(repo.wait_for_job(str(job_id))["resourceId"] if job_id else created["id"])
        try:
            package_ids = set()
            for package in PACKAGES:
                uploaded = repo.request(
                    "POST",
                    "/upload-packages",
                    params={"shouldOverwrite": "true"},
                    files={
                        "package": (package.name, package.read_bytes(), "application/octet-stream")
                    },
                )
                [upload_job] = uploaded["jobIds"]
                package_ids.add(str(repo.wait_for_job(upload_job)["resourceId"]))
            repo.request(
                "POST",
                f"/feeds/{feed_id}/add-package-references",
                json={"packageReferences": sorted(package_ids)},
            )
            # The reference job is not always queryable, so wait for the listing instead.
            _poll(
                "the feed to list the uploaded packages",
                lambda: package_ids <= {p["id"] for p in repo.packages(feed_id)} or None,
            )
            yield SeededFeed(repo, feed_id)
        finally:
            repo.run("DELETE", f"/feeds/{feed_id}")


def test_feed_packages_download_with_listed_size_and_md5(seeded: SeededFeed) -> None:
    """Every package the feed lists downloads intact, with the size and MD5 the listing reports."""
    expected = {package.name: package.read_bytes() for package in PACKAGES}
    packages = seeded.repo.packages(seeded.feed_id)

    assert sorted(p["metadata"]["fileName"] for p in packages) == sorted(expected)
    for package in packages:
        metadata = package["metadata"]
        download = seeded.repo.session.get(
            f"{seeded.repo.base_url}{package['fileUri']}", timeout=30
        )
        download.raise_for_status()
        assert download.content == expected[metadata["fileName"]]
        assert len(download.content) == metadata["size"]
        md5 = hashlib.md5(download.content, usedforsecurity=False).hexdigest()
        assert md5 == metadata["attributes"]["MD5sum"]

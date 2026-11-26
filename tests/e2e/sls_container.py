"""Prepare a running SystemLink Server container as the live migration E2E source.

Start a server from the published base image first: locally with the compose
file from ``ni-kismet/sls-test``, or in CI with its ``sls-start-server`` action.
Then run::

    poetry run python -m tests.e2e.sls_container --url http://127.0.0.1:8080

The command signs in as the container's web admin, creates an API key, saves it
in an slcli profile, and waits until Test Monitor and Files accept writes in the
source workspaces. The tests seed their own data; run them with
``SLCLI_E2E_SOURCE_MODE=live`` and ``SLCLI_E2E_SOURCE_PROFILE`` set to the profile.

With ``--container`` (default ``$SLS_CONTAINER``, which ``sls-start-server``
exports), it stops waiting as soon as the container records a Windows bugcheck.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, TypeVar

import requests
from click.testing import CliRunner

from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from tests.e2e.migration_endpoints import get_or_create_workspace
from tests.e2e.owned_resource_helpers import MIGRATION_DISCOVERY_OWNER, owner_properties
from tests.e2e.workspaces import E2EWorkspace

DEFAULT_URL = "http://127.0.0.1:8080"
DEFAULT_PROFILE = "migration-source"
RETRY_INTERVAL_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 60
DOCKER_TIMEOUT_SECONDS = 30
# Written by the image's sls-panic-watch after a Windows bugcheck; the guest stays paused.
PANIC_FILE = "${STORAGE:-/storage}/sls-panic.txt"

# Workspaces the tests write to on the source. Disabled workspaces reject writes anyway.
TEST_MONITOR_WORKSPACES = (E2EWorkspace.SOURCE, E2EWorkspace.SOURCE_OTHER)
FILES_WORKSPACE = E2EWorkspace.FILES_SOURCE

T = TypeVar("T")
CrashCheck = Callable[[], Optional[str]]


def retry(
    description: str,
    action: Callable[[], T],
    deadline: float,
    interval: float = RETRY_INTERVAL_SECONDS,
    crashed: Optional[CrashCheck] = None,
) -> T:
    """Call ``action`` until it succeeds or ``deadline`` (monotonic seconds) passes.

    A freshly started server answers before every service knows about new
    workspaces and keys, so any failure is retried until the deadline. After a
    failure, ``crashed`` can end the wait early by returning why the server is gone.
    """
    attempt = 1
    while True:
        try:
            return action()
        except Exception as exc:
            crash = crashed() if crashed else None
            if crash:
                raise RuntimeError(f"Stopped waiting to {description}: {crash}") from exc
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Gave up waiting to {description}: {exc}") from exc
            print(f"Waiting to {description} (attempt {attempt}): {exc}", flush=True)
            attempt += 1
            time.sleep(interval)


def guest_crash(container: str) -> Optional[str]:
    """Return the container's Windows bugcheck record, or ``None`` if it has none.

    Docker errors count as no crash, so the wait falls back to its deadline.
    """
    try:
        result = subprocess.run(
            ["docker", "exec", container, "sh", "-c", f'cat "{PANIC_FILE}" 2>/dev/null'],
            capture_output=True,
            text=True,
            timeout=DOCKER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    record = result.stdout.strip() if result.returncode == 0 else ""
    return f"Windows bugcheck in container {container} ({record})" if record else None


def create_api_key(
    base_url: str, username: str, password: str, session: Optional[requests.Session] = None
) -> str:
    """Create an all-access API key with the web admin's credentials and return its secret.

    Keys reference policies by ID, so the policy is created first.
    """
    http = session or requests.Session()
    http.auth = (username, password)
    name = f"slcli-e2e-{uuid.uuid4().hex[:8]}"
    policy = _post_json(
        http,
        f"{base_url}/niauth/v1/policies",
        {
            "name": name,
            "type": "internal",
            "statements": [{"actions": ["*"], "resource": ["*"], "workspace": "*"}],
        },
    )
    key = _post_json(
        http, f"{base_url}/niauth/v1/keys", {"name": name, "policyIds": [policy["id"]]}
    )
    secret = key.get("secret")
    if not isinstance(secret, str) or not secret:
        raise RuntimeError("The key response did not include a secret")
    return secret


def _post_json(session: requests.Session, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    response = _checked(session.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS))
    return response.json() if response.content else {}


def _checked(response: requests.Response) -> requests.Response:
    """Raise with the response body, which names the cause of SystemLink errors."""
    if not response.ok:
        raise RuntimeError(
            f"{response.request.method} {response.url} returned "
            f"{response.status_code}: {response.text[:500]}"
        )
    return response


def mask_in_github_actions(secret: str) -> None:
    """Hide a secret from GitHub Actions logs; a no-op elsewhere."""
    if os.getenv("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{secret}", flush=True)


def save_profile(profile: str, base_url: str, api_key: str) -> None:
    """Save the key in an slcli profile without making it the current profile.

    Runs ``slcli config add`` in-process so the key never appears in a process
    list, and answers its optional default-workspace prompt with an empty line.
    """
    from slcli.main import cli

    args = ["config", "add", "--profile", profile, "--url", base_url, "--web-url", base_url]
    args += ["--api-key", api_key, "--no-set-current"]
    result = CliRunner().invoke(cli, args, input="\n")
    print(result.output, end="", flush=True)
    if result.exit_code != 0:
        raise RuntimeError(f"slcli config add exited with {result.exit_code}") from (
            result.exception
        )


def probe_test_monitor(connection: MigrationConnection, workspace_id: str) -> None:
    """Create and delete one owned result to prove Test Monitor accepts the workspace.

    The result has no part number, so Test Monitor creates no product for it.
    """
    base = f"{connection.base_url}/nitestmonitor/v2"
    result = {
        "programName": "slcli e2e readiness",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "workspace": workspace_id,
        "properties": owner_properties(MIGRATION_DISCOVERY_OWNER),
    }
    with connection.create_session() as session:
        body = _post_json(session, f"{base}/results", {"results": [result]})
        ids: List[str] = [r["id"] for r in body.get("results", []) if r.get("id")]
        if not ids:
            raise RuntimeError(f"failed={body.get('failed')!r}, error={body.get('error')!r}")
        _post_json(session, f"{base}/delete-results", {"ids": ids, "deleteSteps": True})


def probe_files(connection: MigrationConnection, workspace_id: str) -> None:
    """Upload and delete one owned file to prove Files accepts the workspace.

    Uploads the way the file tests seed the source, without a caller-assigned ID.
    """
    files_url = f"{connection.base_url}/nifile/v1/service-groups/Default"
    with connection.create_session() as session:
        uri = _checked(
            session.post(
                f"{files_url}/upload-files",
                params={"workspace": workspace_id},
                data={"metadata": json.dumps(owner_properties(MIGRATION_DISCOVERY_OWNER))},
                files={"file": ("slcli-e2e-readiness.txt", b"slcli e2e readiness")},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        ).json()["uri"]
        file_id = uri.rstrip("/").rsplit("/", 1)[-1]
        _checked(session.delete(f"{files_url}/files/{file_id}", timeout=REQUEST_TIMEOUT_SECONDS))


def wait_until_writable(
    profile: str, deadline: float, crashed: Optional[CrashCheck] = None
) -> None:
    """Create the source workspaces and wait until the tests' services accept writes."""
    connection = retry(
        f"load profile {profile}",
        lambda: resolve_migration_connection(profile),
        deadline,
        crashed=crashed,
    )
    for workspace in TEST_MONITOR_WORKSPACES:
        _wait_for_workspace(
            connection,
            workspace,
            probe_test_monitor,
            "write Test Monitor results",
            deadline,
            crashed,
        )
    _wait_for_workspace(connection, FILES_WORKSPACE, probe_files, "upload files", deadline, crashed)


def _wait_for_workspace(
    connection: MigrationConnection,
    workspace: E2EWorkspace,
    probe: Callable[[MigrationConnection, str], None],
    activity: str,
    deadline: float,
    crashed: Optional[CrashCheck],
) -> None:
    workspace_id = retry(
        f"create {workspace.value}",
        lambda: get_or_create_workspace(connection, workspace),
        deadline,
        crashed=crashed,
    )
    retry(
        f"{activity} in {workspace.value}",
        lambda: probe(connection, workspace_id),
        deadline,
        crashed=crashed,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Create a key, save the source profile, and wait for the source workspaces."""
    parser = argparse.ArgumentParser(
        prog="python -m tests.e2e.sls_container",
        description="Prepare a running SystemLink Server container as the migration E2E source.",
    )
    parser.add_argument(
        "--url",
        default=os.getenv("SLS_BASE_URL") or DEFAULT_URL,
        help="Server URL (default: $SLS_BASE_URL or %(default)s)",
    )
    parser.add_argument(
        "--profile",
        default=os.getenv("SLCLI_E2E_SOURCE_PROFILE") or DEFAULT_PROFILE,
        help="slcli profile to save (default: $SLCLI_E2E_SOURCE_PROFILE or %(default)s)",
    )
    parser.add_argument("--admin-user", default=os.getenv("SLS_ADMIN_USER") or "admin")
    parser.add_argument(
        "--admin-password",
        default=os.getenv("SLS_ADMIN_PASSWORD") or "test",
        help="Web admin password (default: $SLS_ADMIN_PASSWORD or the images' default)",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=float,
        default=20.0,
        help="Time allowed for the server to accept the key and workspaces (default: 20)",
    )
    parser.add_argument(
        "--container",
        default=os.getenv("SLS_CONTAINER") or "",
        help="Container to check for a Windows bugcheck while waiting (default: $SLS_CONTAINER)",
    )
    args = parser.parse_args(argv)
    base_url = args.url.rstrip("/")
    deadline = time.monotonic() + args.timeout_minutes * 60
    container: str = args.container
    crashed: Optional[CrashCheck] = (lambda: guest_crash(container)) if container else None

    started = time.monotonic()
    secret = retry(
        f"create an API key on {base_url}",
        lambda: create_api_key(base_url, args.admin_user, args.admin_password),
        deadline,
        crashed=crashed,
    )
    mask_in_github_actions(secret)
    retry(
        f"save profile {args.profile}",
        lambda: save_profile(args.profile, base_url, secret),
        deadline,
    )
    wait_until_writable(args.profile, deadline, crashed)
    print(
        f"Source profile '{args.profile}' is ready after {time.monotonic() - started:.0f}s. "
        f"Run the tests with SLCLI_E2E_SOURCE_MODE=live SLCLI_E2E_SOURCE_PROFILE={args.profile}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

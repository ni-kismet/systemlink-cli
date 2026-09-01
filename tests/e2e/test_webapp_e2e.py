"""E2E tests for webapp commands against a live SystemLink instance."""

import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import pytest


def _get_created_webapp_id(output: str) -> Optional[str]:
    """Extract the created webapp ID from publish output."""
    match = re.search(r"Created webapp metadata:\s*(\S+)", output)
    return match.group(1) if match else None


def _find_published_webapp(
    cli_runner: Any,
    cli_helper: Any,
    webapp_name: str,
    workspace: str,
    max_attempts: int = 4,
) -> Optional[Dict[str, Any]]:
    """Find a published webapp with a short retry window for indexing."""
    for attempt in range(max_attempts):
        result = cli_runner(
            [
                "webapp",
                "list",
                "--workspace",
                workspace,
                "--filter",
                webapp_name,
                "--take",
                "10",
                "--format",
                "json",
            ],
            check=False,
        )
        if result.returncode == 0:
            webapps = cli_helper.get_json_output(result)
            found = cli_helper.find_resource_by_name(webapps, webapp_name)
            if found:
                return found

        if attempt < max_attempts - 1:
            time.sleep(0.5 * (2**attempt))

    return None


@pytest.mark.e2e
def test_webapp_publish_and_list(
    cli_runner: Any, cli_helper: Any, e2e_config: Dict[str, Any]
) -> None:
    """Publish a small webapp, verify it appears in list, then clean up."""
    unique = uuid.uuid4().hex[:8]
    webapp_name = f"e2e-webapp-{unique}"

    webapp_id = None
    try:
        # Create a temporary folder with an index.html
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            site = tmpdir_path / "site"
            site.mkdir()
            (site / "index.html").write_text("<html><body>e2e</body></html>")

            # Publish the folder (CLI will pack it)
            workspace = e2e_config.get("workspace", "Default")
            result = cli_runner(
                ["webapp", "publish", str(site), "--name", webapp_name, "--workspace", workspace]
            )
            cli_helper.assert_success(result)
            webapp_id = _get_created_webapp_id(result.stdout)

        found = _find_published_webapp(cli_runner, cli_helper, webapp_name, workspace)
        if found and not webapp_id:
            webapp_id = found.get("id")
        assert found is not None, f"Published webapp '{webapp_name}' not found in list"

    finally:
        # Always attempt to delete the created webapp regardless of test outcome
        if webapp_id:
            del_res = cli_runner(["webapp", "delete", "--id", webapp_id], check=False)
            if del_res.returncode != 0:
                print(
                    "Warning: failed to delete webapp during cleanup",
                    del_res.stdout,
                    del_res.stderr,
                )

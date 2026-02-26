"""E2E tests for webapp commands against a live SystemLink instance."""

import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest


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

        # Verify webapp appears in list (JSON)
        result = cli_runner(["webapp", "list", "--format", "json"])  # returns JSON list of webapps
        cli_helper.assert_success(result)
        webapps = cli_helper.get_json_output(result)

        found = cli_helper.find_resource_by_name(webapps, webapp_name)
        # Capture the ID before asserting so the finally block can always clean up
        if found:
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

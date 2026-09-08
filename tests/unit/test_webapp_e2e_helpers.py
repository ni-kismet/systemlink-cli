"""Tests for webapp E2E synchronization helpers."""

import importlib
import json
import subprocess
from typing import Any, Dict, List, Optional

test_webapp_e2e: Any = importlib.import_module("tests.e2e.test_webapp_e2e")


class WebappHelper:
    """Minimal helper implementation used by lookup tests."""

    def get_json_output(self, result: subprocess.CompletedProcess[str]) -> Any:
        """Parse a command's JSON output."""
        return json.loads(result.stdout)

    def find_resource_by_name(
        self, resources: List[Dict[str, Any]], name: str
    ) -> Optional[Dict[str, Any]]:
        """Find a resource by exact name."""
        return next((resource for resource in resources if resource.get("name") == name), None)


def test_get_created_webapp_id() -> None:
    """Publish output exposes the ID needed for reliable cleanup."""
    output = "✓ Created webapp metadata: webapp-id\n✓ Published webapp content"

    assert test_webapp_e2e._get_created_webapp_id(output) == "webapp-id"


def test_find_published_webapp_retries_targeted_list(monkeypatch: Any) -> None:
    """Lookup filters by workspace and unique name while waiting for indexing."""
    missing = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
    found = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps([{"id": "webapp-id", "name": "e2e-webapp-1234"}]),
        stderr="",
    )
    results = iter([missing, found])
    calls: List[List[str]] = []
    sleeps: List[float] = []

    def run(arguments: List[str], check: bool) -> subprocess.CompletedProcess[str]:
        calls.append(arguments)
        assert check is False
        return next(results)

    monkeypatch.setattr(test_webapp_e2e.time, "sleep", sleeps.append)

    result = test_webapp_e2e._find_published_webapp(
        run, WebappHelper(), "e2e-webapp-1234", "Default"
    )

    assert result == {"id": "webapp-id", "name": "e2e-webapp-1234"}
    assert (
        calls
        == [
            [
                "webapp",
                "list",
                "--workspace",
                "Default",
                "--filter",
                "e2e-webapp-1234",
                "--take",
                "10",
                "--format",
                "json",
            ]
        ]
        * 2
    )
    assert sleeps == [0.5]

"""Unit tests for dashboard CLI commands."""

import json
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner
from slcli.dashboard_click import register_dashboard_commands


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring lookups for deterministic tests."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: (
            "test-key" if key == "SYSTEMLINK_API_KEY" else "https://demo.lifecyclesolutions.ni.com"
        ),
    )


def make_cli() -> click.Group:
    """Create a test CLI with dashboard commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_dashboard_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    """Return Click runner for command tests."""
    return CliRunner()


def test_dashboard_list_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Dashboard list returns JSON payload from search API."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return [
                    {
                        "id": 1,
                        "uid": "system-health",
                        "title": "System Health",
                        "type": "dash-db",
                        "folderTitle": "General",
                        "url": "/d/system-health/system-health",
                    }
                ]

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["dashboard", "list", "-f", "json", "--take", "5"])
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert data[0]["uid"] == "system-health"


def test_dashboard_list_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Dashboard list table output includes dashboard title and uid."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return [
                    {
                        "uid": "system-health",
                        "title": "System Health",
                        "type": "dash-db",
                        "folderTitle": "General",
                        "url": "/d/system-health/system-health",
                    }
                ]

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["dashboard", "list"])
    assert result.exit_code == 0
    assert "System Health" in result.output
    assert "system-health" in result.output


def test_dashboard_export(monkeypatch: Any, runner: CliRunner, tmp_path: Path) -> None:
    """Dashboard export writes dashboard JSON file to output path."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            content = b"{}"

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "dashboard": {"uid": "system-health", "title": "System Health"},
                    "meta": {"folderTitle": "General"},
                }

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    output_path = tmp_path / "system-health.json"

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["dashboard", "export", "system-health", "-o", str(output_path)],
    )
    assert result.exit_code == 0
    assert output_path.exists()

    data = json.loads(output_path.read_text())
    assert data["dashboard"]["uid"] == "system-health"


def test_dashboard_import_dashboard_only_file(
    monkeypatch: Any, runner: CliRunner, tmp_path: Path
) -> None:
    """Dashboard import wraps plain dashboard object for Grafana import API."""
    patch_keyring(monkeypatch)

    captured: dict = {}

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured["url"] = a[0]
        captured["payload"] = kw.get("json")

        class R:
            content = b'{"status":"success","uid":"system-health"}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"status": "success", "uid": "system-health"}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    dashboard_file = tmp_path / "dashboard.json"
    dashboard_file.write_text(json.dumps({"uid": "system-health", "title": "System Health"}))

    cli = make_cli()
    result = runner.invoke(cli, ["dashboard", "import", "-i", str(dashboard_file)])
    assert result.exit_code == 0

    assert captured["url"].endswith("/dashboardhost/api/dashboards/db")
    assert captured["payload"]["dashboard"]["uid"] == "system-health"
    assert captured["payload"]["overwrite"] is False


def test_dashboard_import_full_payload_with_overwrite(
    monkeypatch: Any, runner: CliRunner, tmp_path: Path
) -> None:
    """Dashboard import honors --overwrite for a wrapped dashboard payload."""
    patch_keyring(monkeypatch)

    captured: dict = {}

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured["payload"] = kw.get("json")

        class R:
            content = b'{"status":"success","uid":"system-health"}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"status": "success", "uid": "system-health"}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    dashboard_file = tmp_path / "dashboard-wrapper.json"
    dashboard_file.write_text(
        json.dumps(
            {
                "dashboard": {"uid": "system-health", "title": "System Health"},
                "overwrite": False,
                "message": "old message",
            }
        )
    )

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["dashboard", "import", "-i", str(dashboard_file), "--overwrite"],
    )
    assert result.exit_code == 0
    assert captured["payload"]["overwrite"] is True

"""Unit tests for the hosted webapp smoke-build script."""

from pathlib import Path
from typing import Any, Sequence

import pytest
from scripts import smoke_test_webapp


def test_smoke_test_webapp_runs_generation_install_and_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[tuple[list[str], Path | None]] = []

    class Completed:
        returncode = 0

    def fake_run(command: Sequence[str], cwd: Path | None = None, check: bool = False) -> Any:
        assert check is False
        commands.append((list(command), cwd))
        return Completed()

    monkeypatch.setattr(smoke_test_webapp.subprocess, "run", fake_run)

    workspace_dir = tmp_path / "smoke-check"
    smoke_test_webapp.smoke_test_webapp(workspace_dir, "smoke-check")

    assert commands == [
        (
            [
                smoke_test_webapp.sys.executable,
                "-m",
                "slcli",
                "webapp",
                "new",
                "smoke-check",
                "--directory",
                str(workspace_dir),
                "--skip-install",
            ],
            None,
        ),
        (["npm", "install"], workspace_dir),
        (["npm", "run", "build"], workspace_dir),
    ]


def test_run_command_exits_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Completed:
        returncode = 7

    def fake_run(command: Sequence[str], cwd: Path | None = None, check: bool = False) -> Any:
        del command
        del cwd
        del check
        return Completed()

    monkeypatch.setattr(smoke_test_webapp.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        smoke_test_webapp._run_command(["npm", "run", "build"])

    assert exc_info.value.code == 7

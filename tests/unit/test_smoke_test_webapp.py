"""Unit tests for the hosted webapp smoke-build script."""

from pathlib import Path
from typing import Any, Sequence

import pytest
from scripts import smoke_test_webapp


def test_smoke_test_webapp_runs_generation_install_sbom_and_runtime_localized_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[tuple[list[str], Path | None]] = []
    verified_builds: list[tuple[Path, str]] = []

    class Completed:
        returncode = 0

    def fake_run(command: Sequence[str], cwd: Path | None = None, check: bool = False) -> Any:
        assert check is False
        commands.append((list(command), cwd))
        return Completed()

    def fake_verify_runtime_localized_build(workspace_dir: Path, app_name: str) -> None:
        verified_builds.append((workspace_dir, app_name))

    monkeypatch.setattr(smoke_test_webapp.subprocess, "run", fake_run)
    monkeypatch.setattr(
        smoke_test_webapp,
        "_verify_runtime_localized_build",
        fake_verify_runtime_localized_build,
    )

    workspace_dir = tmp_path / "smoke-check"
    smoke_test_webapp.smoke_test_webapp(workspace_dir, "Smoke Check")

    assert commands == [
        (
            [
                smoke_test_webapp.sys.executable,
                "-m",
                "slcli",
                "webapp",
                "new",
                "Smoke Check",
                "--directory",
                str(workspace_dir),
                "--skip-install",
            ],
            None,
        ),
        (["npm", "install"], workspace_dir),
        (["npm", "run", "i18n:extract"], workspace_dir),
        (["npm", "run", "sbom"], workspace_dir),
        (["npm", "run", "build"], workspace_dir),
    ]
    assert verified_builds == [(workspace_dir, "Smoke Check")]


def test_verify_runtime_localized_build_uses_normalized_angular_output_path(
    tmp_path: Path,
) -> None:
    display_name = "Smoke Check"
    project_name = "smoke-check"
    (tmp_path / "angular.json").write_text(
        '{"projects":{"smoke-check":{"architect":{"build":{"options":{"outputPath":"dist/smoke-check"}}}}}}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "dist" / project_name / "browser"
    output_dir.mkdir(parents=True)
    (output_dir / "index.html").write_text(
        '<html lang="en-US"><head></head><body></body></html>', encoding="utf-8"
    )
    (output_dir / "main.js").write_text(
        "skyline-api-languages; Aper\\xE7u de la localisation; "
        "Vista previa de localizaci\\xF3n; Vorschau der Lokalisierung; "
        "\\u30ED\\u30FC\\u30AB\\u30E9\\u30A4\\u30BA\\u306E\\u30D7\\u30EC\\u30D3\\u30E5\\u30FC; "
        "\\uD604\\uC9C0\\uD654 \\uBBF8\\uB9AC \\uBCF4\\uAE30; "
        "\\u672C\\u5730\\u5316\\u9884\\u89C8",
        encoding="utf-8",
    )

    smoke_test_webapp._verify_runtime_localized_build(tmp_path, display_name)


def test_verify_runtime_localized_build_fails_when_catalog_string_is_missing(
    tmp_path: Path,
) -> None:
    (tmp_path / "angular.json").write_text(
        '{"projects":{"smoke-check":{"architect":{"build":{"options":{"outputPath":"dist/smoke-check"}}}}}}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "dist" / "smoke-check" / "browser"
    output_dir.mkdir(parents=True)
    (output_dir / "index.html").write_text(
        '<html lang="en-US"><head></head><body></body></html>', encoding="utf-8"
    )
    (output_dir / "main.js").write_text("Fecha de ejemplo", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Runtime localization strings are missing"):
        smoke_test_webapp._verify_runtime_localized_build(tmp_path, "smoke-check")


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

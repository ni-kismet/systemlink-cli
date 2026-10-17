"""Generate and build a temporary hosted Angular webapp as a smoke test."""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


def _run_command(command: Sequence[str], cwd: Path | None = None) -> None:
    """Run a command and exit immediately if it fails."""
    result = subprocess.run(list(command), cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _decode_javascript_unicode_escapes(content: str) -> str:
    """Decode Unicode escapes used by optimized JavaScript bundles."""

    def decode(match: re.Match[str]) -> str:
        codepoint = match.group(1)
        if codepoint is None:
            codepoint = match.group(2)
        assert codepoint is not None
        return chr(int(codepoint, 16))

    return re.sub(r"\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4}))", decode, content)


def _verify_runtime_localized_build(workspace_dir: Path, app_name: str) -> None:
    """Verify runtime locale catalogs and hosted HTML were emitted by the build."""
    output_dir = workspace_dir / "dist" / app_name / "browser"
    index_file = output_dir / "index.html"
    javascript_files = list(output_dir.rglob("*.js"))
    if not index_file.is_file() or not javascript_files:
        raise RuntimeError(f"Localized build output is incomplete: {output_dir}")

    index_html = index_file.read_text(encoding="utf-8")
    if '<html lang="en-US"' not in index_html or "<base" in index_html.casefold():
        raise RuntimeError("Localized build has an invalid source language or base element")

    bundle = _decode_javascript_unicode_escapes(
        "\n".join(path.read_text(encoding="utf-8") for path in javascript_files)
    )
    required_messages = (
        "skyline-api-languages",
        "Aperçu de la localisation",
        "Vista previa de localización",
        "Vorschau der Lokalisierung",
        "ローカライズのプレビュー",
        "현지화 미리 보기",
        "本地化预览",
    )
    missing_messages = [message for message in required_messages if message not in bundle]
    if missing_messages:
        raise RuntimeError(
            f"Runtime localization strings are missing from {output_dir}: "
            f"{', '.join(missing_messages)}"
        )


def smoke_test_webapp(workspace_dir: Path, app_name: str) -> None:
    """Generate a hosted Angular webapp and verify localization extraction, SBOM, and builds."""
    _run_command(
        [
            sys.executable,
            "-m",
            "slcli",
            "webapp",
            "new",
            app_name,
            "--directory",
            str(workspace_dir),
            "--skip-install",
        ]
    )
    _run_command(["npm", "install"], cwd=workspace_dir)
    _run_command(["npm", "run", "i18n:extract"], cwd=workspace_dir)
    _run_command(["npm", "run", "sbom"], cwd=workspace_dir)
    _run_command(["npm", "run", "build"], cwd=workspace_dir)
    _verify_runtime_localized_build(workspace_dir, app_name)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the webapp smoke test."""
    parser = argparse.ArgumentParser(
        description=(
            "Generate a hosted Angular webapp and verify npm install, localization extraction, "
            "SBOM generation, and a runtime-localized production build."
        ),
    )
    parser.add_argument(
        "--app-name",
        default="smoke-check",
        help="App name to pass to `slcli webapp new`.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=None,
        help="Optional output directory to keep after the smoke test completes.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the hosted webapp smoke-build flow."""
    args = _parse_args(argv)

    if args.directory is not None:
        smoke_test_webapp(args.directory.resolve(), args.app_name)
        return

    with tempfile.TemporaryDirectory(prefix="slcli-webapp-smoke-") as temp_dir:
        smoke_test_webapp(Path(temp_dir) / args.app_name, args.app_name)


if __name__ == "__main__":
    main()

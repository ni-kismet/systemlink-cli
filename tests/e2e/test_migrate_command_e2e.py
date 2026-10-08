"""Subprocess tests for how the CLI loads the optional migration extra."""

import os
import subprocess
import sys

import pytest

# Each test starts a fresh interpreter, so too slow for unit tests.
pytestmark = pytest.mark.e2e_migration


def _run_python(code: str) -> "subprocess.CompletedProcess[str]":
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "COLUMNS": "200"}
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, encoding="utf-8", env=environment
    )


def test_cli_startup_does_not_import_migration_dependencies() -> None:
    """Normal CLI use does not pay for the optional migration extra."""
    result = _run_python(
        "import sys, slcli.main\n"
        "loaded = {'prefect', 'psutil', 'pydantic', 'slcli.migration'} & set(sys.modules)\n"
        "assert not loaded, loaded"
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("package", ["prefect", "psutil", "pydantic"])
def test_missing_migration_extra_is_actionable(package: str) -> None:
    """Without the migration extra the command explains how to install it."""
    result = _run_python(
        f"import sys; sys.modules[{package!r}] = None\n"
        "from click.testing import CliRunner\n"
        "from slcli.main import cli\n"
        "result = CliRunner().invoke(cli, ['migrate', '--source-profile', 'source'])\n"
        "print(result.output)\n"
        "sys.exit(result.exit_code)"
    )

    assert result.returncode == 1
    assert "systemlink-cli[migration]" in result.stdout


@pytest.mark.parametrize(("missing", "visible"), [("", True), ("prefect", False)])
def test_help_lists_migrate_only_with_migration_extra(missing: str, visible: bool) -> None:
    """The command is a dev feature toggle: hidden from help unless the extra is installed."""
    result = _run_python(
        f"import sys; sys.modules.update({{{missing!r}: None}} if {missing!r} else {{}})\n"
        "from click.testing import CliRunner\n"
        "from slcli.main import cli\n"
        "print(CliRunner().invoke(cli, ['--help']).output)"
    )

    assert result.returncode == 0, result.stderr
    assert ("migrate" in result.stdout) is visible

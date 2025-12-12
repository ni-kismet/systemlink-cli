"""E2E test configuration and shared fixtures for testing against dev tier."""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest


def _load_config_file() -> Dict[str, Any]:
    """Load configuration from file if it exists."""
    config_file = Path("tests/e2e/e2e_config.json")
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    return {}


@pytest.fixture(scope="session")
def e2e_config() -> Dict[str, Any]:
    """Load E2E test configuration from environment or config file.

    Supports both legacy flat config and new multi-platform config.
    """
    file_config = _load_config_file()

    # Check for new multi-platform config structure
    if "sle" in file_config or "sls" in file_config:
        # New format - return the whole config with platform sections
        return {
            "sle": file_config.get("sle", {}),
            "sls": file_config.get("sls", {}),
            "timeout": file_config.get("timeout", 30),
            "cleanup": file_config.get("cleanup", True),
        }

    # Legacy format - convert to new format for compatibility
    config = {
        "base_url": os.getenv("SLCLI_E2E_BASE_URL"),
        "api_key": os.getenv("SLCLI_E2E_API_KEY"),
        "workspace": os.getenv("SLCLI_E2E_WORKSPACE", "Default"),
        "timeout": int(os.getenv("SLCLI_E2E_TIMEOUT", "30")),
        "cleanup": os.getenv("SLCLI_E2E_CLEANUP", "true").lower() == "true",
    }

    # Load from config file if environment variables not set
    if not all([config["base_url"], config["api_key"]]):
        for key, value in file_config.items():
            if not config.get(key):
                config[key] = value

    return config


def _is_sle_url(base_url: str) -> bool:
    """Check if a URL matches SLE (SystemLink Enterprise) patterns.

    Uses the same patterns as platform.py for consistency.
    Only specific URL patterns are SLE - not all systemlink.io subdomains.
    """
    url_lower = base_url.lower()
    sle_patterns = [
        "api.systemlink.io",  # SLE production
        "-api.lifecyclesolutions.ni.com",  # SLE dev/demo with -api suffix
        "dev-api.lifecyclesolutions",
        "demo-api.lifecyclesolutions",
    ]
    return any(pattern in url_lower for pattern in sle_patterns)


@pytest.fixture(scope="session")
def sle_config(e2e_config: Dict[str, Any]) -> Dict[str, Any]:
    """Get SLE-specific configuration."""
    if "sle" in e2e_config:
        return e2e_config["sle"]
    # Legacy format - check if it's an SLE URL using consistent patterns
    base_url = e2e_config.get("base_url", "")
    if _is_sle_url(base_url):
        return e2e_config
    return {}


@pytest.fixture(scope="session")
def sls_config(e2e_config: Dict[str, Any]) -> Dict[str, Any]:
    """Get SLS-specific configuration."""
    if "sls" in e2e_config:
        return e2e_config["sls"]
    # Legacy format - check if it's an SLS URL (anything not matching SLE patterns)
    base_url = e2e_config.get("base_url", "")
    if base_url and not _is_sle_url(base_url):
        return e2e_config
    return {}


@pytest.fixture(scope="session")
def sle_available(sle_config: Dict[str, Any]) -> bool:
    """Check if SLE configuration is available for testing."""
    return bool(sle_config.get("base_url") and sle_config.get("api_key"))


@pytest.fixture(scope="session")
def sls_available(sls_config: Dict[str, Any]) -> bool:
    """Check if SLS configuration is available for testing."""
    return bool(sls_config.get("base_url") and sls_config.get("api_key"))


@pytest.fixture(scope="session")
def require_sle(sle_available: bool) -> None:
    """Skip test if SLE is not configured."""
    if not sle_available:
        pytest.skip("SLE configuration not available")


@pytest.fixture(scope="session")
def require_sls(sls_available: bool) -> None:
    """Skip test if SLS is not configured."""
    if not sls_available:
        pytest.skip("SLS configuration not available")


@pytest.fixture(scope="session", autouse=True)
def setup_e2e_environment(e2e_config: Dict[str, Any]) -> Generator[None, None, None]:
    """Set up environment for E2E tests.

    Note: Individual test classes/functions should use sle_cli_runner or sls_cli_runner
    which configure the environment per-platform.
    """
    # Store original environment
    original_env = {
        "SYSTEMLINK_BASE_URL": os.environ.get("SYSTEMLINK_BASE_URL"),
        "SYSTEMLINK_API_KEY": os.environ.get("SYSTEMLINK_API_KEY"),
    }

    # For multi-platform config, don't set global env vars
    # Tests should use platform-specific runners
    if "sle" not in e2e_config and "sls" not in e2e_config:
        # Legacy single-platform config
        if e2e_config.get("base_url") and e2e_config.get("api_key"):
            os.environ["SYSTEMLINK_BASE_URL"] = e2e_config["base_url"]
            os.environ["SYSTEMLINK_API_KEY"] = e2e_config["api_key"]

    yield

    # Restore original environment
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


def _make_cli_runner(config: Dict[str, Any], timeout: int = 30) -> Any:
    """Create a CLI runner with specific platform configuration."""

    def run_command(
        args: List[str], input_data: Optional[str] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run slcli command with platform-specific environment."""
        cmd = ["poetry", "run", "slcli"] + args

        # Set up environment with platform-specific config
        env = os.environ.copy()
        if config.get("base_url"):
            env["SYSTEMLINK_API_URL"] = config["base_url"]
        if config.get("api_key"):
            env["SYSTEMLINK_API_KEY"] = config["api_key"]
        # Use explicit platform if specified in config (most reliable method)
        if config.get("platform"):
            env["SYSTEMLINK_PLATFORM"] = config["platform"]

        result = subprocess.run(
            cmd,
            input=input_data,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=env,
        )

        if check and result.returncode != 0:
            pytest.fail(
                f"Command failed: {' '.join(cmd)}\n"
                f"Return code: {result.returncode}\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}"
            )

        return result

    return run_command


@pytest.fixture
def cli_runner(e2e_config: Dict[str, Any]) -> Any:
    """CLI runner for executing slcli commands.

    Prefer the SLE config when available, otherwise fall back to SLS, and
    finally the bare environment. This keeps legacy single-config runs working
    while enabling multi-platform configs to still have a sensible default
    runner for tests that do not opt into a platform-specific fixture.
    """
    timeout = e2e_config.get("timeout", 30)

    # Prefer SLE when configured
    if (
        "sle" in e2e_config
        and e2e_config["sle"].get("base_url")
        and e2e_config["sle"].get("api_key")
    ):
        config = {**e2e_config["sle"], "platform": "SLE"}
        return _make_cli_runner(config, timeout)

    # Fall back to SLS when configured
    if (
        "sls" in e2e_config
        and e2e_config["sls"].get("base_url")
        and e2e_config["sls"].get("api_key")
    ):
        config = {**e2e_config["sls"], "platform": "SLS"}
        return _make_cli_runner(config, timeout)

    # Legacy / no config: use current environment
    return _make_cli_runner({})


@pytest.fixture
def sle_cli_runner(sle_config: Dict[str, Any], e2e_config: Dict[str, Any]) -> Any:
    """CLI runner configured for SystemLink Enterprise."""
    timeout = e2e_config.get("timeout", 30)
    # Ensure platform is explicitly set for SLE
    config = {**sle_config, "platform": "SLE"}
    return _make_cli_runner(config, timeout)


@pytest.fixture
def sls_cli_runner(sls_config: Dict[str, Any], e2e_config: Dict[str, Any]) -> Any:
    """CLI runner configured for SystemLink Server."""
    timeout = e2e_config.get("timeout", 30)
    # Ensure platform is explicitly set for SLS
    config = {**sls_config, "platform": "SLS"}
    return _make_cli_runner(config, timeout)


@pytest.fixture
def configured_workspace(e2e_config: Dict[str, Any]) -> str:
    """Return the configured workspace name for E2E tests.

    Returns the workspace from 'sle' section if using multi-platform config,
    otherwise from the top-level config. Defaults to 'Default' if not configured.
    Note: For SLS-specific tests, use 'sls_workspace' fixture instead.
    """
    # Support both new and legacy config formats
    if "sle" in e2e_config:
        return e2e_config["sle"].get("workspace", "Default")
    return e2e_config.get("workspace", "Default")


@pytest.fixture
def sle_workspace(sle_config: Dict[str, Any]) -> str:
    """Return the SLE workspace name."""
    return sle_config.get("workspace", "Default")


@pytest.fixture
def sls_workspace(sls_config: Dict[str, Any]) -> str:
    """Return the SLS workspace name."""
    return sls_config.get("workspace", "Default")


@pytest.fixture
def sle_test_notebook_id(sle_config: Dict[str, Any]) -> Optional[str]:
    """Return the SLE test notebook ID."""
    return sle_config.get("test_notebook_id")


@pytest.fixture
def sls_test_notebook_path(sls_config: Dict[str, Any]) -> Optional[str]:
    """Return the SLS test notebook path."""
    return sls_config.get("test_notebook_path")


@pytest.fixture
def temp_workspace(cli_runner: Any) -> Generator[str, None, None]:
    """Create a temporary workspace for testing."""
    workspace_name = f"e2e-test-{uuid.uuid4().hex[:8]}"

    # Create workspace
    result = cli_runner(["workspace", "create", "--name", workspace_name])
    assert result.returncode == 0

    yield workspace_name

    # Cleanup workspace
    try:
        cli_runner(["workspace", "delete", "--name", workspace_name], check=False)
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture
def temp_file() -> Generator[str, None, None]:
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        yield f.name

    # Cleanup
    try:
        os.unlink(f.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def sample_notebook_content() -> str:
    """Sample Jupyter notebook content for testing."""
    return json.dumps(
        {
            "cells": [
                {
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": ["# E2E Test Notebook\n", "This is a test notebook for E2E testing."],
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": ["print('Hello from E2E test!')"],
                },
            ],
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                "language_info": {"name": "python", "version": "3.11.0"},
            },
            "nbformat": 4,
            "nbformat_minor": 4,
        }
    )


@pytest.fixture
def sample_dff_config() -> Dict[str, Any]:
    """Sample DFF configuration for testing."""
    unique_id = uuid.uuid4().hex[:8]
    return {
        "configurations": [
            {
                "name": f"E2E Test Config {unique_id}",
                "key": f"e2e-test-config-{unique_id}",
                "workspace": "",  # Will be set by test
                "resourceType": "workorder:workorder",
                "views": [
                    {
                        "key": f"view-{unique_id}",
                        "displayText": "Test View",
                        "groups": [f"group-{unique_id}"],
                    }
                ],
            }
        ],
        "groups": [
            {
                "key": f"group-{unique_id}",
                "workspace": "",  # Will be set by test
                "displayText": "Test Group",
                "fields": [f"field-{unique_id}"],
            }
        ],
        "fields": [
            {
                "key": f"field-{unique_id}",
                "workspace": "",  # Will be set by test
                "displayText": "Test Field",
                "type": "Text",
                "mandatory": False,
            }
        ],
    }


class CLITestHelper:
    """Helper class for common CLI test operations."""

    def __init__(self, cli_runner: Any) -> None:
        """Initialize CLI test helper with runner."""
        self.cli_runner = cli_runner

    def assert_success(
        self, result: subprocess.CompletedProcess, expected_output: Optional[str] = None
    ) -> None:
        """Assert command succeeded and optionally check output."""
        assert (
            result.returncode == 0
        ), f"Command failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        if expected_output:
            assert expected_output in result.stdout

    def assert_failure(
        self, result: subprocess.CompletedProcess, expected_error: Optional[str] = None
    ) -> None:
        """Assert command failed and optionally check error message."""
        assert (
            result.returncode != 0
        ), f"Expected command to fail but it succeeded:\nSTDOUT: {result.stdout}"
        if expected_error:
            assert expected_error in result.stderr or expected_error in result.stdout

    def get_json_output(self, result: subprocess.CompletedProcess) -> Any:
        """Parse JSON output from command result."""
        self.assert_success(result)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Failed to parse JSON output: {e}\nOutput: {result.stdout}")

    def find_resource_by_name(self, resources: List[Dict], name: str) -> Optional[Dict]:
        """Find a resource by name in a list of resources."""
        return next((r for r in resources if r.get("name") == name), None)


@pytest.fixture
def cli_helper(cli_runner: Any) -> CLITestHelper:
    """Helper for common CLI test operations."""
    return CLITestHelper(cli_runner)


@pytest.fixture
def sle_cli_helper(sle_cli_runner: Any) -> CLITestHelper:
    """Helper for SLE-specific CLI test operations."""
    return CLITestHelper(sle_cli_runner)


@pytest.fixture
def sls_cli_helper(sls_cli_runner: Any) -> CLITestHelper:
    """Helper for SLS-specific CLI test operations."""
    return CLITestHelper(sls_cli_runner)


# Test markers
def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "notebook: mark test as notebook-related")
    config.addinivalue_line("markers", "dff: mark test as dynamic form fields related")
    config.addinivalue_line("markers", "workspace: mark test as workspace-related")
    config.addinivalue_line("markers", "user: mark test as user management related")
    config.addinivalue_line("markers", "sls: mark test as SystemLink Server specific")
    config.addinivalue_line("markers", "sle: mark test as SystemLink Enterprise specific")
    config.addinivalue_line("markers", "file: mark test as file service related")

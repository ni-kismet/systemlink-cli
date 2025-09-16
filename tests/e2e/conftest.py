"""E2E test configuration and shared fixtures for testing against dev tier."""

import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest


@pytest.fixture(scope="session")
def e2e_config() -> Dict[str, Any]:
    """Load E2E test configuration from environment or config file."""
    config = {
        "base_url": os.getenv("SLCLI_E2E_BASE_URL"),
        "api_key": os.getenv("SLCLI_E2E_API_KEY"),
        "workspace": os.getenv("SLCLI_E2E_WORKSPACE", "Default"),
        "timeout": int(os.getenv("SLCLI_E2E_TIMEOUT", "30")),
        "cleanup": os.getenv("SLCLI_E2E_CLEANUP", "true").lower() == "true",
    }

    # Load from config file if environment variables not set
    config_file = Path("tests/e2e/e2e_config.json")
    if config_file.exists() and not all([config["base_url"], config["api_key"]]):
        with open(config_file) as f:
            file_config = json.load(f)
            for key, value in file_config.items():
                if not config.get(key):
                    config[key] = value

    # Validate required config
    required_fields = ["base_url", "api_key"]
    missing_fields = [field for field in required_fields if not config.get(field)]
    if missing_fields:
        pytest.skip(f"E2E tests skipped - missing config: {', '.join(missing_fields)}")

    return config


@pytest.fixture(scope="session", autouse=True)
def setup_e2e_environment(e2e_config: Dict[str, Any]) -> Generator[None, None, None]:
    """Set up environment for E2E tests."""
    # Store original environment
    original_env = {
        "SYSTEMLINK_BASE_URL": os.environ.get("SYSTEMLINK_BASE_URL"),
        "SYSTEMLINK_API_KEY": os.environ.get("SYSTEMLINK_API_KEY"),
    }

    # Set test environment
    os.environ["SYSTEMLINK_BASE_URL"] = e2e_config["base_url"]
    os.environ["SYSTEMLINK_API_KEY"] = e2e_config["api_key"]

    yield

    # Restore original environment
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]


@pytest.fixture
def cli_runner() -> Any:
    """CLI runner for executing slcli commands."""

    def run_command(
        args: List[str], input_data: Optional[str] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run slcli command and return result."""
        cmd = ["poetry", "run", "slcli"] + args

        result = subprocess.run(
            cmd,
            input=input_data,
            text=True,
            capture_output=True,
            timeout=30,
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
def configured_workspace(e2e_config: Dict[str, Any]) -> str:
    """Return the configured workspace name for E2E tests."""
    return e2e_config["workspace"]


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
@pytest.fixture
def cli_helper(cli_runner: Any) -> CLITestHelper:
    """Helper for common CLI test operations."""
    return CLITestHelper(cli_runner)


# Test markers
def pytest_configure(config: Any) -> None:
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "notebook: mark test as notebook-related")
    config.addinivalue_line("markers", "dff: mark test as dynamic form fields related")
    config.addinivalue_line("markers", "workspace: mark test as workspace-related")
    config.addinivalue_line("markers", "user: mark test as user management related")

"""E2E Test runner and utilities."""

import os
import sys
from pathlib import Path

import pytest


def run_e2e_tests() -> int:
    """Run E2E tests with proper configuration."""
    # Check for required environment variables
    required_env = ["SLCLI_E2E_BASE_URL", "SLCLI_E2E_API_KEY"]
    missing_env = [var for var in required_env if not os.getenv(var)]
    config_file = Path(__file__).resolve().with_name("e2e_config.json")

    if missing_env and not config_file.is_file():
        print("❌ Missing required environment variables for E2E tests:")
        for var in missing_env:
            print(f"  - {var}")
        print("\nSet these environment variables or create tests/e2e/e2e_config.json")
        print("See tests/e2e/e2e_config.json.template for format")
        sys.exit(1)

    # Run E2E tests
    pytest_args = ["tests/e2e/", "-v", "--tb=short", "-m", "e2e", "--disable-warnings"]

    return pytest.main(pytest_args)


if __name__ == "__main__":
    run_e2e_tests()

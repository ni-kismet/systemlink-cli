"""E2E Test runner and utilities."""

import os
import sys

import pytest


def run_e2e_tests() -> int:
    """Run E2E tests with proper configuration."""
    # Check for required environment variables
    required_env = ["SLCLI_E2E_BASE_URL", "SLCLI_E2E_API_KEY"]
    missing_env = [var for var in required_env if not os.getenv(var)]

    if missing_env:
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

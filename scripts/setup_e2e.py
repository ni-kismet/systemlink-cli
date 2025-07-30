#!/usr/bin/env python3
"""Setup script for E2E testing environment."""

import json
import os
import sys
from pathlib import Path


def setup_e2e_environment():
    """Interactive setup for E2E testing environment."""
    print("🔧 SystemLink CLI E2E Testing Setup")
    print("=" * 50)

    # Check if config file already exists
    config_file = Path("tests/e2e/e2e_config.json")
    if config_file.exists():
        print(f"⚠️  Configuration file already exists: {config_file}")
        overwrite = input("Do you want to overwrite it? (y/N): ").lower().strip()
        if overwrite != "y":
            print("Setup cancelled.")
            return

    print("\nPlease provide your SystemLink dev environment details:")

    # Collect configuration
    config = {}

    # Base URL
    while True:
        base_url = input(
            "\n🌐 SystemLink base URL (e.g., https://dev-systemlink.example.com): "
        ).strip()
        if base_url.startswith(("http://", "https://")):
            config["base_url"] = base_url.rstrip("/")
            break
        print("❌ Please enter a valid URL starting with http:// or https://")

    # API Key
    while True:
        api_key = input("\n� API Key: ").strip()
        if api_key:
            config["api_key"] = api_key
            break
        print("❌ API Key cannot be empty")

    # Workspace (optional)
    workspace = input("\n🏢 Test workspace (default: Default): ").strip()
    config["workspace"] = workspace or "Default"

    # Timeout (optional)
    timeout_input = input("\n⏱️  Timeout in seconds (default: 30): ").strip()
    try:
        config["timeout"] = int(timeout_input) if timeout_input else 30
    except ValueError:
        config["timeout"] = 30

    # Cleanup (optional)
    cleanup_input = input("\n🧹 Auto-cleanup test data? (Y/n): ").lower().strip()
    config["cleanup"] = cleanup_input != "n"

    # Save configuration
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Configuration saved to {config_file}")

    # Add to gitignore
    gitignore_file = Path(".gitignore")
    gitignore_entry = "tests/e2e/e2e_config.json"

    if gitignore_file.exists():
        with open(gitignore_file, "r") as f:
            gitignore_content = f.read()

        if gitignore_entry not in gitignore_content:
            with open(gitignore_file, "a") as f:
                f.write(f"\n# E2E test configuration\n{gitignore_entry}\n")
            print(f"✅ Added {gitignore_entry} to .gitignore")

    # Test the configuration
    print("\n🧪 Testing configuration...")

    # Set environment variables temporarily
    original_env = {}
    test_env_vars = {
        "SYSTEMLINK_BASE_URL": config["base_url"],
        "SYSTEMLINK_API_KEY": config["api_key"],
    }

    for key, value in test_env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        # Test basic CLI functionality
        import subprocess

        result = subprocess.run(
            ["poetry", "run", "slcli", "--version"], capture_output=True, text=True, timeout=10
        )

        if result.returncode == 0:
            print(f"✅ CLI version: {result.stdout.strip()}")
        else:
            print(f"❌ CLI test failed: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("⚠️  CLI test timed out - may indicate environment issues")
    except Exception as e:
        print(f"⚠️  CLI test error: {e}")
    finally:
        # Restore original environment
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

    print("\n🎉 E2E testing environment setup complete!")
    print("\nNext steps:")
    print("1. Verify your test user has appropriate permissions")
    print("2. Run E2E tests: python tests/e2e/run_e2e.py")
    print("3. Or run specific tests: poetry run pytest tests/e2e/test_notebook_e2e.py -m e2e -v")
    print(f"\nConfiguration file: {config_file}")
    print("⚠️  Keep your credentials secure and don't commit the config file!")


if __name__ == "__main__":
    try:
        setup_e2e_environment()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)

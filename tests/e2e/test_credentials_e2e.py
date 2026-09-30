"""Opt-in native credential lifecycle tests with isolated profile configurations."""

import json
import os
import platform
import secrets
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.getenv("SLCLI_E2E_NATIVE_CREDENTIALS") != "1",
        reason="Set SLCLI_E2E_NATIVE_CREDENTIALS=1 to enable real native-store access.",
    ),
    pytest.mark.skipif(
        platform.system() not in {"Darwin", "Windows", "Linux"},
        reason="No supported native credential backend on this OS.",
    ),
]


def _isolated_environment(config_file: Path) -> dict[str, str]:
    """Build a subprocess environment with no authentication or profile overrides."""
    env = os.environ.copy()
    for name in (
        "SLCLI_PROFILE",
        "SLCLI_API_KEY",
        "SYSTEMLINK_API_KEY",
        "SLCLI_API_URL",
        "SYSTEMLINK_API_URL",
        "SYSTEMLINK_BASE_URL",
        "SLCLI_WEB_URL",
        "SYSTEMLINK_WEB_URL",
        "SLCLI_CREDENTIAL_STORE",
        "SLCLI_READONLY",
    ):
        env.pop(name, None)
    env["SLCLI_CONFIG"] = str(config_file)
    return env


def _run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a fresh CLI process without exposing command output on assertion failures."""
    return subprocess.run(
        [sys.executable, "-m", "slcli", *args],
        env=env,
        capture_output=True,
        text=True,
        input="",
        timeout=90,
        check=False,
    )


def _assert_native_item_absent(profile_id: str, credential: str, env: dict[str, str]) -> None:
    """Verify logout removed the native item in a process with an empty credential cache."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from slcli.credentials import get_credential; "
            "assert get_credential(sys.argv[1], sys.argv[2]) is None",
            profile_id,
            credential,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, "The native credential remains after logout."


@pytest.mark.parametrize("auth_mode", ["api-key", "pkce"])
def test_native_secure_read_logout(tmp_path: Path, auth_mode: str) -> None:
    """Secure, read, and remove API-key and PKCE secrets using the actual OS backend."""
    config_file = tmp_path / "config.json"
    env = _isolated_environment(config_file)
    name = f"slcli-e2e-{uuid.uuid4()}"
    secret = secrets.token_urlsafe(32)
    credential = "pkce" if auth_mode == "pkce" else "api-key"
    profile: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "server": "https://example.invalid",
        "credential-store": "file",
        "auth-mode": auth_mode,
    }
    if auth_mode == "pkce":
        profile["pkce-credentials"] = {"access-token": secret, "refresh-token": secret}
    else:
        profile["api-key"] = secret
    config_file.write_text(json.dumps({"current-profile": name, "profiles": {name: profile}}))
    try:
        secured = _run_cli(["config", "secure"], env)
        assert secured.returncode == 0, "Native secure migration failed; check the OS store setup."
        saved_text = config_file.read_text()
        saved = json.loads(saved_text)["profiles"][name]
        assert saved["credential-store"] == "os"
        assert secret not in saved_text, "A secret remains in the isolated config."
        viewed = _run_cli(["config", "view", "--format", "json", "--show-secrets"], env)
        assert viewed.returncode == 0, "Native credential read failed."
        revealed = json.loads(viewed.stdout)["profiles"][name]
        actual = (
            revealed["pkce-credentials"]["access-token"]
            if auth_mode == "pkce"
            else revealed["api-key"]
        )
        assert actual == secret
        removed = _run_cli(["logout", "--force"], env)
        assert removed.returncode == 0, "Native logout failed."
        _assert_native_item_absent(saved["id"], credential, env)
        assert not json.loads(config_file.read_text()).get("profiles", {})
    finally:
        _run_cli(["logout", "--all", "--force"], env)


def test_native_login_authenticated_command_logout(
    tmp_path: Path, selected_platform_config: Optional[dict[str, Any]]
) -> None:
    """Run login, a live authenticated request, and logout through each OS's native store."""
    server = selected_platform_config
    if not server or not server.get("base_url") or not server.get("api_key"):
        pytest.skip("Live SystemLink E2E server and API key are not configured.")
    config_file = tmp_path / "config.json"
    env = _isolated_environment(config_file)
    name = f"slcli-e2e-{uuid.uuid4()}"
    try:
        login = _run_cli(
            [
                "login",
                "--profile",
                name,
                "--url",
                server["base_url"],
                "--web-url",
                server.get("web_url") or server["base_url"],
                "--api-key",
                server["api_key"],
                "--workspace",
                server.get("workspace") or "Default",
                "--credential-store",
                "os",
            ],
            env,
        )
        assert login.returncode == 0, "Live native-store login failed."
        saved_text = config_file.read_text()
        saved = json.loads(saved_text)["profiles"][name]
        assert (
            saved["credential-store"] == "os"
        ), "Login fell back instead of using the native store."
        assert server["api_key"] not in saved_text, "A secret remains in the isolated config."
        result = _run_cli(["workspace", "list", "--format", "json"], env)
        assert (
            result.returncode == 0
        ), "The native credential did not authenticate the live request."
        assert isinstance(json.loads(result.stdout), list)
        removed = _run_cli(["logout", "--force"], env)
        assert removed.returncode == 0, "Live native-store logout failed."
        _assert_native_item_absent(saved["id"], "api-key", env)
        assert not json.loads(config_file.read_text()).get("profiles", {})
    finally:
        _run_cli(["logout", "--all", "--force"], env)

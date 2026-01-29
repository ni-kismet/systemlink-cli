"""Unit tests for combined keyring config and web URL helper."""

import json
from pathlib import Path
from typing import Any, Dict

import keyring
from pytest import MonkeyPatch

import slcli.utils as utils


def patch_combined_keyring(monkeypatch: MonkeyPatch, combined: Dict[str, Any]) -> None:
    """Helper to patch keyring.get_password to return combined JSON for config."""

    def fake_get_password(service: str, key: str) -> Any:
        if service == "systemlink-cli" and key == "SYSTEMLINK_CONFIG":
            return json.dumps(combined)
        return None

    monkeypatch.setattr(keyring, "get_password", fake_get_password)


def test__get_keyring_config_parses_combined(monkeypatch: MonkeyPatch) -> None:
    combined = {
        "api_url": "https://api.example",
        "api_key": "ABC123",
        "web_url": "https://app.example",
    }
    patch_combined_keyring(monkeypatch, combined)

    cfg = utils._get_keyring_config()
    assert isinstance(cfg, dict)
    assert cfg.get("api_url") == "https://api.example"
    assert cfg.get("api_key") == "ABC123"
    assert cfg.get("web_url") == "https://app.example"


def test_get_web_url_precedence(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    # Disable profiles to test keyring fallback
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

    # Env var should take precedence
    monkeypatch.setenv("SYSTEMLINK_WEB_URL", "https://env.example")
    # even if combined keyring exists
    combined = {"web_url": "https://keyring.example"}
    patch_combined_keyring(monkeypatch, combined)

    val = utils.get_web_url()
    assert val.rstrip("/") == "https://env.example"

    # Remove env and test keyring fallback
    monkeypatch.delenv("SYSTEMLINK_WEB_URL", raising=False)
    val2 = utils.get_web_url()
    assert val2.rstrip("/") == "https://keyring.example"

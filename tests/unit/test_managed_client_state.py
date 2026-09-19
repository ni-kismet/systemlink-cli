"""Unit tests for isolated managed-client state."""

import json
import stat
from pathlib import Path

import pytest

from slcli.managed_client.models import MasterIdentityChangedError, StateError
from slcli.managed_client.state import StateStore


def test_state_store_preserves_identity_and_restricts_files(tmp_path: Path) -> None:
    """A reload keeps the same key and does not persist REST credentials."""
    store = StateStore(tmp_path / "minion")
    first = store.load_or_create_identity("slcli-test-001")
    second = store.load_or_create_identity("slcli-test-001")
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())

    assert first.public_key.public_numbers() == second.public_key.public_numbers()
    assert "api-key" not in metadata
    assert stat.S_IMODE((tmp_path / "minion").stat().st_mode) == 0o700
    assert stat.S_IMODE((tmp_path / "minion" / "minion-key.pem").stat().st_mode) == 0o600


def test_state_store_rejects_different_minion_id(tmp_path: Path) -> None:
    """A state directory cannot be reused for another identity."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")

    with pytest.raises(StateError, match="different minion ID"):
        store.load_or_create_identity("slcli-test-002")


def test_state_store_rejects_master_identity_change(tmp_path: Path) -> None:
    """A changed master identity requires an explicit reset."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    store.record_master_identity("master-a")

    with pytest.raises(MasterIdentityChangedError, match="identity changed"):
        store.record_master_identity("master-b")


def test_state_store_reset_removes_only_managed_files(tmp_path: Path) -> None:
    """Reset clears identity material without deleting unrelated state."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    unrelated = tmp_path / "minion" / "unrelated.txt"
    unrelated.write_text("keep")

    store.reset()

    assert unrelated.exists()
    assert not (tmp_path / "minion" / "metadata.json").exists()
    assert not (tmp_path / "minion" / "minion-key.pem").exists()

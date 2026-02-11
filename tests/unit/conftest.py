"""Unit test configuration - runs before any test collection or imports.

Forces the keyring null backend to prevent macOS Keychain access on CI runners.
Without this, macOS GitHub Actions runners hang for minutes per keyring call
because the Keychain is locked and no user session exists.

Also patches workspace utilities to prevent real HTTP calls during tests.
"""

import keyring
import pytest
from keyring.backends.null import Keyring as NullKeyring

# Force the null backend BEFORE any test or doctest-module collection
# triggers a real keyring call. This is critical for macOS CI where
# the default macOS Keychain backend blocks on a locked keychain.
keyring.set_keyring(NullKeyring())


@pytest.fixture(autouse=True)
def mock_workspace_utils_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent workspace_utils from making real HTTP calls.

    The get_workspace_display_name() function in workspace_utils.py calls
    get_workspace_map() when no workspace_map is provided. This makes real
    HTTP requests that fail/timeout on CI runners without credentials.

    This fixture patches the source of get_workspace_map in workspace_utils
    to prevent network calls in all unit tests.
    """
    monkeypatch.setattr("slcli.workspace_utils.get_workspace_map", lambda: {})

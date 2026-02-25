"""Unit test configuration - runs before any test collection or imports.

Forces the keyring null backend to prevent macOS Keychain access on CI runners.
Without this, macOS GitHub Actions runners hang for minutes per keyring call
because the Keychain is locked and no user session exists.

Also patches network utilities to prevent real HTTP calls during tests.
"""

from typing import Any, Callable, Dict, Optional

import keyring
import pytest
from keyring.backends.null import Keyring as NullKeyring

# Force the null backend BEFORE any test or doctest-module collection
# triggers a real keyring call. This is critical for macOS CI where
# the default macOS Keychain backend blocks on a locked keychain.
keyring.set_keyring(NullKeyring())


class MockResponse:
    """Mock HTTP response for preventing real network calls."""

    def __init__(self, json_data: Optional[Dict[str, Any]] = None, status_code: int = 200) -> None:
        """Initialize mock response.

        Args:
            json_data: JSON data to return from json() method
            status_code: HTTP status code
        """
        self._json_data = json_data or {}
        self.status_code = status_code
        self.text = ""

    def json(self) -> Dict[str, Any]:
        """Return the JSON data."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise an exception if status code indicates an error."""
        pass


@pytest.fixture(autouse=True)
def mock_network_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real HTTP calls from slcli modules during unit tests.

    Many CLI modules call get_workspace_map() and make_api_request() which
    make real HTTP requests. On CI without credentials, these fail/timeout.

    This fixture patches:
    1. slcli.utils.get_workspace_map - the source function
    2. slcli.workspace_utils.get_workspace_map - directly imported copy
    3. All *_click modules that import get_workspace_map
    4. requests.get/post/put/delete as a fallback safety net

    Individual tests can override with their own mocks.
    """
    empty_workspace_map: Callable[[], Dict[str, str]] = lambda: {}

    # Patch the source function in utils
    monkeypatch.setattr("slcli.utils.get_workspace_map", empty_workspace_map)

    # Patch workspace_utils (imports from utils)
    monkeypatch.setattr("slcli.workspace_utils.get_workspace_map", empty_workspace_map)

    # Patch all click modules that import get_workspace_map
    # These need to be patched because they bind the function at import time
    modules_with_workspace_map = [
        "slcli.asset_click",
        "slcli.comment_click",
        "slcli.dff_click",
        "slcli.example_click",
        "slcli.feed_click",
        "slcli.file_click",
        "slcli.function_click",
        "slcli.notebook_click",
        "slcli.system_click",
        "slcli.templates_click",
        "slcli.testmonitor_click",
        "slcli.webapp_click",
        "slcli.workflows_click",
    ]

    for module in modules_with_workspace_map:
        try:
            monkeypatch.setattr(f"{module}.get_workspace_map", empty_workspace_map)
        except AttributeError:
            # Module might not have imported get_workspace_map
            pass

    # Safety net: patch requests module methods to return mock responses
    # This catches any unpatched HTTP calls. Individual tests that need
    # specific responses should override these with their own mocks.
    def mock_requests_method(*args: Any, **kwargs: Any) -> MockResponse:
        """Return empty mock response for any unpatched HTTP call."""
        return MockResponse()

    monkeypatch.setattr("requests.get", mock_requests_method)
    monkeypatch.setattr("requests.post", mock_requests_method)
    monkeypatch.setattr("requests.put", mock_requests_method)
    monkeypatch.setattr("requests.patch", mock_requests_method)
    monkeypatch.setattr("requests.delete", mock_requests_method)

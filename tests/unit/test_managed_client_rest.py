"""Unit tests for REST key approval orchestration."""

from typing import Any

import pytest

from slcli.managed_client.models import ManagedClientError
from slcli.managed_client.rest import ManagedClientRestAdapter


class FakeResponse:
    """Minimal JSON response for the injected REST requester."""

    def __init__(self, value: Any) -> None:
        """Store a decoded response value."""
        self.value = value

    def json(self) -> Any:
        """Return the stored decoded value."""
        return self.value


def test_list_key_states_parses_optional_categories() -> None:
    """Missing categories become empty maps while public keys are preserved."""
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        calls.append((method, url, kwargs))
        return FakeResponse({"systemsPending": {"minion-1": "public-key"}})

    adapter = ManagedClientRestAdapter(base_url="https://example.test", request=request)
    states = adapter.list_key_states()

    assert states.state_for("minion-1") == "pending"
    assert states.approved == {}
    assert calls[0][0:2] == ("GET", "https://example.test/nisysmgmt/v1/get-systems-keys")


def test_approve_and_delete_use_scoped_key_actions() -> None:
    """Approval includes the key and workspace; deletion remains scoped."""
    calls: list[dict[str, Any]] = []

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        calls.append(kwargs["payload"])
        return FakeResponse({})

    adapter = ManagedClientRestAdapter(base_url="https://example.test", request=request)
    adapter.approve_pending_key("minion-1", "public-key", "workspace-1")
    adapter.delete_managed_system("minion-1", "workspace-1")

    assert calls == [
        {
            "keyActions": [
                {
                    "id": "minion-1",
                    "action": "ACCEPT",
                    "key": "public-key",
                    "workspace": "workspace-1",
                }
            ]
        },
        {"keyActions": [{"id": "minion-1", "action": "DELETE", "workspace": "workspace-1"}]},
    ]


def test_invalid_key_state_response_fails_closed() -> None:
    """Malformed control-plane data does not reach lifecycle decisions."""
    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        request=lambda *args, **kwargs: FakeResponse({"systemsPending": ["invalid"]}),
    )

    with pytest.raises(ManagedClientError, match="systemsPending"):
        adapter.list_key_states()

"""Unit tests for REST key approval orchestration."""

from typing import Any

import pytest

from slcli.managed_client.models import ManagedClientError
from slcli.managed_client.rest import ManagedClientRestAdapter


class FakeResponse:
    """Minimal JSON response for the injected REST requester."""

    def __init__(self, value: Any, status_code: int | None = None) -> None:
        """Store a decoded response value."""
        self.value = value
        self.status_code = status_code

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
    """Approval includes the key and deletion verifies the approved key."""
    calls: list[dict[str, Any]] = []

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        if kwargs["payload"] == {"systemIds": ["minion-1"]}:
            return FakeResponse({"systemsApproved": {"minion-1": "public-key"}})
        calls.append(kwargs["payload"])
        return FakeResponse({}, status_code=204)

    adapter = ManagedClientRestAdapter(base_url="https://example.test", request=request)
    adapter.approve_pending_key("minion-1", "public-key", "workspace-1")
    adapter.delete_managed_system("minion-1", "workspace-1", "public-key")

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
        {
            "keyActions": [
                {
                    "id": "minion-1",
                    "action": "DELETE",
                    "key": "public-key",
                    "workspace": "workspace-1",
                }
            ]
        },
    ]


def test_manage_key_raises_matching_partial_action_error() -> None:
    """A successful HTTP response can still report a failed key action."""

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        del method, url
        if kwargs["payload"] == {"systemIds": ["minion-1"]}:
            return FakeResponse({"systemsApproved": {"minion-1": "public-key"}})
        return FakeResponse(
            {
                "error": {
                    "message": "system is in use",
                    "resourceId": "minion-1",
                    "innerErrors": [{"message": "key is currently active"}],
                }
            },
            status_code=200,
        )

    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        request=request,
    )

    with pytest.raises(ManagedClientError, match="system is in use") as error:
        adapter.delete_managed_system("minion-1", "workspace-1", "public-key")
    assert "key is currently active" in str(error.value)


def test_delete_rejects_a_different_approved_key() -> None:
    """Cleanup refuses to delete a system whose approved key does not match."""
    methods: list[str] = []

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        methods.append(method)
        return FakeResponse({"systemsApproved": {"other-minion": "other-key"}})

    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        request=request,
    )

    with pytest.raises(ManagedClientError, match="public key does not match"):
        adapter.delete_managed_system("minion-1", "workspace-1", "public-key")
    assert methods == ["POST"]


def test_delete_rejects_a_pending_key() -> None:
    """Cleanup refuses to delete a system that has not been approved."""
    methods: list[str] = []

    def request(method: str, url: str, **kwargs: Any) -> FakeResponse:
        methods.append(method)
        return FakeResponse({"systemsPending": {"minion-1": "public-key"}})

    adapter = ManagedClientRestAdapter(base_url="https://example.test", request=request)

    with pytest.raises(ManagedClientError, match="public key does not match"):
        adapter.delete_managed_system("minion-1", "workspace-1", "public-key")
    assert methods == ["POST"]


def test_invalid_key_state_response_fails_closed() -> None:
    """Malformed control-plane data does not reach lifecycle decisions."""
    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        request=lambda *args, **kwargs: FakeResponse({"systemsPending": ["invalid"]}),
    )

    with pytest.raises(ManagedClientError, match="systemsPending"):
        adapter.list_key_states()


def test_invalid_json_response_fails_with_typed_error() -> None:
    """A non-JSON control-plane response becomes a managed-client error."""

    class InvalidJsonResponse:
        def json(self) -> Any:
            raise ValueError("not JSON")

    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        request=lambda *args, **kwargs: InvalidJsonResponse(),
    )

    with pytest.raises(ManagedClientError, match="invalid JSON"):
        adapter.list_key_states()

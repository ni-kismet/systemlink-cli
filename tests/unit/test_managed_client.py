"""Integration coverage for the foreground managed-client lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from slcli.managed_client import MinionConfiguration, MinionEvent, TestMinion as ManagedTestMinion
from slcli.managed_client.models import ReconnectLimitExceededError, TransportError
from slcli.managed_client.rest import ManagedClientRestAdapter
from tests.unit.managed_client_fixture import FixtureSaltServer


class JsonResponse:
    """Small JSON response used by the local REST orchestration test."""

    def __init__(self, value: Any) -> None:
        """Store one decoded response value."""
        self.value = value

    def json(self) -> Any:
        """Return the stored response value."""
        return self.value


def test_minion_completes_pending_publish_and_refresh_job_return(tmp_path: Path) -> None:
    """The minion returns the normal multi-function refresh result."""
    server = FixtureSaltServer()
    server.start()
    events: list[MinionEvent] = []
    minion = ManagedTestMinion(
        MinionConfiguration(
            master=f"127.0.0.1:{server.request_port}",
            minion_id="slcli-fixture-001",
            state_dir=tmp_path / "state",
            request_timeout=5,
            reconnect_interval=0.05,
        ),
        on_event=events.append,
    )
    try:
        minion.start()
        assert server.pending.wait(5)
        minion.wait_for_state("pending", timeout=5)
        server.approve.set()
        minion.wait_for_state("connecting_publish", timeout=5)
        minion.wait_for_state("connected", timeout=5)
        server.release_job.set()
        result = server.result.get(timeout=5)
        assert result["return"] == [True, True, None, None, None]
        assert result["retcode"] == [0, 0, 0, 0, 0]
        assert result["success"] == [True, True, True, True, True]
        received = next(event for event in events if event.message == "Received Salt job")
        returned = next(event for event in events if event.message == "Sent Salt job return")
        assert received.details == {
            "jid": "fixture-jid-001",
            "functions": (
                "saltutil.refresh_pillar, nisysmgmt.state_apply, pkg.list_repos, "
                "nisysmgmt.grains_items, pkg.info_installed"
            ),
            "target": "slcli-fixture-001",
        }
        assert returned.details == {
            **received.details,
            "retcode": "[0, 0, 0, 0, 0]",
            "success": "[True, True, True, True, True]",
        }
        assert minion.connected
    finally:
        minion.stop(timeout=5)
        server.close()


def test_minion_rest_approval_orchestration(tmp_path: Path) -> None:
    """REST key actions drive approval while Salt carries the data plane."""
    server = FixtureSaltServer()
    server.start()
    approved = False
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request(method: str, url: str, **kwargs: Any) -> JsonResponse:
        nonlocal approved
        payload = kwargs.get("payload")
        calls.append((method, url, payload))
        if url.endswith("get-systems-keys"):
            if not server.public_keys:
                return JsonResponse({"systemsPending": {}})
            state = "systemsApproved" if approved else "systemsPending"
            return JsonResponse({state: {"slcli-fixture-rest": server.public_keys[0]}})
        assert isinstance(payload, dict)
        actions = payload["keyActions"]
        assert isinstance(actions, list)
        action = actions[0]
        assert isinstance(action, dict)
        if action["action"] == "ACCEPT":
            approved = True
            server.approve.set()
        return JsonResponse({})

    adapter = ManagedClientRestAdapter(
        base_url="https://example.test",
        credential="rest-credential-not-in-state",
        request=request,
    )
    minion = ManagedTestMinion(
        MinionConfiguration(
            master=f"127.0.0.1:{server.request_port}",
            minion_id="slcli-fixture-rest",
            state_dir=tmp_path / "state",
            request_timeout=5,
            reconnect_interval=0.05,
        ),
    )
    try:
        minion.start()
        assert server.pending.wait(5)
        states = adapter.list_key_states([minion.minion_id])
        public_key = states.pending[minion.minion_id]
        adapter.approve_pending_key(
            minion.minion_id,
            public_key,
            "workspace-1",
        )
        adapter.wait_for_key_state(
            minion.minion_id,
            "approved",
            timeout=5,
            poll_interval=0.01,
        )
        minion.wait_for_state("connected", timeout=5)
        server.release_job.set()
        assert server.result.get(timeout=5)["return"] == [True, True, None, None, None]
        adapter.delete_managed_system(minion.minion_id, "workspace-1", public_key)
    finally:
        minion.stop(timeout=5)
        server.close()

    assert calls[-1][2] == {
        "keyActions": [{"id": "slcli-fixture-rest", "action": "DELETE", "workspace": "workspace-1"}]
    }


def test_minion_reconnects_with_the_same_identity(tmp_path: Path) -> None:
    """A publish interruption reconnects and returns the next refresh job."""
    server = FixtureSaltServer(reconnect=True)
    server.start()
    minion = ManagedTestMinion(
        MinionConfiguration(
            master=f"127.0.0.1:{server.request_port}",
            minion_id="slcli-fixture-reconnect",
            state_dir=tmp_path / "state",
            request_timeout=5,
            reconnect_interval=0.05,
        ),
    )
    try:
        minion.start()
        assert server.pending.wait(5)
        minion.wait_for_state("pending", timeout=5)
        server.approve.set()
        minion.wait_for_state("connected", timeout=5)
        server.release_job.set()

        first_result = server.result.get(timeout=5)
        second_result = server.result.get(timeout=5)
        assert server.reconnected.wait(5)
        assert first_result["return"] == [True, True, None, None, None]
        assert second_result["return"] == [True, True, None, None, None]
        assert server.public_keys[0] == server.public_keys[1]
    finally:
        minion.stop(timeout=5)
        server.close()


def test_minion_fails_after_reconnect_limit(tmp_path: Path) -> None:
    """Reconnect attempts stop after the configured limit."""
    minion = ManagedTestMinion(
        MinionConfiguration(
            master="127.0.0.1",
            minion_id="slcli-reconnect-limit",
            state_dir=tmp_path / "state",
            reconnect_interval=0.01,
            max_reconnect_attempts=1,
        )
    )

    minion._record_reconnect(TransportError("connection interrupted"))

    assert minion.phase.value == "RECONNECTING"
    assert minion.events[-1].retry_count == 1
    with pytest.raises(ReconnectLimitExceededError, match="reconnect limit"):
        minion._record_reconnect(TransportError("connection interrupted"))

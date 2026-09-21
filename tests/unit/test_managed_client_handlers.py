"""Unit tests for deterministic managed-client job handlers."""

from pathlib import Path

from slcli.managed_client.handlers import FixtureHandlerRegistry
from slcli.managed_client.state import StateStore


def test_success_handler_returns_stable_payload() -> None:
    """The success fixture has a stable return schema."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {"jid": "20260918-001", "fun": registry.RETURN_SUCCESS},
        "slcli-test-001",
    )

    assert result == {
        "jid": "20260918-001",
        "id": "slcli-test-001",
        "fun": registry.RETURN_SUCCESS,
        "return": {"value": "success"},
        "retcode": 0,
        "success": True,
    }


def test_fixture_handler_returns_configured_payload() -> None:
    """The fixture handler returns data without evaluating it."""
    registry = FixtureHandlerRegistry()
    fixture = {"serial": "fixture-001", "values": [1, 2, 3]}

    result = registry.dispatch(
        {
            "jid": "20260918-002",
            "fun": registry.RETURN_FIXTURE,
            "kwargs": {"payload": fixture},
        },
        "slcli-test-001",
    )

    assert result["return"] == fixture
    assert result["success"] is True


def test_failure_handler_returns_controlled_failure() -> None:
    """A controlled failure is represented as data and does not raise."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {
            "jid": "20260918-003",
            "fun": registry.FAIL,
            "kwargs": {"code": 17, "message": "expected failure"},
        },
        "slcli-test-001",
    )

    assert result["retcode"] == 17
    assert result["success"] is False
    assert result["error"] == "expected failure"


def test_unknown_or_malformed_jobs_never_execute() -> None:
    """Unknown and malformed jobs receive deterministic errors."""
    registry = FixtureHandlerRegistry()

    unknown = registry.dispatch(
        {"jid": "20260918-004", "fun": "cmd.run", "args": ["touch unsafe"]},
        "slcli-test-001",
    )
    malformed = registry.dispatch({"fun": registry.RETURN_SUCCESS}, "slcli-test-001")

    assert unknown["error"] == "unsupported-operation"
    assert unknown["retcode"] == 2
    assert malformed["error"] == "malformed-job"
    assert malformed["retcode"] == 2


def test_systemlink_refresh_job_returns_normal_multi_function_result() -> None:
    """The on-connect refresh matches the observed SystemLink result arrays."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {
            "jid": "refresh-001",
            "fun": [
                registry.REFRESH_PILLAR,
                registry.STATE_APPLY,
                registry.LIST_REPOS,
                registry.GRAINS_ITEMS,
                registry.INFO_INSTALLED,
            ],
            "arg": [
                [],
                [],
                [],
                [],
                [{"__kwarg__": True, "attr": ["version", "arch"]}],
            ],
        },
        "slcli-test-001",
    )

    assert result == {
        "jid": "refresh-001",
        "id": "slcli-test-001",
        "fun": [
            registry.REFRESH_PILLAR,
            registry.STATE_APPLY,
            registry.LIST_REPOS,
            registry.GRAINS_ITEMS,
            registry.INFO_INSTALLED,
        ],
        "return": [True, True, None, None, None],
        "retcode": [0, 0, 0, 0, 0],
        "success": [True, True, True, True, True],
    }


def test_systemlink_restart_job_returns_success() -> None:
    """The SystemLink restart operation receives a successful Salt return."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {"jid": "restart-001", "fun": registry.RESTART},
        "slcli-test-001",
    )

    assert result == {
        "jid": "restart-001",
        "id": "slcli-test-001",
        "fun": registry.RESTART,
        "return": True,
        "retcode": 0,
        "success": True,
    }


def test_systemlink_set_blackout_persists_lock_and_unlock(tmp_path: Path) -> None:
    """The blackout job persists lock state and supports unlocking it."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)

    locked = registry.dispatch(
        {"jid": "lock-001", "fun": registry.SET_BLACKOUT, "arg": []},
        "slcli-test-001",
    )
    assert locked["return"] is True
    assert locked["retcode"] == 0
    assert locked["success"] is True
    assert StateStore(tmp_path / "minion").get_blackout_state() is True

    unlocked = registry.dispatch(
        {"jid": "unlock-001", "fun": registry.SET_BLACKOUT, "arg": [False]},
        "slcli-test-001",
    )
    assert unlocked["return"] is False
    assert unlocked["retcode"] == 0
    assert unlocked["success"] is True
    assert StateStore(tmp_path / "minion").get_blackout_state() is False


def test_systemlink_lock_batch_returns_success_for_each_function(tmp_path: Path) -> None:
    """A lock job can be combined with the normal grains refresh."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)

    result = registry.dispatch(
        {
            "jid": "lock-batch-001",
            "fun": [registry.SET_BLACKOUT, registry.GRAINS_ITEMS],
            "arg": [[], []],
        },
        "slcli-test-001",
    )

    assert result["return"] == [True, None]
    assert result["retcode"] == [0, 0]
    assert result["success"] == [True, True]
    assert StateStore(tmp_path / "minion").get_blackout_state() is True

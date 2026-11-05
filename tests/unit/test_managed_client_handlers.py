"""Unit tests for deterministic managed-client job handlers."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from slcli.managed_client.handlers import FixtureHandlerRegistry
from slcli.managed_client.models import StateError
from slcli.managed_client.state import StateStore

EXPECTED_WINDOWS_GRAINS = {
    "kernel": "Windows",
    "os": "Windows",
    "os_family": "Windows",
    "cpuarch": "AMD64",
    "pid": os.getpid(),
}


def test_systemlink_uninstall_batch_persists_package_removal(tmp_path: Path) -> None:
    """The observed uninstall batch removes only requested mock packages."""
    store = StateStore(tmp_path / "minion")
    store.install_mock_packages({"ni-dcpower": "25.0.0.49431-0+f279", "ni-other": "1.0"})
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {
            "jid": "ui-remove-001",
            "fun": ["pkg.remove", "system.get_reboot_required_witnessed", "pkg.info_installed"],
            "arg": [
                [
                    {
                        "__kwarg__": True,
                        "pkgs": ["ni-dcpower"],
                        "auto_remove_deps": True,
                        "remove_dependencies": True,
                        "test": False,
                    }
                ],
                [],
                [{"__kwarg__": True, "attr": ["version", "arch"]}],
            ],
        },
        "slcli-test-001",
    )
    assert result["retcode"] == [0, 0, 0]
    assert result["success"] == [True, True, True]
    assert result["return"] == [
        {"ni-dcpower": {"old": "25.0.0.49431-0+f279", "new": ""}},
        False,
        {"ni-other": {"version": "1.0", "arch": "all"}},
    ]
    assert StateStore(tmp_path / "minion").get_installed_packages() == {
        "ni-other": {"version": "1.0", "arch": "all"}
    }


def test_mock_package_removal_is_safe_idempotent_and_supports_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removal affects mock inventory only and supports dry runs and repeated requests."""
    store = StateStore(tmp_path / "minion")
    store.install_mock_packages({"ni-one": "1.0", "ni-two": "2.0"})

    def unexpected_command(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Mock removals must never launch an uninstaller.")

    monkeypatch.setattr(StateStore, "_restrict_permissions", lambda *args: None)
    monkeypatch.setattr(subprocess, "run", unexpected_command)
    registry = FixtureHandlerRegistry(state_store=store)
    simulated = registry.dispatch(
        {
            "jid": "remove-dry-run",
            "fun": "pkg.remove",
            "kwargs": {"pkgs": ["ni-one"], "test": True},
        },
        "slcli-test-001",
    )
    assert simulated["return"] == {"ni-one": {"old": "1.0", "new": ""}}
    assert "ni-one" in store.get_installed_packages()
    job = {"jid": "remove-named", "fun": "pkg.remove", "arg": ["ni-one, ni-missing"]}
    removed = registry.dispatch(job, "slcli-test-001")
    assert removed["return"] == {"ni-one": {"old": "1.0", "new": ""}}
    repeated = registry.dispatch(job, "slcli-test-001")
    assert repeated["return"] == {}
    assert repeated["success"] is True
    assert store.get_installed_packages() == {"ni-two": {"version": "2.0", "arch": "all"}}
    removed = registry.dispatch(
        {"jid": "remove-last", "fun": "pkg.remove", "kwargs": {"name": "ni-two"}},
        "slcli-test-001",
    )
    assert removed["success"] is True
    assert StateStore(tmp_path / "minion").get_installed_packages() == {}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"name": ""},
        {"pkgs": []},
        {"pkgs": "ni-one"},
        {"pkgs": ["ni-one", None]},
        {"pkgs": ["ni-one"], "name": "ni-two"},
        {"pkgs": ["ni-one"], "test": "false"},
    ],
)
def test_mock_package_removal_rejects_invalid_requests_atomically(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    """Invalid removal input cannot partially delete tracked packages."""
    store = StateStore(tmp_path / "minion")
    store.install_mock_packages({"ni-one": "1.0"})
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {"jid": "remove-invalid", "fun": "pkg.remove", "kwargs": kwargs}, "slcli-test-001"
    )
    assert result["success"] is False
    assert result["retcode"] == 2
    assert store.get_installed_packages() == {"ni-one": {"version": "1.0", "arch": "all"}}


def test_mock_package_removal_requires_state_store() -> None:
    """Removal cannot acknowledge success without access to mock state."""
    result = FixtureHandlerRegistry().dispatch(
        {"jid": "remove-no-state", "fun": "pkg.remove", "kwargs": {"name": "ni-one"}},
        "slcli-test-001",
    )
    assert result["error"] == "pkg.remove-requires-state-store"
    assert result["success"] is False


def test_mock_package_removal_handles_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unsuccessful state write preserves inventory and fails the removal job."""
    store = StateStore(tmp_path / "minion")
    store.install_mock_packages({"ni-one": "1.0"})

    def fail_write(metadata: dict[str, Any]) -> None:
        raise StateError("unwritable state")

    monkeypatch.setattr(store, "_write_metadata", fail_write)
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {"jid": "remove-write-failure", "fun": "pkg.remove", "kwargs": {"name": "ni-one"}},
        "slcli-test-001",
    )
    assert result["success"] is False
    assert result["error"] == "unable-to-persist-package-state"
    assert store.get_installed_packages() == {"ni-one": {"version": "1.0", "arch": "all"}}


def test_systemlink_install_batch_returns_complete_success(tmp_path: Path) -> None:
    """The UI install batch returns changes, no reboot, and requested inventory."""
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    result = registry.dispatch(
        {
            "jid": "ui-install-001",
            "fun": ["pkg.install", "system.get_reboot_required_witnessed", "pkg.info_installed"],
            "arg": [
                [
                    {
                        "__kwarg__": True,
                        "pkgs": [{"ni-dcpower": "25.0.0.49431-0+f279"}],
                        "refresh": True,
                        "reinstall": False,
                        "install_recommends": True,
                        "restart_if_required": True,
                        "test": False,
                    }
                ],
                [],
                [
                    {
                        "__kwarg__": True,
                        "attr": [
                            "description",
                            "displayname",
                            "displayversion",
                            "group",
                            "packager",
                            "priority",
                            "releasenotes",
                            "url",
                            "uservisible",
                            "version",
                            "wininsttype",
                            "storeproduct",
                            "size",
                            "arch",
                        ],
                    }
                ],
            ],
        },
        "slcli-test-001",
    )
    assert result["retcode"] == [0, 0, 0]
    assert result["success"] == [True, True, True]
    assert result["return"] == [
        {"ni-dcpower": {"old": "", "new": "25.0.0.49431-0+f279"}},
        False,
        {"ni-dcpower": {"version": "25.0.0.49431-0+f279", "arch": "all"}},
    ]


@pytest.mark.parametrize("arguments", [{}, {"arg": [True]}, {"kwargs": {"force": True}}])
def test_mock_reboot_query_never_launches_commands(
    arguments: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reboot queries are deterministic and reject unexpected arguments."""

    def unexpected_command(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Mock reboot queries must never launch a host command.")

    monkeypatch.setattr(subprocess, "run", unexpected_command)
    result = FixtureHandlerRegistry().dispatch(
        {"jid": "reboot-query", "fun": "system.get_reboot_required_witnessed", **arguments},
        "slcli-test-001",
    )
    assert result["success"] is (not arguments)
    assert result["retcode"] == (2 if arguments else 0)
    if not arguments:
        assert result["return"] is False


def test_mock_packages_persist_and_report_inventory(tmp_path: Path) -> None:
    """Mock installs survive registry reloads and report Salt software inventory."""
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    installed = registry.dispatch(
        {
            "jid": "install-001",
            "fun": "pkg.install",
            "arg": [{"__kwarg__": True, "pkgs": [{"ni-test": "1.2"}, "ni-other"]}],
        },
        "slcli-test-001",
    )
    assert installed["success"] is True
    assert installed["return"] == {
        "ni-test": {"old": "", "new": "1.2"},
        "ni-other": {"old": "", "new": "latest"},
    }

    reloaded = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    inventory = reloaded.dispatch(
        {
            "jid": "inventory-001",
            "fun": ["pkg.list_pkgs", "pkg.info_installed"],
            "arg": [[], [{"__kwarg__": True, "attr": ["version", "arch"]}]],
        },
        "slcli-test-001",
    )
    assert inventory["return"] == [
        {"ni-test": "1.2", "ni-other": "latest"},
        {
            "ni-test": {"version": "1.2", "arch": "all"},
            "ni-other": {"version": "latest", "arch": "all"},
        },
    ]
    assert inventory["success"] == [True, True]


def test_mock_package_upgrade_and_repeat_install(tmp_path: Path) -> None:
    """Salt positional names and keyword versions report only actual mock changes."""
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))

    def install(version: str) -> dict[str, Any]:
        return registry.dispatch(
            {
                "jid": "install-upgrade",
                "fun": "pkg.install",
                "arg": ["ni-test", {"__kwarg__": True, "version": version}],
            },
            "slcli-test-001",
        )

    assert install("1.0")["return"] == {"ni-test": {"old": "", "new": "1.0"}}
    assert install("2.0")["return"] == {"ni-test": {"old": "1.0", "new": "2.0"}}
    assert install("2.0")["return"] == {}
    inventory = registry.dispatch(
        {
            "jid": "inventory-filtered",
            "fun": "pkg.info_installed",
            "arg": ["ni-test", {"__kwarg__": True, "attr": ["version"]}],
        },
        "slcli-test-001",
    )
    assert inventory["return"] == {"ni-test": {"version": "2.0"}}
    versions = registry.dispatch(
        {
            "jid": "inventory-versions",
            "fun": "pkg.list_pkgs",
            "kwargs": {"versions_as_list": True},
        },
        "slcli-test-001",
    )
    assert versions["return"] == {"ni-test": ["2.0"]}


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"name": ""},
        {"name": "ni-test", "version": 1},
        {"name": "ni-test", "pkgs": ["ni-other"]},
        {"pkgs": []},
        {"pkgs": "ni-test"},
        {"pkgs": ["ni-valid", {"ni-invalid": None}]},
        {"pkgs": [{"ni-one": "1", "ni-two": "2"}]},
    ],
)
def test_mock_package_install_rejects_invalid_requests_atomically(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    """Invalid installs fail without persisting even the valid package entries."""
    store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=store)
    result = registry.dispatch(
        {"jid": "invalid-install", "fun": "pkg.install", "kwargs": kwargs},
        "slcli-test-001",
    )
    assert result["success"] is False
    assert result["retcode"] == 2
    assert store.get_installed_packages() == {}


def test_mock_package_operations_never_launch_installers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Package jobs execute no host commands, apart from separate state ACL handling."""

    def unexpected_command(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Mock package jobs must never launch a host command.")

    monkeypatch.setattr(StateStore, "_restrict_permissions", lambda *args: None)
    monkeypatch.setattr(subprocess, "run", unexpected_command)
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    result = registry.dispatch(
        {"jid": "safe-install", "fun": "pkg.install", "kwargs": {"name": "ni-test"}},
        "slcli-test-001",
    )
    assert result["success"] is True
    result = registry.dispatch(
        {"jid": "safe-inventory", "fun": "pkg.info_installed"}, "slcli-test-001"
    )
    assert result["return"] == {"ni-test": {"version": "latest", "arch": "all"}}


def test_mock_package_install_requires_state_store() -> None:
    """Installs cannot report success unless their mock inventory can be persisted."""
    result = FixtureHandlerRegistry().dispatch(
        {"jid": "no-state", "fun": "pkg.install", "kwargs": {"name": "ni-test"}},
        "slcli-test-001",
    )
    assert result["error"] == "pkg.install-requires-state-store"
    assert result["success"] is False


@pytest.mark.parametrize("function", ["pkg.install", "pkg.info_installed", "pkg.list_pkgs"])
def test_mock_package_jobs_handle_corrupt_inventory(tmp_path: Path, function: str) -> None:
    """Corrupt package state yields a controlled Salt failure instead of raising."""
    state_dir = tmp_path / "minion"
    state_dir.mkdir()
    (state_dir / "metadata.json").write_text(json.dumps({"installed_packages": []}))
    registry = FixtureHandlerRegistry(state_store=StateStore(state_dir))
    result = registry.dispatch(
        {"jid": "corrupt-state", "fun": function, "kwargs": {"name": "ni-test"}},
        "slcli-test-001",
    )
    assert result["success"] is False
    assert result["retcode"] == 2


def test_mock_package_install_handles_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unwritable state store does not acknowledge a successful mock install."""
    store = StateStore(tmp_path / "minion")

    def fail_write(metadata: dict[str, Any]) -> None:
        raise StateError("unwritable state")

    monkeypatch.setattr(store, "_write_metadata", fail_write)
    registry = FixtureHandlerRegistry(state_store=store)
    result = registry.dispatch(
        {"jid": "write-failure", "fun": "pkg.install", "kwargs": {"name": "ni-test"}},
        "slcli-test-001",
    )
    assert result["error"] == "unable-to-persist-package-state"
    assert result["success"] is False
    assert store.get_installed_packages() == {}


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
        "return": [True, True, {}, {**EXPECTED_WINDOWS_GRAINS, "minion_blackout": False}, None],
        "retcode": [0, 0, 0, 0, 0],
        "success": [True, True, True, True, True],
    }


def test_mock_feed_jobs_persist_and_return_repository_inventory(tmp_path: Path) -> None:
    """The observed mod_repo batch persists feed data without configuring host feeds."""
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    repositories = {
        "ni-example-released": {
            "uri": "https://example.invalid/released",
            "enabled": True,
            "trusted": False,
        },
        "ni-example-critical": {
            "uri": "https://example.invalid/critical",
            "enabled": True,
            "trusted": False,
        },
    }
    result = registry.dispatch(
        {
            "jid": "feeds-001",
            "fun": ["pkg.mod_repo", "pkg.mod_repo", "pkg.list_repos"],
            "arg": [
                [name, {"__kwarg__": True, **properties, "allow_renaming": True}]
                for name, properties in repositories.items()
            ]
            + [[]],
        },
        "slcli-test-001",
    )
    assert result["success"] == [True, True, True]
    expected_inventory = {
        properties["uri"]: [{"name": name, **properties}]
        for name, properties in repositories.items()
    }
    assert result["return"][-1] == expected_inventory
    reloaded = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))
    inventory = reloaded.dispatch({"jid": "feeds-002", "fun": "pkg.list_repos"}, "slcli-test-001")
    assert inventory["return"] == expected_inventory


def test_mock_feed_update_and_rename_never_touch_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mock feeds can be updated and renamed without commands or HTTP requests."""
    import requests

    def unexpected_io(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Mock feed jobs must not configure the host or contact repositories.")

    monkeypatch.setattr(StateStore, "_restrict_permissions", lambda *args: None)
    monkeypatch.setattr(subprocess, "run", unexpected_io)
    monkeypatch.setattr(requests, "get", unexpected_io)
    monkeypatch.setattr(requests, "post", unexpected_io)
    registry = FixtureHandlerRegistry(state_store=StateStore(tmp_path / "minion"))

    def modify(name: str, **kwargs: Any) -> dict[str, Any]:
        return registry.dispatch(
            {"jid": "feed-update", "fun": "pkg.mod_repo", "kwargs": {"name": name, **kwargs}},
            "slcli-test-001",
        )

    assert modify("old-feed", uri="https://example.invalid/feed")["success"] is True
    updated = modify("old-feed", enabled=False, trusted=True)
    assert updated["return"] == {
        "old-feed": {"uri": "https://example.invalid/feed", "enabled": False, "trusted": True}
    }
    assert (
        modify("new-feed", uri="https://example.invalid/feed", allow_renaming=True)["success"]
        is True
    )
    inventory = registry.dispatch(
        {"jid": "feed-inventory", "fun": "pkg.list_repos"}, "slcli-test-001"
    )
    assert inventory["return"] == {
        "https://example.invalid/feed": [
            {
                "name": "new-feed",
                "uri": "https://example.invalid/feed",
                "enabled": True,
                "trusted": False,
            }
        ]
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"name": ""},
        {"name": "feed", "uri": ""},
        {"name": "feed", "uri": 123},
        {"name": "feed", "uri": "https://example.invalid", "enabled": "true"},
        {"name": "feed", "uri": "https://example.invalid", "trusted": 1},
        {"name": "feed", "uri": "https://example.invalid", "allow_renaming": "true"},
    ],
)
def test_mock_feed_rejects_invalid_records_without_writes(
    tmp_path: Path, kwargs: dict[str, Any]
) -> None:
    """Malformed feed requests leave the mock repository inventory unchanged."""
    store = StateStore(tmp_path / "minion")
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {"jid": "feed-invalid", "fun": "pkg.mod_repo", "kwargs": kwargs}, "slcli-test-001"
    )
    assert result["retcode"] == 2
    assert result["success"] is False
    assert store.get_mock_repositories() == {}


def test_mock_feed_requires_state_store() -> None:
    """A feed modification cannot succeed without persistent isolated state."""
    result = FixtureHandlerRegistry().dispatch(
        {
            "jid": "feed-no-state",
            "fun": "pkg.mod_repo",
            "kwargs": {"name": "feed", "uri": "https://example.invalid"},
        },
        "slcli-test-001",
    )
    assert result["error"] == "pkg.mod_repo-requires-state-store"
    assert result["success"] is False


@pytest.mark.parametrize("function", ["pkg.mod_repo", "pkg.list_repos"])
def test_mock_feed_handles_corrupt_inventory(tmp_path: Path, function: str) -> None:
    """Corrupt feed metadata returns a controlled failure rather than raising."""
    state_dir = tmp_path / "minion"
    state_dir.mkdir()
    (state_dir / "metadata.json").write_text(json.dumps({"repositories": {"feed": {}}}))
    result = FixtureHandlerRegistry(state_store=StateStore(state_dir)).dispatch(
        {
            "jid": "feed-corrupt",
            "fun": function,
            "arg": (
                ["feed", {"__kwarg__": True, "uri": "https://example.invalid"}]
                if function == "pkg.mod_repo"
                else []
            ),
        },
        "slcli-test-001",
    )
    assert result["success"] is False
    assert result["retcode"] == 2


def test_mock_feed_handles_write_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed metadata writes do not acknowledge a successful feed modification."""
    store = StateStore(tmp_path / "minion")

    def fail_write(metadata: dict[str, Any]) -> None:
        raise StateError("unwritable state")

    monkeypatch.setattr(store, "_write_metadata", fail_write)
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {
            "jid": "feed-write-failure",
            "fun": "pkg.mod_repo",
            "kwargs": {"name": "feed", "uri": "https://example.invalid"},
        },
        "slcli-test-001",
    )
    assert result["success"] is False
    assert result["error"] == "unable-to-persist-repository-state"
    assert store.get_mock_repositories() == {}


def test_mock_repository_inventory_groups_names_sharing_a_uri(tmp_path: Path) -> None:
    """Feed inventory preserves all names in a list under their shared URI."""
    store = StateStore(tmp_path / "minion")
    uri = "https://example.invalid/shared"
    store.modify_mock_repository("feed-one", {"uri": uri})
    store.modify_mock_repository("feed-two", {"uri": uri, "enabled": False})
    result = FixtureHandlerRegistry(state_store=store).dispatch(
        {"jid": "feeds-grouped", "fun": "pkg.list_repos"}, "slcli-test-001"
    )
    assert result["return"] == {
        uri: [
            {"name": "feed-one", "uri": uri, "enabled": True, "trusted": False},
            {"name": "feed-two", "uri": uri, "enabled": False, "trusted": False},
        ]
    }


def test_mock_repository_inventory_is_an_empty_map() -> None:
    """No configured feeds is represented by a map, not a missing inventory."""
    registry = FixtureHandlerRegistry()
    result = registry.dispatch({"jid": "repos-empty", "fun": registry.LIST_REPOS}, "slcli-test-001")
    assert result["return"] == {}
    assert result["success"] is True
    invalid = registry.dispatch(
        {"jid": "repos-invalid", "fun": registry.LIST_REPOS, "arg": ["unexpected"]},
        "slcli-test-001",
    )
    assert invalid["retcode"] == 2
    assert invalid["success"] is False


@pytest.mark.parametrize("function", ["nisysmgmt.restart", "nisysmgmt.restart_if_required"])
def test_systemlink_restart_job_returns_success(
    function: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SystemLink restart operation receives a successful Salt return."""

    def unexpected_command(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Mock restart jobs must never launch a host command.")

    monkeypatch.setattr(subprocess, "run", unexpected_command)
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {"jid": "restart-001", "fun": function},
        "slcli-test-001",
    )

    assert result == {
        "jid": "restart-001",
        "id": "slcli-test-001",
        "fun": function,
        "return": True,
        "retcode": 0,
        "success": True,
    }


@pytest.mark.parametrize("function", ["nisysmgmt.restart", "nisysmgmt.restart_if_required"])
def test_systemlink_restart_job_accepts_single_function_list_without_args(function: str) -> None:
    """A no-argument single-function Salt job can omit its argument list."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {"jid": "restart-002", "fun": [function]},
        "slcli-test-001",
    )

    assert result == {
        "jid": "restart-002",
        "id": "slcli-test-001",
        "fun": [function],
        "return": [True],
        "retcode": [0],
        "success": [True],
    }


def test_systemlink_restart_if_required_rejects_arguments() -> None:
    """Unexpected restart arguments receive a controlled failure."""
    registry = FixtureHandlerRegistry()
    result = registry.dispatch(
        {"jid": "restart-invalid", "fun": registry.RESTART_IF_REQUIRED, "arg": ["unexpected"]},
        "slcli-test-001",
    )
    assert result["retcode"] == 2
    assert result["success"] is False


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


def test_systemlink_unset_blackout_persists_unlock(tmp_path: Path) -> None:
    """The SystemLink unlock operation clears the persisted blackout state."""
    state_store = StateStore(tmp_path / "minion")
    state_store.record_blackout_state(True)
    registry = FixtureHandlerRegistry(state_store=state_store)

    result = registry.dispatch(
        {
            "jid": "unlock-002",
            "fun": [registry.UNSET_BLACKOUT, registry.GRAINS_ITEMS],
            "arg": [[], []],
        },
        "slcli-test-001",
    )

    assert result["return"] == [False, {**EXPECTED_WINDOWS_GRAINS, "minion_blackout": False}]
    assert result["retcode"] == [0, 0]
    assert result["success"] == [True, True]
    assert StateStore(tmp_path / "minion").get_blackout_state() is False


def test_systemlink_add_asset_accepts_nested_keyword_arguments(tmp_path: Path) -> None:
    """The asset job accepts Salt's nested keyword argument shape."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)

    result = registry.dispatch(
        {
            "jid": "asset-001",
            "fun": "ni_asset.add_asset",
            "arg": [
                [
                    {
                        "__kwarg__": True,
                        "name": "xxc",
                        "model_name": "zxc",
                        "model_number": 0,
                        "vendor_name": "zxc",
                        "vendor_number": 0,
                        "serial_number": "zxc",
                        "bus_type": "USB",
                        "asset_type": "GENERIC",
                        "keywords": [],
                        "properties": {
                            "asset_reserved": "false",
                            "asset_assigned_to": "",
                        },
                        "part_number": "",
                        "firmware_version": "",
                        "hardware_version": "",
                        "supports_external_calibration": None,
                        "is_ni_asset": False,
                        "location": {
                            "minionId": "slcli-test-001",
                            "physicalLocation": "",
                            "parent": "",
                            "slot_number": -1,
                            "state": {"asset_presence": "PRESENT"},
                        },
                        "external_calibration": None,
                    }
                ]
            ],
        },
        "slcli-test-001",
    )

    assert result["retcode"] == 0
    assert result["success"] is True
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())
    assert metadata["asset_records"] == [
        {
            "name": "xxc",
            "identification": {
                "model_name": "zxc",
                "model_number": 0,
                "vendor_name": "zxc",
                "vendor_number": 0,
                "serial_number": "zxc",
            },
        }
    ]


def test_systemlink_add_asset_records_multiple_names(tmp_path: Path) -> None:
    """The asset job records all names from one multi-asset request."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)

    result = registry.dispatch(
        {
            "jid": "asset-002",
            "fun": registry.ADD_ASSET,
            "arg": [
                [
                    {"__kwarg__": True, "name": "asset-one"},
                    {"__kwarg__": True, "name": "asset-two"},
                ]
            ],
        },
        "slcli-test-001",
    )

    assert result["retcode"] == 0
    assert result["success"] is True
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())
    assert [record["name"] for record in metadata["asset_records"]] == [
        "asset-one",
        "asset-two",
    ]


def test_systemlink_remove_asset_removes_matching_asset_record(tmp_path: Path) -> None:
    """The asset removal handler removes the name for the identified asset."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)
    identification = {
        "model_name": "fixture-model",
        "model_number": 0,
        "vendor_name": "fixture-vendor",
        "vendor_number": 0,
        "serial_number": "fixture-serial",
    }
    state_store.record_asset_records([{"name": "fixture-asset", **identification}])

    result = registry.dispatch(
        {
            "jid": "asset-remove-001",
            "fun": registry.REMOVE_ASSET,
            "arg": [
                {
                    "__kwarg__": True,
                    "identification": identification,
                }
            ],
        },
        "slcli-test-001",
    )

    assert result["return"] is True
    assert result["retcode"] == 0
    assert result["success"] is True
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())
    assert metadata["asset_records"] == []


def test_systemlink_refresh_asset_returns_success() -> None:
    """The asset refresh handler accepts a no-argument Salt job."""
    registry = FixtureHandlerRegistry()

    result = registry.dispatch(
        {"jid": "asset-refresh-001", "fun": registry.REFRESH_ASSET},
        "slcli-test-001",
    )

    assert result["return"] is True
    assert result["retcode"] == 0
    assert result["success"] is True


def test_systemlink_remove_asset_batch_returns_success(tmp_path: Path) -> None:
    """A batch of identified asset removals returns one success per asset."""
    state_store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=state_store)
    identification = {
        "model_name": "fixture-model",
        "model_number": 0,
        "vendor_name": "fixture-vendor",
        "vendor_number": 0,
        "serial_number": "fixture-serial",
    }
    state_store.record_asset_records(
        [{"name": f"asset-{index}", **identification} for index in range(3)]
    )

    result = registry.dispatch(
        {
            "jid": "asset-remove-batch-001",
            "fun": [registry.REMOVE_ASSET] * 3,
            "arg": [[{"__kwarg__": True, "identification": identification}]] * 3,
        },
        "slcli-test-001",
    )

    assert result["return"] == [True, True, True]
    assert result["retcode"] == [0, 0, 0]
    assert result["success"] == [True, True, True]
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())
    assert metadata["asset_records"] == []


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

    assert result["return"] == [True, {**EXPECTED_WINDOWS_GRAINS, "minion_blackout": True}]
    assert result["retcode"] == [0, 0]
    assert result["success"] == [True, True]
    assert StateStore(tmp_path / "minion").get_blackout_state() is True

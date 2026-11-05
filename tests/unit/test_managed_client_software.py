"""Tests for mock software dependency transactions."""

import gzip
from pathlib import Path
from typing import Any, Iterator

import pytest
import requests

from slcli.managed_client.handlers import FixtureHandlerRegistry
from slcli.managed_client.software import CatalogPackage, SoftwareResolutionError, load_feed_packages, solve_package_install
from slcli.managed_client.state import StateStore


def test_solver_selects_dependency_upgrade_without_mutating_inventory() -> None:
    """An exact driver install upgrades its runtime and preserves the input snapshot."""
    pytest.importorskip("solv")
    installed = {"runtime": {"version": "1.0", "arch": "all"}}
    catalog = [
        CatalogPackage("runtime", "1.0"),
        CatalogPackage("runtime", "2.0", architecture="windows_all"),
        CatalogPackage("driver", "1.0", depends="runtime (>= 2.0)"),
    ]
    result = solve_package_install({"driver": "1.0"}, installed, catalog)
    assert result["driver"]["version"] == "1.0"
    assert result["runtime"]["version"] == "2.0"
    assert result["runtime"]["arch"] == "windows_all"
    assert installed["runtime"]["version"] == "1.0"
    with pytest.raises(SoftwareResolutionError, match="Unsatisfiable"):
        solve_package_install({"driver": "9.0"}, installed, catalog)


def test_enabled_feed_install_commits_complete_transaction_atomically(tmp_path: Path) -> None:
    """Salt installs persist dependency upgrades and dry runs or failures change nothing."""
    pytest.importorskip("solv")
    store = StateStore(tmp_path / "minion")
    store.install_mock_packages({"runtime": "1.0", "untouched": "4.0"})
    store.modify_mock_repository("feed", {"uri": "https://example.invalid/feed"})
    catalog = [CatalogPackage("runtime", "2.0"), CatalogPackage("driver", "1.0", depends="runtime (>= 2.0)")]

    def load(repositories: Any) -> list[CatalogPackage]:
        return catalog

    registry = FixtureHandlerRegistry(state_store=store, catalog_loader=load)
    job = {
        "jid": "resolved-install", "fun": "pkg.install",
        "kwargs": {"pkgs": [{"driver": "1.0"}], "test": True},
    }
    result = registry.dispatch(job, "mock-system")
    assert result["success"] is True
    assert result["return"] == {
        "driver": {"old": "", "new": "1.0"}, "runtime": {"old": "1.0", "new": "2.0"}
    }
    assert "driver" not in store.get_installed_packages()
    job["kwargs"] = {"pkgs": [{"driver": "9.0"}]}
    result = registry.dispatch(job, "mock-system")
    assert result["error"] == "software-resolution-failed"
    assert store.get_installed_packages()["runtime"]["version"] == "1.0"
    job["kwargs"] = {"pkgs": [{"driver": "1.0"}]}
    result = registry.dispatch(job, "mock-system")
    assert result["success"] is True
    assert StateStore(tmp_path / "minion").get_installed_packages()["runtime"]["version"] == "2.0"
    assert store.get_installed_packages()["untouched"]["version"] == "4.0"
    assert store.get_installed_packages()["driver"]["depends"] == "runtime (>= 2.0)"


def test_solver_selects_latest_and_honors_recommendation_flag() -> None:
    """Unpinned requests select the best version, with optional recommendations."""
    pytest.importorskip("solv")
    catalog = [
        CatalogPackage("driver", "1.0"), CatalogPackage("driver", "2.0", recommends="addon"),
        CatalogPackage("addon", "1.0"),
    ]
    installed = {"driver": {"version": "1.0", "arch": "all"}}
    result = solve_package_install({"driver": "latest"}, installed, catalog, install_recommends=False)
    assert result["driver"]["version"] == "2.0"
    assert "addon" not in result
    result = solve_package_install({"driver": "latest"}, installed, catalog)
    assert result["addon"]["version"] == "1.0"


def test_solver_honors_alternatives_and_conflicts() -> None:
    """Alternative requirements resolve, while installed-package conflicts reject safely."""
    pytest.importorskip("solv")
    catalog = [
        CatalogPackage("driver", "1.0", depends="missing | runtime (>= 2.0)", conflicts="incompatible"),
        CatalogPackage("runtime", "2.0"),
    ]
    assert solve_package_install({"driver": "1.0"}, {}, catalog)["runtime"]["version"] == "2.0"
    with pytest.raises(SoftwareResolutionError, match="Unsatisfiable"):
        solve_package_install({"driver": "1.0"}, {"incompatible": {"version": "1.0", "arch": "all"}}, catalog)


def test_legacy_inventory_uses_feed_dependencies_for_repeat_install() -> None:
    """Existing simple records acquire dependency metadata before solving repeat installs."""
    pytest.importorskip("solv")
    result = solve_package_install(
        {"driver": "1.0"}, {"driver": {"version": "1.0", "arch": "all"}},
        [CatalogPackage("driver", "1.0", depends="runtime (>= 2.0)"), CatalogPackage("runtime", "2.0")],
    )
    assert result["runtime"]["version"] == "2.0"
    assert result["driver"]["depends"] == "runtime (>= 2.0)"


def test_feed_loader_parses_only_enabled_metadata_without_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only public package metadata is fetched; package payloads and API credentials are absent."""
    pytest.importorskip("debian.deb822")
    content = gzip.compress(b"Package: driver\nVersion: 1.0\nArchitecture: windows_x64\nDepends: runtime (>= 2.0)\nDisplayName: Driver\n\n")
    urls: list[str] = []

    class Response:
        status_code = 200

        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_content(self, chunk_size: int) -> Iterator[bytes]:
            yield content

    def get(url: str, **kwargs: Any) -> Response:
        urls.append(url)
        assert "headers" not in kwargs and "auth" not in kwargs
        return Response()

    monkeypatch.setattr(requests, "get", get)
    catalog = load_feed_packages({
        "active": {"uri": "https://example.invalid/feed", "enabled": True},
        "disabled": {"uri": "https://example.invalid/disabled", "enabled": False},
    })
    assert urls == ["https://example.invalid/feed/Packages.gz"]
    assert catalog[0].architecture == "windows_x64"
    assert catalog[0].depends == "runtime (>= 2.0)"
    assert catalog[0].metadata["displayname"] == "Driver"
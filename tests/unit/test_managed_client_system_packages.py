"""Unit tests for host package-manager backends used by real-mode managed clients."""

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import pytest

from slcli.managed_client import system_packages
from slcli.managed_client.handlers import FixtureHandlerRegistry
from slcli.managed_client.state import StateStore
from slcli.managed_client.system_packages import (
    DpkgPackageBackend,
    PackageBackendError,
    UnsupportedPackageBackend,
    select_package_backend,
    validate_package_name,
    validate_version,
)

DPKG_OUTPUT = (
    "bash\t5.1-6\tamd64\tii \tGNU Bourne Again SHell\tshells\tUbuntu Developers <d@example.com>\n"
    "old-lib\t1.0\tamd64\trc \tOld library\tlibs\tOld Maintainer <o@example.com>\n"
    "openssl\t3.0.2\tamd64\tii \tSecure Sockets Layer toolkit\tlibs\tOpenSSL Team <s@example.com>\n"
)


class FakeRunner:
    """Record apt and dpkg invocations and return scripted results."""

    def __init__(self, results: Sequence[subprocess.CompletedProcess[str]] = ()) -> None:
        self.calls: List[List[str]] = []
        self._results = list(results)
        self.inventory = DPKG_OUTPUT

    def __call__(self, argv: List[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        if argv[0] == "dpkg-query":
            return subprocess.CompletedProcess(argv, 0, self.inventory, "")
        if self._results:
            return self._results.pop(0)
        return subprocess.CompletedProcess(argv, 0, "", "")


def _completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _backend(
    runner: FakeRunner, tmp_path: Path, privilege: Sequence[str] = ()
) -> DpkgPackageBackend:
    return DpkgPackageBackend(
        runner=runner,
        privilege_prefix=list(privilege),
        sources_list=tmp_path / "sources.list",
        sources_directory=tmp_path / "sources.list.d",
        reboot_markers=(tmp_path / "reboot-required",),
    )


def test_package_names_and_versions_reject_option_injection() -> None:
    """Names and versions that could be read as apt options or shell syntax are refused."""
    assert validate_package_name("libc6:amd64") == "libc6:amd64"
    assert validate_version("1.2.3-1ubuntu1~22.04") == "1.2.3-1ubuntu1~22.04"
    for bad_name in ("-y", "pkg;rm", "a b", ""):
        with pytest.raises(PackageBackendError) as error:
            validate_package_name(bad_name)
        assert error.value.code == "invalid-package-name"
    with pytest.raises(PackageBackendError) as error:
        validate_version("--allow-unauthenticated")
    assert error.value.code == "invalid-package-version"


def test_select_backend_uses_dpkg_for_debian_family(tmp_path: Path) -> None:
    """Ubuntu and other ID_LIKE=debian hosts get the dpkg backend when tools exist."""
    release = tmp_path / "os-release"
    release.write_text('ID=ubuntu\nID_LIKE="debian"\n', encoding="utf-8")
    backend = select_package_backend(release, which=lambda name: f"/usr/bin/{name}")
    assert isinstance(backend, DpkgPackageBackend)


def test_select_backend_rejects_other_families_and_missing_tools(tmp_path: Path) -> None:
    """Non-dpkg hosts and debian hosts without apt get a clear unsupported backend."""
    fedora = tmp_path / "fedora"
    fedora.write_text("ID=fedora\n", encoding="utf-8")
    assert isinstance(
        select_package_backend(fedora, which=lambda name: "/usr/bin/x"), UnsupportedPackageBackend
    )
    debian = tmp_path / "debian"
    debian.write_text("ID=debian\n", encoding="utf-8")
    assert isinstance(
        select_package_backend(debian, which=lambda name: None), UnsupportedPackageBackend
    )
    with pytest.raises(PackageBackendError) as error:
        select_package_backend(fedora, which=lambda name: "/usr/bin/x").list_installed()
    assert error.value.code == "unsupported-host-package-manager"


def test_list_installed_keeps_only_installed_packages(tmp_path: Path) -> None:
    """Packages in removed-but-config-remaining states are not reported as installed."""
    backend = _backend(FakeRunner(), tmp_path)
    assert backend.list_installed() == {
        "bash": {
            "version": "5.1-6",
            "arch": "amd64",
            "description": "GNU Bourne Again SHell",
            "group": "shells",
            "packager": "Ubuntu Developers <d@example.com>",
        },
        "openssl": {
            "version": "3.0.2",
            "arch": "amd64",
            "description": "Secure Sockets Layer toolkit",
            "group": "libs",
            "packager": "OpenSSL Team <s@example.com>",
        },
    }


def test_dry_run_install_uses_simulation_without_privilege(tmp_path: Path) -> None:
    """Dry runs call apt-get -s without sudo and map planned changes."""
    stdout = (
        "Inst openssl [3.0.1] (3.0.2 Ubuntu:22.04/jammy-updates [amd64])\nInst curl (7.81 Ubuntu)\n"
    )
    runner = FakeRunner([_completed(stdout)])
    backend = _backend(runner, tmp_path, privilege=["sudo", "-n"])
    changes = backend.install(
        {"openssl": "latest", "curl": "7.81"}, dry_run=True, install_recommends=False
    )
    assert changes == {
        "curl": {"old": "", "new": "7.81"},
        "openssl": {"old": "3.0.1", "new": "3.0.2"},
    }
    apt_call = runner.calls[0]
    assert "sudo" not in apt_call
    assert "-s" in apt_call and "--no-install-recommends" in apt_call
    assert "LC_ALL=C" in apt_call and "DEBIAN_FRONTEND=noninteractive" in apt_call
    assert apt_call[-3:] == ["install", "openssl", "curl=7.81"]


def test_real_install_runs_privileged_and_diffs_inventory(tmp_path: Path) -> None:
    """A real install runs apt-get through the privilege prefix and reports version changes."""

    class UpgradingRunner(FakeRunner):
        def __call__(self, argv: List[str]) -> subprocess.CompletedProcess[str]:
            result = super().__call__(argv)
            if "apt-get" in argv and "install" in argv:
                self.inventory = (
                    DPKG_OUTPUT.replace("3.0.2", "3.0.3") + "curl\t7.81\tamd64\tii \tcurl\tweb\tC\n"
                )
            return result

    runner = UpgradingRunner()
    backend = _backend(runner, tmp_path, privilege=["sudo", "-n"])
    changes = backend.install(
        {"openssl": "latest", "curl": "latest"}, dry_run=False, install_recommends=True
    )
    assert changes == {
        "curl": {"old": "", "new": "7.81"},
        "openssl": {"old": "3.0.2", "new": "3.0.3"},
    }
    apt_call = [call for call in runner.calls if "apt-get" in call][-1]
    assert apt_call[:2] == ["sudo", "-n"]
    assert apt_call[-3:] == ["install", "openssl", "curl"]
    assert "--install-recommends" in apt_call and "-s" not in apt_call


def test_remove_builds_remove_argv_and_parses_simulation(tmp_path: Path) -> None:
    """Dry-run removal parses Remv lines into old/new changes."""
    runner = FakeRunner([_completed("Remv openssl [3.0.2]\n")])
    backend = _backend(runner, tmp_path)
    assert backend.remove(["openssl"], dry_run=True) == {"openssl": {"old": "3.0.2", "new": ""}}
    assert runner.calls[0][-2:] == ["remove", "openssl"]


def test_apt_failure_becomes_backend_error(tmp_path: Path) -> None:
    """A non-zero apt-get exit is reported with the tool's last output line."""
    runner = FakeRunner([_completed("", 100, "E: Unable to locate package nope\n")])
    backend = _backend(runner, tmp_path)
    with pytest.raises(PackageBackendError) as error:
        backend.install({"nope": "latest"}, dry_run=True, install_recommends=True)
    assert error.value.code == "package-command-failed"
    assert "Unable to locate package nope" in error.value.message


def test_install_rejects_unsafe_names_before_running_anything(tmp_path: Path) -> None:
    """Invalid names never reach the command runner."""
    runner = FakeRunner()
    backend = _backend(runner, tmp_path)
    with pytest.raises(PackageBackendError):
        backend.install({"-o": "latest"}, dry_run=False, install_recommends=True)
    assert runner.calls == []


def test_list_repositories_reads_one_line_and_deb822_sources(tmp_path: Path) -> None:
    """Classic and deb822 sources are both reported, with disabled one-line entries."""
    (tmp_path / "sources.list").write_text(
        "# comment\n"
        "deb http://archive.ubuntu.com/ubuntu jammy main\n"
        "# deb-src http://archive.ubuntu.com/ubuntu jammy main\n",
        encoding="utf-8",
    )
    directory = tmp_path / "sources.list.d"
    directory.mkdir()
    (directory / "extra.sources").write_text(
        "Types: deb\nURIs: https://repo.example.com/apt\nSuites: stable\nEnabled: no\nTrusted: yes\n",
        encoding="utf-8",
    )
    repositories: Dict[str, Dict[str, Any]] = _backend(FakeRunner(), tmp_path).list_repositories()
    assert repositories["sources.list-1"] == {
        "uri": "http://archive.ubuntu.com/ubuntu",
        "enabled": True,
        "trusted": False,
    }
    assert repositories["sources.list-2"]["enabled"] is False
    assert repositories["extra.sources"] == {
        "uri": "https://repo.example.com/apt",
        "enabled": False,
        "trusted": True,
    }


def test_reboot_required_follows_marker_file(tmp_path: Path) -> None:
    """The Debian reboot marker controls reboot_required."""
    backend = _backend(FakeRunner(), tmp_path)
    assert backend.reboot_required() is False
    (tmp_path / "reboot-required").write_text("*** System restart required ***\n", encoding="utf-8")
    assert backend.reboot_required() is True


class RecordingBackend:
    """Fake backend that records calls and returns scripted values."""

    def __init__(self) -> None:
        self.calls: List[tuple[str, Any]] = []

    def list_installed(self) -> Dict[str, Dict[str, str]]:
        self.calls.append(("list_installed", None))
        return {"openssl": {"version": "3.0.2", "arch": "amd64"}}

    def install(
        self, packages: Mapping[str, str], dry_run: bool, install_recommends: bool
    ) -> Dict[str, Dict[str, str]]:
        self.calls.append(("install", (dict(packages), dry_run, install_recommends)))
        return {"openssl": {"old": "", "new": "3.0.2"}}

    def remove(self, names: Sequence[str], dry_run: bool) -> Dict[str, Dict[str, str]]:
        self.calls.append(("remove", (list(names), dry_run)))
        return {"openssl": {"old": "3.0.2", "new": ""}}

    def list_repositories(self) -> Dict[str, Dict[str, Any]]:
        self.calls.append(("list_repositories", None))
        return {"sources.list-1": {"uri": "http://x", "enabled": True, "trusted": False}}

    def reboot_required(self) -> bool:
        self.calls.append(("reboot_required", None))
        return True


def _job(
    function: str, args: List[Any] | None = None, kwargs: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    return {"jid": "job-1", "fun": function, "arg": args or [], "kwarg": kwargs or {}}


def test_registry_routes_package_jobs_to_backend_and_skips_mock_state(tmp_path: Path) -> None:
    """With a backend, install/remove/list/repo/reboot jobs use the backend, not mock state."""
    backend = RecordingBackend()
    store = StateStore(tmp_path / "minion")
    registry = FixtureHandlerRegistry(state_store=store, package_backend=backend)

    install = registry.dispatch(
        _job("pkg.install", kwargs={"pkgs": ["openssl"], "test": True}), "minion-a"
    )
    assert install["retcode"] == 0 and install["return"] == {"openssl": {"old": "", "new": "3.0.2"}}
    assert backend.calls[0] == ("install", ({"openssl": "latest"}, True, True))

    removed = registry.dispatch(_job("pkg.remove", args=["openssl"]), "minion-a")
    assert removed["return"] == {"openssl": {"old": "3.0.2", "new": ""}}
    assert ("remove", (["openssl"], False)) in backend.calls

    listed = registry.dispatch(_job("pkg.list_pkgs"), "minion-a")
    assert listed["return"] == {"openssl": "3.0.2"}
    repos = registry.dispatch(_job("pkg.list_repos"), "minion-a")
    assert repos["return"] == {
        "http://x": [
            {"name": "sources.list-1", "uri": "http://x", "enabled": True, "trusted": False}
        ]
    }
    reboot = registry.dispatch(_job("system.get_reboot_required_witnessed"), "minion-a")
    assert reboot["return"] is True

    assert store.get_installed_packages() == {}


def test_registry_rejects_mod_repo_on_real_hosts(tmp_path: Path) -> None:
    """Writing apt sources is not supported in real mode, so mod_repo fails clearly."""
    registry = FixtureHandlerRegistry(
        state_store=StateStore(tmp_path / "minion"), package_backend=RecordingBackend()
    )
    result = registry.dispatch(
        _job("pkg.mod_repo", args=["repo"], kwargs={"uri": "http://x"}), "minion-a"
    )
    assert result["retcode"] == 2
    assert result["error"] == "pkg.mod_repo-unsupported-on-host"


def test_registry_maps_backend_errors_to_salt_failure(tmp_path: Path) -> None:
    """Backend failures return retcode 2 with the backend's stable error code and message."""

    class FailingBackend(RecordingBackend):
        def install(
            self, packages: Mapping[str, str], dry_run: bool, install_recommends: bool
        ) -> Dict[str, Dict[str, str]]:
            raise PackageBackendError("package-command-failed", "apt-get exited with status 100")

    registry = FixtureHandlerRegistry(package_backend=FailingBackend())
    result = registry.dispatch(_job("pkg.install", kwargs={"pkgs": ["openssl"]}), "minion-a")
    assert result["retcode"] == 2
    assert result["error"] == "package-command-failed"
    assert result["return"] == {"message": "apt-get exited with status 100"}


def test_default_runner_maps_missing_binary_to_backend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing package-manager binary is reported as a backend error, not a traceback."""

    def missing(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("dpkg-query")

    monkeypatch.setattr(system_packages.subprocess, "run", missing)
    with pytest.raises(PackageBackendError) as error:
        system_packages._run_command(["dpkg-query", "-W"])
    assert error.value.code == "package-manager-missing"

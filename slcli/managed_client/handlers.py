"""Allowlisted deterministic handlers for managed-client integration jobs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .models import ManagedClientError
from .state import ASSET_IDENTIFICATION_FIELDS, StateStore
from .software import CatalogPackage, SoftwareResolutionError, load_feed_packages, solve_package_install

FixtureHandler = Callable[["FixtureJob"], "HandlerResult"]
MOCK_SYSTEM_GRAINS: Mapping[str, str] = {
    "kernel": "Windows",
    "os": "Windows",
    "os_family": "Windows",
    "cpuarch": "AMD64",
}


class HandlerError(ManagedClientError):
    """Raised for malformed fixture jobs during direct validation."""


@dataclass(frozen=True)
class FixtureJob:
    """The safe subset of a server-dispatched fixture job."""

    jid: str
    function: str
    args: Tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the fields used by deterministic handlers."""
        if not self.jid.strip():
            raise HandlerError("A fixture job ID is required.")
        if not self.function.strip():
            raise HandlerError("A fixture function is required.")
        if not isinstance(self.args, tuple):
            raise HandlerError("Fixture job args must be a tuple.")
        if not isinstance(self.kwargs, Mapping):
            raise HandlerError("Fixture job kwargs must be a map.")

    @classmethod
    def from_mapping(cls, job: Mapping[str, Any]) -> "FixtureJob":
        """Parse a job without accepting shell or evaluation fields."""
        jid = job.get("jid")
        function = job.get("fun", job.get("function"))
        args = job.get("args", job.get("arg", ()))
        kwargs = job.get("kwargs", job.get("kwarg", {}))
        if not isinstance(jid, str) or not isinstance(function, str):
            raise HandlerError("Fixture jobs require string jid and fun fields.")
        if not isinstance(args, (list, tuple)):
            raise HandlerError("Fixture job args must be a list.")
        if not isinstance(kwargs, Mapping):
            raise HandlerError("Fixture job kwargs must be a map.")
        if (
            len(args) == 1
            and isinstance(args[0], (list, tuple))
            and len(args[0]) == 1
            and isinstance(args[0][0], Mapping)
            and args[0][0].get("__kwarg__") is True
        ):
            args = args[0]
        if args and isinstance(args[-1], Mapping) and args[-1].get("__kwarg__") is True:
            salt_kwargs = {key: value for key, value in args[-1].items() if key != "__kwarg__"}
            if set(kwargs) & set(salt_kwargs):
                raise HandlerError("Fixture keyword arguments must not be duplicated.")
            kwargs = {**kwargs, **salt_kwargs}
            args = args[:-1]
        return cls(jid=jid, function=function, args=tuple(args), kwargs=kwargs)


@dataclass(frozen=True)
class HandlerResult:
    """Deterministic result returned by an allowlisted fixture handler."""

    success: bool
    return_code: int
    value: Any = None
    error: Optional[str] = None

    def to_payload(self, job: FixtureJob, minion_id: str) -> Dict[str, Any]:
        """Build a stable Salt-style return payload without secrets."""
        payload: Dict[str, Any] = {
            "jid": job.jid,
            "id": minion_id,
            "fun": job.function,
            "return": self.value,
            "retcode": self.return_code,
            "success": self.success,
        }
        if self.error is not None:
            payload["error"] = self.error
        return payload


class FixtureHandlerRegistry:
    """Dispatch only explicitly registered deterministic test handlers."""

    RETURN_SUCCESS = "slcli.test.return_success"
    RETURN_FIXTURE = "slcli.test.return_fixture"
    FAIL = "slcli.test.fail"
    REFRESH = "slcli.test.refresh"
    REFRESH_PILLAR = "saltutil.refresh_pillar"
    STATE_APPLY = "nisysmgmt.state_apply"
    RESTART = "nisysmgmt.restart"
    RESTART_IF_REQUIRED = "nisysmgmt.restart_if_required"
    REBOOT_REQUIRED = "system.get_reboot_required_witnessed"
    SET_BLACKOUT = "nisysmgmt.set_blackout"
    UNSET_BLACKOUT = "nisysmgmt.unset_blackout"
    ADD_ASSET = "ni_asset.add_asset"
    REMOVE_ASSET = "ni_asset.remove_asset"
    REFRESH_ASSET = "ni_asset.refresh"
    LIST_REPOS = "pkg.list_repos"
    MOD_REPO = "pkg.mod_repo"
    GRAINS_ITEMS = "nisysmgmt.grains_items"
    INFO_INSTALLED = "pkg.info_installed"
    INSTALL = "pkg.install"
    REMOVE = "pkg.remove"
    LIST_PACKAGES = "pkg.list_pkgs"

    def __init__(
        self,
        state_store: StateStore | None = None,
        boot_time: str | None = None,
        extra_grains: Mapping[str, Any] | None = None,
        catalog_loader: Callable[[Mapping[str, Mapping[str, Any]]], list[CatalogPackage]] = load_feed_packages,
    ) -> None:
        """Create a registry with the built-in deterministic handlers."""
        self._state_store = state_store
        self._boot_time = boot_time
        self._extra_grains = dict(extra_grains or {})
        self._catalog_loader = catalog_loader
        self._handlers: Dict[str, FixtureHandler] = {
            self.RETURN_SUCCESS: self._return_success,
            self.RETURN_FIXTURE: self._return_fixture,
            self.FAIL: self._fail,
            self.REFRESH: self._refresh,
            self.REFRESH_PILLAR: self._return_true,
            self.STATE_APPLY: self._return_true,
            self.RESTART: self._return_true,
            self.RESTART_IF_REQUIRED: self._return_true,
            self.REBOOT_REQUIRED: self._reboot_required,
            self.SET_BLACKOUT: self._set_blackout,
            self.UNSET_BLACKOUT: self._unset_blackout,
            self.ADD_ASSET: self._add_asset,
            self.REMOVE_ASSET: self._remove_asset,
            self.REFRESH_ASSET: self._refresh_asset,
            self.LIST_REPOS: self._list_repos,
            self.MOD_REPO: self._mod_repo,
            self.GRAINS_ITEMS: self._grains_items,
            self.INFO_INSTALLED: self._info_installed,
            self.INSTALL: self._install,
            self.REMOVE: self._remove,
            self.LIST_PACKAGES: self._list_packages,
        }

    def dispatch(self, job: Mapping[str, Any], minion_id: str) -> Dict[str, Any]:
        """Dispatch a job or return a deterministic unsupported/error payload."""
        functions = job.get("fun", job.get("function"))
        if isinstance(functions, list):
            return self._dispatch_batch(job, minion_id)
        try:
            fixture_job = FixtureJob.from_mapping(job)
        except HandlerError as error:
            return {
                "id": minion_id,
                "return": None,
                "retcode": 2,
                "success": False,
                "error": "malformed-job",
                "error_message": str(error),
            }

        handler = self._handlers.get(fixture_job.function)
        if handler is None:
            return HandlerResult(
                success=False,
                return_code=2,
                value=None,
                error="unsupported-operation",
            ).to_payload(fixture_job, minion_id)
        return handler(fixture_job).to_payload(fixture_job, minion_id)

    def _dispatch_batch(self, job: Mapping[str, Any], minion_id: str) -> Dict[str, Any]:
        """Dispatch a multi-function Salt job and aggregate its scalar results."""
        jid = job.get("jid")
        functions = job.get("fun", job.get("function"))
        args = job.get("arg", job.get("args", []))
        kwargs = job.get("kwarg", job.get("kwargs", []))
        if (
            not isinstance(jid, str)
            or not jid.strip()
            or not functions
            or any(not isinstance(function, str) or not function.strip() for function in functions)
            or not isinstance(args, list)
            or not isinstance(kwargs, (list, tuple, Mapping))
        ):
            return {
                "id": minion_id,
                "return": None,
                "retcode": 2,
                "success": False,
                "error": "malformed-job",
                "error_message": "Multi-function fixture jobs have mismatched fields.",
            }
        if not args:
            args = [[] for _ in functions]
        elif len(args) != len(functions):
            return {
                "id": minion_id,
                "return": None,
                "retcode": 2,
                "success": False,
                "error": "malformed-job",
                "error_message": "Multi-function fixture jobs have mismatched fields.",
            }

        values: list[Any] = []
        return_codes: list[int] = []
        successes: list[bool] = []
        for index, function in enumerate(functions):
            function_kwargs: Mapping[str, Any]
            if isinstance(kwargs, Mapping):
                function_kwargs = kwargs
            else:
                if len(kwargs) not in (0, len(functions)):
                    return {
                        "id": minion_id,
                        "return": None,
                        "retcode": 2,
                        "success": False,
                        "error": "malformed-job",
                        "error_message": "Multi-function kwargs have the wrong length.",
                    }
                function_kwargs = kwargs[index] if kwargs else {}
                if not isinstance(function_kwargs, Mapping):
                    return {
                        "id": minion_id,
                        "return": None,
                        "retcode": 2,
                        "success": False,
                        "error": "malformed-job",
                        "error_message": "Multi-function kwargs must be maps.",
                    }
            try:
                fixture_job = FixtureJob.from_mapping(
                    {
                        "jid": jid,
                        "fun": function,
                        "arg": args[index],
                        "kwarg": function_kwargs,
                    }
                )
            except HandlerError as error:
                return {
                    "id": minion_id,
                    "return": None,
                    "retcode": 2,
                    "success": False,
                    "error": "malformed-job",
                    "error_message": str(error),
                }
            handler = self._handlers.get(function)
            handler_result = (
                handler(fixture_job)
                if handler is not None
                else HandlerResult(False, 2, error="unsupported-operation")
            )
            values.append(handler_result.value)
            return_codes.append(handler_result.return_code)
            successes.append(handler_result.success)

        return {
            "jid": jid,
            "id": minion_id,
            "fun": functions,
            "return": values,
            "retcode": return_codes,
            "success": successes,
        }

    def register(self, function: str, handler: FixtureHandler) -> None:
        """Register an explicit deterministic handler for test code."""
        if not function.strip():
            raise HandlerError("A handler function name is required.")
        self._handlers[function] = handler

    @staticmethod
    def _return_success(job: FixtureJob) -> HandlerResult:
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="return_success-takes-no-arguments")
        return HandlerResult(True, 0, {"value": "success"})

    @staticmethod
    def _return_fixture(job: FixtureJob) -> HandlerResult:
        if "payload" not in job.kwargs or job.args:
            return HandlerResult(False, 2, error="return_fixture-requires-payload")
        return HandlerResult(True, 0, job.kwargs["payload"])

    @staticmethod
    def _fail(job: FixtureJob) -> HandlerResult:
        if job.args:
            return HandlerResult(False, 2, error="fail-takes-keyword-arguments")
        code = job.kwargs.get("code", 1)
        message = job.kwargs.get("message", "controlled failure")
        if isinstance(code, bool) or not isinstance(code, int) or code < 1:
            return HandlerResult(False, 2, error="fail-code-must-be-a-positive-integer")
        if not isinstance(message, str):
            return HandlerResult(False, 2, error="fail-message-must-be-a-string")
        return HandlerResult(False, code, {"message": message}, error=message)

    @staticmethod
    def _refresh(job: FixtureJob) -> HandlerResult:
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="refresh-takes-no-arguments")
        return HandlerResult(True, 0, {"refreshed": True})

    @staticmethod
    def _return_true(job: FixtureJob) -> HandlerResult:
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error=f"{job.function}-takes-no-arguments")
        return HandlerResult(True, 0, True)

    @staticmethod
    def _reboot_required(job: FixtureJob) -> HandlerResult:
        """Report that mock software changes never require a host reboot."""
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="reboot-required-takes-no-arguments")
        return HandlerResult(True, 0, False)

    def _set_blackout(self, job: FixtureJob) -> HandlerResult:
        """Persist a Salt blackout request and return its new state."""
        blackout: Any
        if job.kwargs and job.args:
            return HandlerResult(False, 2, error="set_blackout-arguments-are-ambiguous")
        if not job.args and not job.kwargs:
            blackout = True
        elif len(job.args) == 1:
            blackout = job.args[0]
        elif not job.args and set(job.kwargs) == {"blackout"}:
            blackout = job.kwargs["blackout"]
        else:
            return HandlerResult(False, 2, error="set_blackout-requires-one-boolean")
        if not isinstance(blackout, bool):
            return HandlerResult(False, 2, error="set_blackout-requires-one-boolean")
        if self._state_store is None:
            return HandlerResult(False, 2, error="set_blackout-requires-state-store")
        try:
            self._state_store.record_blackout_state(blackout)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-blackout-state")
        return HandlerResult(True, 0, blackout)

    def _unset_blackout(self, job: FixtureJob) -> HandlerResult:
        """Persist the cleared Salt blackout state and return it."""
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="unset_blackout-takes-no-arguments")
        if self._state_store is None:
            return HandlerResult(False, 2, error="unset_blackout-requires-state-store")
        try:
            self._state_store.record_blackout_state(False)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-blackout-state")
        return HandlerResult(True, 0, False)

    def _add_asset(self, job: FixtureJob) -> HandlerResult:
        """Persist asset names without creating host or server state."""
        asset_kwargs: list[Mapping[str, Any]]
        if not job.args and job.kwargs:
            asset_kwargs = [job.kwargs]
        elif len(job.args) == 1 and isinstance(job.args[0], (list, tuple)):
            raw_assets = job.args[0]
            if not raw_assets or any(
                not isinstance(asset, Mapping) or asset.get("__kwarg__") is not True
                for asset in raw_assets
            ):
                return HandlerResult(False, 2, error="add_asset-requires-keyword-arguments")
            asset_kwargs = list(raw_assets)
        else:
            return HandlerResult(False, 2, error="add_asset-requires-keyword-arguments")
        names: list[str] = []
        for asset in asset_kwargs:
            name = asset.get("name")
            if not isinstance(name, str) or not name.strip():
                return HandlerResult(False, 2, error="add_asset-requires-keyword-arguments")
            names.append(name)
        if self._state_store is None:
            return HandlerResult(False, 2, error="add_asset-requires-state-store")
        try:
            self._state_store.record_asset_records(asset_kwargs)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-asset-names")
        return HandlerResult(True, 0, True)

    def _remove_asset(self, job: FixtureJob) -> HandlerResult:
        """Acknowledge removal of an asset identified by its hardware fields."""
        identification = job.kwargs.get("identification")
        if job.args or set(job.kwargs) != {"identification"}:
            return HandlerResult(False, 2, error="remove_asset-requires-identification")
        if not isinstance(identification, Mapping) or not all(
            field in identification for field in ASSET_IDENTIFICATION_FIELDS
        ):
            return HandlerResult(False, 2, error="remove_asset-requires-identification")
        if self._state_store is None:
            return HandlerResult(False, 2, error="remove_asset-requires-state-store")
        try:
            self._state_store.remove_asset(identification)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-remove-asset")
        return HandlerResult(True, 0, True)

    @staticmethod
    def _refresh_asset(job: FixtureJob) -> HandlerResult:
        """Acknowledge an asset refresh without creating server-side state."""
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="refresh-takes-no-arguments")
        return HandlerResult(True, 0, True)

    def _grains_items(self, job: FixtureJob) -> HandlerResult:
        """Return mock Windows identity and the locally persisted lock state."""
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error="grains_items-takes-no-arguments")
        try:
            blackout = self._state_store.get_blackout_state() if self._state_store else False
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-read-blackout-state")
        grains: Dict[str, Any] = {
            **MOCK_SYSTEM_GRAINS,
            **self._extra_grains,
            "minion_blackout": blackout,
            "pid": os.getpid(),
        }
        if self._boot_time is not None:
            grains["boottime"] = self._boot_time
        return HandlerResult(True, 0, grains)

    def _list_repos(self, job: FixtureJob) -> HandlerResult:
        """Return URI-grouped lists of named feed records for SystemLink."""
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error=f"{job.function}-takes-no-arguments")
        try:
            repositories = self._state_store.get_mock_repositories() if self._state_store else {}
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-read-repository-state")
        groups: Dict[str, list[Dict[str, Any]]] = {}
        for name, repository in repositories.items():
            groups.setdefault(repository["uri"], []).append({"name": name, **repository})
        return HandlerResult(True, 0, groups)

    def _mod_repo(self, job: FixtureJob) -> HandlerResult:
        """Persist a Salt repository modification in isolated mock metadata only."""
        if len(job.args) > 1 or (job.args and "name" in job.kwargs):
            return HandlerResult(False, 2, error="pkg.mod_repo-invalid-arguments")
        name = job.args[0] if job.args else job.kwargs.get("name")
        allow_renaming = job.kwargs.get("allow_renaming", False)
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(allow_renaming, bool)
            or set(job.kwargs) - {"name", "uri", "enabled", "trusted", "allow_renaming"}
        ):
            return HandlerResult(False, 2, error="pkg.mod_repo-invalid-arguments")
        if self._state_store is None:
            return HandlerResult(False, 2, error="pkg.mod_repo-requires-state-store")
        properties = {
            key: value for key, value in job.kwargs.items() if key in {"uri", "enabled", "trusted"}
        }
        try:
            repository = self._state_store.modify_mock_repository(name, properties, allow_renaming)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-repository-state")
        return HandlerResult(True, 0, repository)

    def _install(self, job: FixtureJob) -> HandlerResult:
        """Simulate named or bulk Salt package installs in isolated state only."""
        if len(job.args) > 1 or (job.args and "name" in job.kwargs):
            return HandlerResult(False, 2, error="pkg.install-requires-packages")
        name = job.args[0] if job.args else job.kwargs.get("name")
        requested = job.kwargs.get("pkgs")
        version = job.kwargs.get("version", "latest")
        if not isinstance(version, str) or not version.strip():
            return HandlerResult(False, 2, error="pkg.install-requires-packages")
        if requested is None:
            if not isinstance(name, str) or not name.strip():
                return HandlerResult(False, 2, error="pkg.install-requires-packages")
            requested = [part.strip() for part in name.split(",")]
        elif name is not None:
            return HandlerResult(False, 2, error="pkg.install-requires-packages")
        if not isinstance(requested, list) or not requested:
            return HandlerResult(False, 2, error="pkg.install-requires-packages")
        packages: Dict[str, str] = {}
        for package in requested:
            if isinstance(package, str):
                package_name, package_version = package, version
            elif isinstance(package, Mapping) and len(package) == 1:
                package_name, package_version = next(iter(package.items()))
            else:
                return HandlerResult(False, 2, error="pkg.install-requires-packages")
            if (
                not isinstance(package_name, str)
                or not package_name.strip()
                or not isinstance(package_version, str)
                or not package_version.strip()
            ):
                return HandlerResult(False, 2, error="pkg.install-requires-packages")
            packages[package_name] = package_version
        if self._state_store is None:
            return HandlerResult(False, 2, error="pkg.install-requires-state-store")
        dry_run = job.kwargs.get("test", False)
        recommends = job.kwargs.get("install_recommends", True)
        if not isinstance(dry_run, bool) or not isinstance(recommends, bool):
            return HandlerResult(False, 2, error="pkg.install-invalid-solver-flags")
        try:
            repositories = self._state_store.get_mock_repositories()
            if any(repository.get("enabled", True) for repository in repositories.values()):
                inventory = solve_package_install(
                    packages, self._state_store.get_installed_packages(),
                    self._catalog_loader(repositories), install_recommends=recommends,
                )
                changes = self._state_store.replace_mock_packages(inventory, dry_run)
            else:
                changes = self._state_store.install_mock_packages(packages, dry_run)
        except SoftwareResolutionError as error:
            return HandlerResult(False, 2, value={"message": str(error)}, error="software-resolution-failed")
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-package-state")
        return HandlerResult(True, 0, changes)

    def _remove(self, job: FixtureJob) -> HandlerResult:
        """Simulate Salt package removal in isolated mock state only."""
        if len(job.args) > 1 or (job.args and "name" in job.kwargs):
            return HandlerResult(False, 2, error="pkg.remove-requires-packages")
        name = job.args[0] if job.args else job.kwargs.get("name")
        requested = job.kwargs.get("pkgs")
        dry_run = job.kwargs.get("test", False)
        if not isinstance(dry_run, bool):
            return HandlerResult(False, 2, error="pkg.remove-invalid-test-flag")
        if requested is None:
            if not isinstance(name, str) or not name.strip():
                return HandlerResult(False, 2, error="pkg.remove-requires-packages")
            requested = [part.strip() for part in name.split(",")]
        elif name is not None:
            return HandlerResult(False, 2, error="pkg.remove-requires-packages")
        if (
            not isinstance(requested, list)
            or not requested
            or any(not isinstance(package, str) or not package.strip() for package in requested)
        ):
            return HandlerResult(False, 2, error="pkg.remove-requires-packages")
        if self._state_store is None:
            return HandlerResult(False, 2, error="pkg.remove-requires-state-store")
        try:
            changes = self._state_store.remove_mock_packages(requested, dry_run)
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-persist-package-state")
        return HandlerResult(True, 0, changes)

    def _list_packages(self, job: FixtureJob) -> HandlerResult:
        """Return mock installed versions using Salt's list_pkgs schema."""
        versions_as_list = job.kwargs.get("versions_as_list", False)
        if job.args or not isinstance(versions_as_list, bool):
            return HandlerResult(False, 2, error="pkg.list_pkgs-invalid-arguments")
        try:
            packages = self._state_store.get_installed_packages() if self._state_store else {}
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-read-package-state")
        return HandlerResult(
            True,
            0,
            {
                name: [package["version"]] if versions_as_list else package["version"]
                for name, package in packages.items()
            },
        )

    def _info_installed(self, job: FixtureJob) -> HandlerResult:
        """Return requested mock package metadata for SystemLink software refreshes."""
        attributes = job.kwargs.get("attr", ["version", "arch"])
        if (
            not isinstance(attributes, list)
            or any(not isinstance(attribute, str) for attribute in attributes)
            or any(not isinstance(name, str) for name in job.args)
        ):
            return HandlerResult(False, 2, error="pkg.info_installed-requires-attribute-list")
        try:
            packages = self._state_store.get_installed_packages() if self._state_store else {}
        except ManagedClientError:
            return HandlerResult(False, 2, error="unable-to-read-package-state")
        inventory = {
            name: {
                attribute: package[attribute] for attribute in attributes if attribute in package
            }
            for name, package in packages.items()
            if not job.args or name in job.args
        }
        return HandlerResult(True, 0, inventory)

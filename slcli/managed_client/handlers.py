"""Allowlisted deterministic handlers for managed-client integration jobs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .models import ManagedClientError

FixtureHandler = Callable[["FixtureJob"], "HandlerResult"]


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
        if args and isinstance(args[0], Mapping) and args[0].get("__kwarg__") is True:
            if len(args) != 1:
                raise HandlerError("Fixture keyword arguments must be the only argument.")
            kwargs = {key: value for key, value in args[0].items() if key != "__kwarg__"}
            args = ()
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
    LIST_REPOS = "pkg.list_repos"
    GRAINS_ITEMS = "nisysmgmt.grains_items"
    INFO_INSTALLED = "pkg.info_installed"

    def __init__(self) -> None:
        """Create a registry with the built-in deterministic handlers."""
        self._handlers: Dict[str, FixtureHandler] = {
            self.RETURN_SUCCESS: self._return_success,
            self.RETURN_FIXTURE: self._return_fixture,
            self.FAIL: self._fail,
            self.REFRESH: self._refresh,
            self.REFRESH_PILLAR: self._return_true,
            self.STATE_APPLY: self._return_true,
            self.LIST_REPOS: self._return_none,
            self.GRAINS_ITEMS: self._return_none,
            self.INFO_INSTALLED: self._info_installed,
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
            or len(args) != len(functions)
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
    def _return_none(job: FixtureJob) -> HandlerResult:
        if job.args or job.kwargs:
            return HandlerResult(False, 2, error=f"{job.function}-takes-no-arguments")
        return HandlerResult(True, 0, None)

    @staticmethod
    def _info_installed(job: FixtureJob) -> HandlerResult:
        attributes = job.kwargs.get("attr")
        if (
            job.args
            or not isinstance(attributes, list)
            or any(not isinstance(attribute, str) for attribute in attributes)
        ):
            return HandlerResult(False, 2, error="pkg.info_installed-requires-attribute-list")
        return HandlerResult(True, 0, None)

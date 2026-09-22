"""REST control-plane adapter for managed-client key approval and cleanup."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol

import requests

from .models import ManagedClientError
from ..utils import get_base_url, make_api_request

KEYS_PATH = "/nisysmgmt/v1/get-systems-keys"
MANAGE_KEYS_PATH = "/nisysmgmt/v1/manage-systems-keys"
_DEFAULT_REQUEST_TIMEOUT = 30.0


class KeyAction(str, Enum):
    """Supported Systems Management key actions."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DELETE = "DELETE"


@dataclass(frozen=True)
class SystemKeyStates:
    """Public-key values grouped by the server's key lifecycle state."""

    pending: Mapping[str, str]
    denied: Mapping[str, str]
    approved: Mapping[str, str]
    rejected: Mapping[str, str]

    def state_for(self, system_id: str) -> str | None:
        """Return the current server key state for one system ID."""
        for state, values in (
            ("pending", self.pending),
            ("denied", self.denied),
            ("approved", self.approved),
            ("rejected", self.rejected),
        ):
            if system_id in values:
                return state
        return None


class ResponseLike(Protocol):
    """Small response surface used by the adapter and its tests."""

    def json(self) -> Any:
        """Return the decoded JSON response."""
        ...


RequestFunction = Callable[..., ResponseLike]
ActionName = Literal["ACCEPT", "REJECT", "DELETE"]


class ManagedClientRestAdapter:
    """Coordinate Salt key approval through the existing REST authentication layer."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        credential: str | None = None,
        auth_scheme: str | None = None,
        request: RequestFunction = make_api_request,
    ) -> None:
        """Configure REST access without persisting the supplied credential."""
        self._base_url = (base_url or get_base_url()).rstrip("/")
        self._credential = credential
        self._auth_scheme = auth_scheme
        self._request = request

    def list_key_states(
        self, system_ids: list[str] | None = None, timeout: float | None = None
    ) -> SystemKeyStates:
        """List organization-scoped pending, denied, approved, and rejected keys."""
        payload: dict[str, Any] | None = None
        if system_ids is not None:
            payload = {"systemIds": system_ids}
        response = self._call(
            "POST" if payload is not None else "GET", KEYS_PATH, payload, timeout=timeout
        )
        try:
            data = response.json()
        except ValueError as error:
            raise ManagedClientError("REST key listing returned invalid JSON.") from error
        if not isinstance(data, Mapping):
            raise ManagedClientError("REST key listing returned an invalid response.")
        return SystemKeyStates(
            pending=self._read_key_map(data, "systemsPending"),
            denied=self._read_key_map(data, "systemsDenied"),
            approved=self._read_key_map(data, "systemsApproved"),
            rejected=self._read_key_map(data, "systemsRejected"),
        )

    def approve_pending_key(
        self,
        system_id: str,
        public_key: str,
        workspace: str,
        *,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Accept one pending key into the requested workspace."""
        self._manage_key(system_id, "ACCEPT", public_key, workspace, timeout)

    def reject_pending_key(
        self,
        system_id: str,
        public_key: str,
        workspace: str,
        *,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Reject one pending key in the requested workspace."""
        self._manage_key(system_id, "REJECT", public_key, workspace, timeout)

    def delete_managed_system(
        self,
        system_id: str,
        workspace: str,
        expected_public_key: str,
        *,
        timeout: float = _DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Delete one managed system after verifying its approved public key."""
        if not expected_public_key.strip():
            raise ValueError("The expected public key is required for managed-system cleanup.")
        self._validate_timeout(timeout)
        states = self.list_key_states([system_id], timeout=timeout)
        if states.approved.get(system_id) != expected_public_key:
            raise ManagedClientError(
                "Refusing to delete the managed system because its approved public key "
                "does not match."
            )
        self._manage_key(system_id, "DELETE", expected_public_key, workspace, timeout)

    def wait_for_key_state(
        self,
        system_id: str,
        expected_state: str,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
    ) -> None:
        """Poll key state with a bounded timeout and useful REST errors."""
        if timeout <= 0 or poll_interval <= 0:
            raise ValueError("REST polling timeout and interval must be positive.")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ManagedClientError(
                    f"REST key state for {system_id} did not reach {expected_state}."
                )
            state = self.list_key_states([system_id], timeout=remaining).state_for(system_id)
            if state == expected_state:
                return
            time.sleep(min(poll_interval, remaining))

    def _manage_key(
        self,
        system_id: str,
        action: ActionName,
        public_key: str | None,
        workspace: str,
        timeout: float,
    ) -> None:
        """Send one allowlisted key action to Systems Management."""
        if not system_id.strip() or not workspace.strip():
            raise ValueError("A system ID and workspace are required for key management.")
        self._validate_timeout(timeout)
        action_payload: dict[str, str] = {
            "id": system_id,
            "action": action,
            "workspace": workspace,
        }
        if public_key is not None:
            action_payload["key"] = public_key
        response = self._call(
            "POST",
            MANAGE_KEYS_PATH,
            {"keyActions": [action_payload]},
            timeout=timeout,
        )
        self._check_manage_key_response(response, system_id, action)

    @staticmethod
    def _validate_timeout(timeout: float) -> None:
        """Require a positive timeout for a bounded REST operation."""
        if timeout <= 0:
            raise ValueError("The REST request timeout must be positive.")

    @staticmethod
    def _check_manage_key_response(
        response: ResponseLike,
        system_id: str,
        action: ActionName,
    ) -> None:
        """Raise a typed error when a successful response contains an action failure."""
        status_code = getattr(response, "status_code", None)
        if status_code == 204:
            return
        try:
            data = response.json()
        except ValueError as error:
            raise ManagedClientError("REST key management returned invalid JSON.") from error
        if not isinstance(data, Mapping):
            raise ManagedClientError("REST key management returned an invalid response.")

        action_error = data.get("error")
        if action_error is None:
            return
        if not isinstance(action_error, Mapping):
            raise ManagedClientError("REST key management returned an invalid response.")
        messages: list[str] = []
        pending_errors: list[Mapping[str, Any]] = [action_error]
        while pending_errors:
            nested_error = pending_errors.pop(0)
            message = nested_error.get("message")
            if isinstance(message, str) and message:
                messages.append(message)
            inner_errors = nested_error.get("innerErrors", [])
            if inner_errors is None:
                continue
            if not isinstance(inner_errors, list):
                raise ManagedClientError("REST key management returned an invalid response.")
            for inner_error in inner_errors:
                if not isinstance(inner_error, Mapping):
                    raise ManagedClientError("REST key management returned an invalid response.")
                pending_errors.append(inner_error)
        message = "; ".join(messages) or "unknown action error"
        raise ManagedClientError(
            f"REST key management failed for {action} on {system_id}: {message}"
        )

    def _call(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        timeout: float | None = None,
    ) -> ResponseLike:
        """Call a configured REST route with the active authentication model."""
        kwargs: dict[str, Any] = {"payload": payload, "handle_errors": False}
        if self._credential is not None:
            kwargs["credential"] = self._credential
            kwargs["auth_scheme"] = self._auth_scheme
        if timeout is not None:
            kwargs["timeout"] = timeout
        try:
            return self._request(method, f"{self._base_url}{path}", **kwargs)
        except requests.RequestException as error:
            raise ManagedClientError(f"REST request failed for {path}.") from error

    @staticmethod
    def _read_key_map(data: Mapping[str, Any], field: str) -> dict[str, str]:
        """Read one optional server key-state dictionary safely."""
        values = data.get(field, {})
        if not isinstance(values, Mapping):
            raise ManagedClientError(f"REST key listing field {field} is invalid.")
        result: dict[str, str] = {}
        for system_id, public_key in values.items():
            if not isinstance(system_id, str) or not isinstance(public_key, str):
                raise ManagedClientError(f"REST key listing field {field} is invalid.")
            result[system_id] = public_key
        return result

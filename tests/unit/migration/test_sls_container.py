"""Tests for preparing an SLS container as the migration E2E source."""

import subprocess
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest
import requests

from tests.e2e import sls_container


def _response(status: int, body: Dict[str, Any]) -> MagicMock:
    response = MagicMock()
    response.ok = status < 400
    response.status_code = status
    response.content = b"{}"
    response.json.return_value = body
    response.text = str(body)
    response.url = "http://sls/route"
    response.request.method = "POST"
    return response


def _session(*responses: MagicMock) -> Tuple[MagicMock, List[Tuple[str, Dict[str, Any]]]]:
    posts: List[Tuple[str, Dict[str, Any]]] = []
    answers = iter(responses)

    def post(url: str, json: Dict[str, Any], timeout: int) -> MagicMock:
        posts.append((url, json))
        return next(answers)

    session = MagicMock(spec=requests.Session)
    session.post.side_effect = post
    return session, posts


def test_create_api_key_binds_a_new_policy_with_admin_credentials() -> None:
    """The key references the policy created for it, signed in as the web admin."""
    session, posts = _session(
        _response(200, {"id": "policy-1"}), _response(201, {"id": "key-1", "secret": "s3cret"})
    )

    secret = sls_container.create_api_key("http://sls", "admin", "test", session)

    assert secret == "s3cret"
    assert session.auth == ("admin", "test")
    (policy_url, policy), (key_url, key) = posts
    assert policy_url == "http://sls/niauth/v1/policies"
    assert policy["statements"] == [{"actions": ["*"], "resource": ["*"], "workspace": "*"}]
    assert key_url == "http://sls/niauth/v1/keys"
    assert key == {"name": policy["name"], "policyIds": ["policy-1"]}


def test_create_api_key_reports_the_server_error() -> None:
    """A rejected request names the status and the server's explanation."""
    session, _ = _session(_response(401, {"error": "bad credentials"}))

    with pytest.raises(RuntimeError, match="401.*bad credentials"):
        sls_container.create_api_key("http://sls", "admin", "wrong", session)


def test_retry_waits_until_the_action_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failures before the deadline are retried."""
    monkeypatch.setattr(sls_container.time, "sleep", lambda _: None)
    outcomes: List[Any] = [RuntimeError("UnknownWorkspace"), RuntimeError("503"), "ready"]

    def action() -> str:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return str(outcome)

    assert sls_container.retry("probe", action, deadline=float("inf")) == "ready"
    assert outcomes == []


def test_retry_gives_up_at_the_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """The last failure is reported once the deadline has passed."""
    monkeypatch.setattr(sls_container.time, "sleep", lambda _: None)

    def action() -> None:
        raise RuntimeError("UnknownWorkspace")

    with pytest.raises(RuntimeError, match="Gave up waiting to probe: UnknownWorkspace"):
        sls_container.retry("probe", action, deadline=0.0)


def test_retry_stops_when_the_server_crashed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A crashed server ends the wait at the first failure instead of the deadline."""
    monkeypatch.setattr(sls_container.time, "sleep", lambda _: None)
    attempts: List[int] = []

    def action() -> None:
        attempts.append(1)
        raise ConnectionResetError("Connection reset by peer")

    with pytest.raises(RuntimeError, match="Stopped waiting to probe: Windows bugcheck"):
        sls_container.retry(
            "probe", action, deadline=float("inf"), crashed=lambda: "Windows bugcheck in sls"
        )
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "outcome, expected",
    [
        (
            subprocess.CompletedProcess([], 0, stdout="2026-11-26T01:15:21Z VM paused\n"),
            "Windows bugcheck in container sls (2026-11-26T01:15:21Z VM paused)",
        ),
        (subprocess.CompletedProcess([], 1, stdout=""), None),
        (FileNotFoundError("docker"), None),
        (subprocess.TimeoutExpired("docker", 30), None),
    ],
    ids=["bugcheck", "no-bugcheck", "no-docker", "docker-timeout"],
)
def test_guest_crash_reads_the_panic_record(
    monkeypatch: pytest.MonkeyPatch, outcome: Any, expected: Optional[str]
) -> None:
    """Only a recorded bugcheck counts as a crash; Docker problems leave the deadline in charge."""
    commands: List[List[str]] = []

    def run(command: List[str], **_: Any) -> "subprocess.CompletedProcess[str]":
        commands.append(command)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(sls_container.subprocess, "run", run)

    assert sls_container.guest_crash("sls") == expected
    assert commands[0][:3] == ["docker", "exec", "sls"]


def test_mask_in_github_actions(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The key is masked in GitHub Actions logs and not printed elsewhere."""
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    sls_container.mask_in_github_actions("s3cret")
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    sls_container.mask_in_github_actions("s3cret")
    assert capsys.readouterr().out == "::add-mask::s3cret\n"

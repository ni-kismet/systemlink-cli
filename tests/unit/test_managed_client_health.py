"""Tests for the managed client's synthetic health publisher."""

import threading
from typing import Any

import pytest
import requests

from slcli.managed_client.health import (
    HealthTagPublisher,
    SyntheticHealthValues,
    build_mock_health_tags,
)
from slcli.managed_client.models import ManagedClientError


def test_health_tags_match_beacon_paths_types_and_properties() -> None:
    """Synthetic metrics retain the client's tag naming and metadata contract."""
    tags = build_mock_health_tags("mock-system", "Mock Host", "workspace/one")
    by_path = {tag["path"]: tag for tag in tags}
    assert len(tags) == 13
    cpu_count = by_path["mock-system.Health.CPU.Count"]
    assert cpu_count["type"] == "INT"
    assert cpu_count["value"] == 2
    assert cpu_count["properties"]["units"] == ""
    memory = by_path["mock-system.Health.Memory.UsePercentage"]
    assert memory["properties"]["displayName"] == "Mock Host MEMORY USED"
    assert memory["properties"]["units"] == "%"
    assert memory["properties"]["minionId"] == "mock-system"
    assert memory["properties"]["hyperlink"].startswith("#tagviewer/tag/workspace%2Fone/")
    assert memory["properties"]["slcliMock"] == "true"
    assert all(tag["collectAggregates"] for tag in tags)
    assert all(tag["workspace"] == "workspace/one" for tag in tags)


def test_publisher_uses_system_workspace_and_string_values() -> None:
    """HTTP publication creates metadata once and uses server timestamps for samples."""
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class Response:
        def json(self) -> Any:
            return [{"id": "mock-system", "workspace": "ws", "grains": {"data": {"host": "Mock"}}}]

    def request(method: str, url: str, **kwargs: Any) -> Response:
        calls.append((method, url, kwargs))
        return Response()

    publisher = HealthTagPublisher(
        "mock-system", base_url="https://example.invalid", request=request
    )
    assert publisher.publish_once() == 13
    assert len(calls) == 27
    metadata = calls[1][2]["payload"]
    assert metadata["workspace"] == "ws"
    assert "value" not in metadata
    assert metadata["properties"]["minionId"] == "mock-system"
    value = calls[-1][2]["payload"]
    assert value["value"]["type"] == "DOUBLE"
    assert isinstance(value["value"]["value"], str)
    assert 0 <= float(value["value"]["value"]) <= 100
    assert publisher.publish_once() == 13
    assert len(calls) == 41
    assert all(call[2]["handle_errors"] is False for call in calls)
    assert all(call[2]["timeout"] == 10.0 for call in calls)


def test_publisher_refuses_other_systems_before_writing_tags() -> None:
    """A wrong REST profile cannot cause tags to be created in an unrelated system."""
    calls: list[str] = []

    class Response:
        def json(self) -> Any:
            return {"id": "other-system", "workspace": "ws"}

    def request(method: str, url: str, **kwargs: Any) -> Response:
        calls.append(method)
        return Response()

    publisher = HealthTagPublisher(
        "mock-system", base_url="https://example.invalid", request=request
    )
    with pytest.raises(ManagedClientError, match="could not find"):
        publisher.publish_once()
    assert calls == ["GET"]


def test_worker_reports_http_status_without_sensitive_error_text() -> None:
    """Health retry diagnostics disclose the stage and status, never request secrets."""
    statuses: list[tuple[bool, int]] = []

    def request(method: str, url: str, **kwargs: Any) -> Any:
        response = requests.Response()
        response.status_code = 401
        raise requests.HTTPError("secret credential and private response", response=response)

    def report(success: bool, count: int) -> None:
        statuses.append((success, count))
        publisher._stop_event.set()

    publisher = HealthTagPublisher(
        "mock-system", base_url="https://example.invalid", request=request, on_status=report
    )
    publisher._run()
    assert statuses == [(False, 0)]
    assert publisher.last_error == "system lookup: HTTP 401"
    assert "secret" not in publisher.last_error


def test_random_walk_samples_remain_bounded_and_physically_consistent() -> None:
    """Long-running walks stay in realistic ranges and keep related measurements coherent."""
    now = [0.0]
    generator = SyntheticHealthValues(seed=42, clock=lambda: now[0])
    previous = generator.sample()
    changed = False
    for _ in range(1000):
        now[0] += 30.0
        values = generator.sample()
        assert 0 <= values["CPU.0.UsePercentage"] <= 100
        assert 0 <= values["CPU.1.UsePercentage"] <= 100
        assert values["CPU.MeanUsePercentage"] == pytest.approx(
            (values["CPU.0.UsePercentage"] + values["CPU.1.UsePercentage"]) / 2, abs=0.051
        )
        assert 15 <= values["Memory.UsePercentage"] <= 85
        assert 10 <= values["Disk.UsePercentage"] <= 90
        assert values["Memory.Free"] <= values["Memory.Available"]
        assert values["Memory.Used"] + values["Memory.Available"] == values["Memory.Total"]
        assert values["Disk.Used"] + values["Disk.Free"] == values["Disk.Total"]
        assert abs(values["Disk.UsePercentage"] - previous["Disk.UsePercentage"]) <= 0.1 + 1e-9
        changed = changed or values != previous
        previous = values
    assert changed


def test_seeded_walks_reproduce_samples_and_do_not_move_without_elapsed_time() -> None:
    """A seed and clock reproduce trajectories; reading twice at the same time is stable."""
    now = [0.0]
    first = SyntheticHealthValues(seed=17, clock=lambda: now[0])
    second = SyntheticHealthValues(seed=17, clock=lambda: now[0])
    assert first.sample() == first.sample() == second.sample()
    for _ in range(20):
        now[0] += 15.0
        assert first.sample() == second.sample()


def test_health_worker_publishes_periodically_and_stops() -> None:
    """The idle health worker publishes repeat samples and stops without extra writes."""
    completed = threading.Event()
    statuses: list[tuple[bool, int]] = []

    class Response:
        def json(self) -> Any:
            return {"id": "mock-system", "workspace": "ws"}

    def request(method: str, url: str, **kwargs: Any) -> Response:
        return Response()

    def report(success: bool, count: int) -> None:
        statuses.append((success, count))
        if len(statuses) == 2:
            publisher._stop_event.set()
            completed.set()

    publisher = HealthTagPublisher(
        "mock-system",
        interval=0.01,
        base_url="https://example.invalid",
        request=request,
        on_status=report,
        seed=1,
    )
    try:
        publisher.start()
        assert completed.wait(2.0)
    finally:
        publisher.stop()
    assert statuses == [(True, 13), (True, 13)]
    assert isinstance(publisher.grains["health_monitoring_interval"], int)

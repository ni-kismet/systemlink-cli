"""Synthetic SystemLink health tags using the client beacon's HTTP contract."""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode

import requests

from .models import LifecycleTimeoutError, ManagedClientError
from .rest import RequestFunction
from ..utils import get_base_url, make_api_request


@dataclass
class _MetricWalk:
    """One bounded target-seeking walk with capped per-second movement."""

    value: float
    target: float
    lower: float
    upper: float
    time_scale: float
    max_rate: float
    noise: float
    target_remaining: float = 0.0

    def advance(self, generator: random.Random, elapsed: float) -> float:
        if elapsed <= 0:
            return self.value
        if (
            self.target_remaining <= 0
            or abs(self.target - self.value) < (self.upper - self.lower) * 0.01
        ):
            self.target = generator.uniform(self.lower, self.upper)
            self.target_remaining = generator.uniform(3 * self.time_scale, 8 * self.time_scale)
        drift = (self.target - self.value) * -math.expm1(-elapsed / self.time_scale)
        step = drift + generator.gauss(0.0, self.noise * math.sqrt(elapsed))
        limit = self.max_rate * elapsed
        self.value = min(self.upper, max(self.lower, self.value + min(limit, max(-limit, step))))
        self.target_remaining -= elapsed
        return self.value


class SyntheticHealthValues:
    """Generate time-aware bounded random walks with physically consistent totals."""

    def __init__(
        self, seed: int | None = None, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Initialize synthetic CPU, memory, and disk state.

        Args:
            seed: Optional random seed for reproducible sample sequences.
            clock: Monotonic time source used to scale movement independently of publish interval.
        """
        self._random = random.Random(seed)
        self._clock = clock
        self._last_sample = clock()
        self._cpus = [
            _MetricWalk(20.0, 20.0, 0.0, 100.0, 120.0, 0.75, 0.1),
            _MetricWalk(30.0, 30.0, 0.0, 100.0, 120.0, 0.75, 0.1),
        ]
        self._memory = _MetricWalk(37.5, 37.5, 15.0, 85.0, 900.0, 0.025, 0.01)
        self._free_fraction = _MetricWalk(0.8, 0.8, 0.5, 0.9, 1200.0, 0.0001, 0.0001)
        self._disk = _MetricWalk(25.0, 25.0, 10.0, 90.0, 21600.0, 0.0003, 0.00005)

    def sample(self) -> dict[str, float | int]:
        """Advance synthetic values using elapsed time and derive correlated metrics.

        Returns:
            Metric suffixes mapped to values in the client beacon's units.
        """
        now = self._clock()
        elapsed = min(3600.0, max(0.0, now - self._last_sample))
        self._last_sample = now
        cpus = [round(cpu.advance(self._random, elapsed), 1) for cpu in self._cpus]
        memory_percentage = self._memory.advance(self._random, elapsed)
        free_fraction = self._free_fraction.advance(self._random, elapsed)
        disk_percentage = self._disk.advance(self._random, elapsed)
        memory_total = float(8 * 1024**3)
        memory_used = float(round(memory_total * memory_percentage / 100.0))
        memory_available = memory_total - memory_used
        disk_total = float(128 * 1024**3)
        disk_used = float(round(disk_total * disk_percentage / 100.0))
        values: dict[str, float | int] = {
            "CPU.Count": len(cpus),
            "CPU.MeanUsePercentage": round(sum(cpus) / len(cpus), 1),
            "Memory.Total": memory_total,
            "Memory.Used": memory_used,
            "Memory.Available": memory_available,
            "Memory.Free": float(round(memory_available * free_fraction)),
            "Memory.UsePercentage": round(memory_used / memory_total * 100.0, 1),
            "Disk.Total": disk_total,
            "Disk.Used": disk_used,
            "Disk.Free": disk_total - disk_used,
            "Disk.UsePercentage": round(disk_used / disk_total * 100.0, 1),
        }
        values.update({f"CPU.{index}.UsePercentage": value for index, value in enumerate(cpus)})
        return values


def build_mock_health_tags(
    minion_id: str,
    hostname: str,
    workspace: str,
    values: Mapping[str, float | int] | None = None,
) -> list[dict[str, Any]]:
    """Build beacon-compatible tag metadata and deterministic synthetic values.

    Args:
        minion_id: System identity used as the tag path prefix.
        hostname: Name used in the tag display metadata.
        workspace: System workspace used for tag ownership and hyperlinks.
        values: Optional correlated synthetic metric values to include in the sample.

    Returns:
        Health tag definitions including their synthetic sample values.
    """
    gibibyte = 1024.0**3
    metrics = [
        ("Disk.Free", "DISK FREE", "DOUBLE", "BYTES", 96 * gibibyte),
        ("Disk.Used", "DISK USED", "DOUBLE", "BYTES", 32 * gibibyte),
        ("Disk.Total", "DISK TOTAL", "DOUBLE", "BYTES", 128 * gibibyte),
        ("Disk.UsePercentage", "DISK USED", "DOUBLE", "%", 25.0),
        ("Memory.Free", "MEMORY FREE", "DOUBLE", "BYTES", 4 * gibibyte),
        ("Memory.Available", "MEMORY AVAILABLE", "DOUBLE", "BYTES", 5 * gibibyte),
        ("Memory.Used", "MEMORY USED", "DOUBLE", "BYTES", 3 * gibibyte),
        ("Memory.Total", "MEMORY TOTAL", "DOUBLE", "BYTES", 8 * gibibyte),
        ("Memory.UsePercentage", "MEMORY USED", "DOUBLE", "%", 37.5),
        ("CPU.Count", "CPU COUNT", "INT", "", 2),
        ("CPU.MeanUsePercentage", "CPU USED", "DOUBLE", "%", 25.0),
        ("CPU.0.UsePercentage", "CPU 0 USED", "DOUBLE", "%", 20.0),
        ("CPU.1.UsePercentage", "CPU 1 USED", "DOUBLE", "%", 30.0),
    ]
    tags: list[dict[str, Any]] = []
    for suffix, display_name, tag_type, units, value in metrics:
        path = f"{minion_id}.Health.{suffix}"
        tags.append(
            {
                "path": path,
                "type": tag_type,
                "workspace": workspace,
                "collectAggregates": True,
                "properties": {
                    "minionId": minion_id,
                    "displayName": f"{hostname} {display_name}",
                    "units": units,
                    "hyperlink": f"#tagviewer/tag/{quote(workspace, safe='')}/{quote(path, safe='')}",
                    "nitagRetention": "DURATION",
                    "nitagHistoryTTLDays": "30",
                    "nitagMaxHistoryCount": "10000",
                    "slcliMock": "true",
                },
                "value": values.get(suffix, value) if values is not None else value,
            }
        )
    return tags


class HealthTagPublisher:
    """Publish synthetic health values through the selected slcli REST profile."""

    def __init__(
        self,
        minion_id: str,
        *,
        interval: float = 300.0,
        timeout: float = 10.0,
        base_url: str | None = None,
        request: RequestFunction = make_api_request,
        on_status: Callable[[bool, int], None] | None = None,
        seed: int | None = None,
    ) -> None:
        """Configure periodic publishing without opening sockets or saving credentials.

        Args:
            minion_id: The managed system to look up in the selected REST profile.
            interval: Seconds between successful synthetic samples.
            timeout: Maximum duration of each HTTP request.
            base_url: Optional explicit REST server URL.
            request: Authenticated request function used for HTTP operations.
            on_status: Optional callback receiving success and published tag count.
            seed: Optional seed for reproducible synthetic health walks.
        """
        if not minion_id.strip() or not all(
            math.isfinite(value) and value > 0 for value in (interval, timeout)
        ):
            raise ValueError(
                "Health publishing requires an identity and positive finite intervals."
            )
        self.interval = interval
        self._minion_id = minion_id
        self._timeout = timeout
        self._base_url = (base_url or get_base_url()).rstrip("/")
        self._request = request
        self._on_status = on_status
        self._metadata: list[dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_error: str | None = None
        self._stage = "system lookup"
        self._values = SyntheticHealthValues(seed=seed)

    def publish_once(self) -> int:
        """Resolve the system workspace and publish one synthetic health sample.

        Returns:
            Number of current tag values written.
        """
        query = urlencode({"id": self._minion_id})
        self._stage = "system lookup"
        response = self._request(
            "GET",
            f"{self._base_url}/nisysmgmt/v1/systems?{query}",
            handle_errors=False,
            timeout=self._timeout,
        )
        record = response.json()
        if isinstance(record, list):
            record = record[0] if len(record) == 1 else None
        if not isinstance(record, dict) or record.get("id") != self._minion_id:
            raise ManagedClientError(
                "Health publishing could not find this minion in the REST profile."
            )
        workspace = record.get("workspace")
        if not isinstance(workspace, str) or not workspace.strip():
            raise ManagedClientError("Health publishing requires the system workspace.")
        grains = record.get("grains", {}).get("data", {}) or {}
        hostname = grains.get("host") or self._minion_id
        if not isinstance(hostname, str):
            raise ManagedClientError("Health publishing received an invalid hostname.")
        tags = build_mock_health_tags(self._minion_id, hostname, workspace, self._values.sample())
        retention = {
            "nitagRetention": str(
                grains.get("health_monitoring_retention_type", "DURATION")
            ).upper(),
            "nitagHistoryTTLDays": str(grains.get("health_monitoring_retention_duration_days", 30)),
            "nitagMaxHistoryCount": str(
                grains.get("health_monitoring_retention_max_history_count", 10000)
            ),
        }
        metadata = []
        for tag in tags:
            tag["properties"].update(retention)
            metadata.append({key: value for key, value in tag.items() if key != "value"})
        if metadata != self._metadata:
            self._stage = "tag metadata"
            for tag in metadata:
                if self._stop_event.is_set():
                    return 0
                encoded_path = quote(tag["path"], safe="")
                self._request(
                    "PUT",
                    f"{self._base_url}/nitag/v2/tags/{quote(workspace, safe='')}/{encoded_path}",
                    payload=tag,
                    handle_errors=False,
                    timeout=self._timeout,
                )
            self._metadata = metadata
        count = 0
        self._stage = "tag values"
        for tag in tags:
            if self._stop_event.is_set():
                break
            encoded_path = quote(tag["path"], safe="")
            self._request(
                "PUT",
                f"{self._base_url}/nitag/v2/tags/{quote(workspace, safe='')}/{encoded_path}/values/current",
                payload={"value": {"type": tag["type"], "value": str(tag["value"])}},
                handle_errors=False,
                timeout=self._timeout,
            )
            count += 1
        return count

    @property
    def last_error(self) -> str | None:
        """Return a safe failure reason without credentials, URLs, or response bodies."""
        return self._last_error

    @property
    def grains(self) -> dict[str, Any]:
        """Return monitoring settings advertised by this opt-in mock publisher."""
        return {
            "health_monitoring_enabled": True,
            "health_monitoring_interval": max(1, math.ceil(self.interval)),
            "health_monitoring_retention_type": "duration",
            "health_monitoring_retention_duration_days": 30,
            "health_monitoring_retention_max_history_count": 10000,
        }

    def start(self) -> None:
        """Start one background publisher for the connected Salt lifecycle."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._metadata = []
        self._thread = threading.Thread(target=self._run, name="slcli-mock-health", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Interrupt interval waits and join the worker after its bounded HTTP request."""
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(2 * self._timeout + 1)
            if self._thread.is_alive():
                raise LifecycleTimeoutError("The health publisher did not stop in time.")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                count = self.publish_once()
                success = True
                self._last_error = None
                delay = self.interval
            except (
                requests.RequestException,
                ManagedClientError,
                ValueError,
                TypeError,
                AttributeError,
            ) as error:
                self._metadata = []
                status = getattr(getattr(error, "response", None), "status_code", None)
                reason = f"HTTP {status}" if isinstance(status, int) else type(error).__name__
                if isinstance(error, ManagedClientError):
                    reason = (
                        "system identity or workspace is unavailable in the selected REST profile"
                    )
                self._last_error = f"{self._stage}: {reason}"
                count = 0
                success = False
                delay = 15.0
            if not self._stop_event.is_set() and self._on_status is not None:
                self._on_status(success, count)
            self._stop_event.wait(delay)

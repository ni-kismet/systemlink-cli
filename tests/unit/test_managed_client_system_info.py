"""Tests for simulated versus real host identity and health values."""

from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.managed_client import MinionConfiguration, health, system_info
from slcli.managed_client.health import HealthTagPublisher, build_mock_health_tags
from slcli.managed_client.system_info import HostHealthValues, identity_grains
from slcli.managed_client_click import register_managed_client_commands


def _fake_host(monkeypatch: pytest.MonkeyPatch, cpu_percent: list[float]) -> None:
    """Replace host identity and resource reads with deterministic values."""
    monkeypatch.setattr(system_info.platform, "system", lambda: "Linux")
    monkeypatch.setattr(system_info.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(system_info.socket, "gethostname", lambda: "lab-box")
    monkeypatch.setattr(system_info.socket, "getfqdn", lambda: "lab-box.example.com")
    monkeypatch.setattr(system_info, "_hardware_identity", lambda: ("Dell Inc.", "Latitude 7440"))
    monkeypatch.setattr(
        system_info.psutil,
        "net_if_addrs",
        lambda: {
            "lo": [SimpleNamespace(family=socket.AF_INET, address="127.0.0.1")],
            "eth0": [
                SimpleNamespace(family=socket.AF_INET, address="10.12.1.5"),
                SimpleNamespace(family=socket.AF_INET6, address="fe80::1"),
            ],
        },
    )
    monkeypatch.setattr(system_info.psutil, "cpu_percent", lambda **_: list(cpu_percent))
    monkeypatch.setattr(
        system_info.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(total=8000, used=3000, available=5000, free=2000, percent=37.5),
    )
    monkeypatch.setattr(
        system_info.psutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100, used=40, free=60, percent=40.0),
    )


def test_simulated_identity_uses_minion_id_and_mock_os() -> None:
    """Simulated grains keep the Windows mock identity and use the minion ID as host."""
    grains = identity_grains("minion-a", simulated=True)

    assert grains["host"] == "minion-a"
    assert grains["alias"] == "minion-a"
    assert grains["fqdn"] == "minion-a"
    assert grains["localhost"] == "minion-a"
    assert grains["kernel"] == "Windows"
    assert grains["os"] == "Windows"
    assert grains["os_family"] == "Windows"
    assert grains["manufacturer"] == system_info.SIMULATED_VENDOR
    assert grains["productname"] == system_info.SIMULATED_MODEL
    assert grains["ip4_interfaces"] == {"lo": [system_info.SIMULATED_IPV4]}


def test_real_identity_reports_local_host_and_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-simulated grains report the local host, OS, vendor, model, and IPv4 addresses."""
    _fake_host(monkeypatch, [10.0])

    grains = identity_grains("minion-a", simulated=False)

    assert grains["host"] == "lab-box"
    assert grains["alias"] == "lab-box"
    assert grains["localhost"] == "lab-box"
    assert grains["fqdn"] == "lab-box.example.com"
    assert grains["kernel"] == "Linux"
    assert grains["os"] == "Linux"
    assert grains["os_family"] == "Linux"
    assert grains["cpuarch"] == "x86_64"
    assert grains["manufacturer"] == "Dell Inc."
    assert grains["productname"] == "Latitude 7440"
    assert grains["ip4_interfaces"] == {"eth0": ["10.12.1.5"]}


def test_read_dmi_returns_firmware_value_or_unknown(tmp_path: Path) -> None:
    """DMI reads strip the firmware value and fall back to Unknown when it is missing."""
    (tmp_path / "sys_vendor").write_text("Dell Inc.\n", encoding="utf-8")

    assert system_info._read_dmi("sys_vendor", tmp_path) == "Dell Inc."
    assert system_info._read_dmi("product_name", tmp_path) == "Unknown"


def test_host_health_values_use_local_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Host sampling reports per-core CPU, memory, and system disk values."""
    _fake_host(monkeypatch, [12.34, 56.0, 30.0, 10.0])

    values = HostHealthValues().sample()

    assert values["CPU.Count"] == 4
    assert values["CPU.MeanUsePercentage"] == pytest.approx(27.1)
    assert values["CPU.0.UsePercentage"] == 12.3
    assert values["CPU.3.UsePercentage"] == 10.0
    assert values["Memory.Total"] == 8000.0
    assert values["Memory.Used"] == 3000.0
    assert values["Memory.UsePercentage"] == 37.5
    assert values["Disk.Total"] == 100.0
    assert values["Disk.Free"] == 60.0
    assert values["Disk.UsePercentage"] == 40.0


def test_mock_tags_follow_cpu_count_without_simulated_marker() -> None:
    """Real-host tags include every core and omit the simulated marker."""
    values: dict[str, float | int] = {"CPU.Count": 3, "CPU.0.UsePercentage": 1.0}
    values.update({"CPU.1.UsePercentage": 2.0, "CPU.2.UsePercentage": 3.0})

    tags = build_mock_health_tags("minion-a", "lab-box", "ws", values, simulated=False)
    paths = {tag["path"] for tag in tags}

    assert "minion-a.Health.CPU.2.UsePercentage" in paths
    assert "minion-a.Health.CPU.3.UsePercentage" not in paths
    assert all("slcliMock" not in tag["properties"] for tag in tags)


def test_simulated_tags_keep_marker_and_default_cpus() -> None:
    """Simulated tags keep the marker and the existing two-core defaults."""
    tags = build_mock_health_tags("minion-a", "minion-a", "ws")

    assert all(tag["properties"]["slcliMock"] == "true" for tag in tags)
    cpu_values = {
        tag["path"]: tag["value"] for tag in tags if ".CPU." in tag["path"] and "Use" in tag["path"]
    }
    assert cpu_values["minion-a.Health.CPU.0.UsePercentage"] == 20.0
    assert cpu_values["minion-a.Health.CPU.1.UsePercentage"] == 30.0


def test_publisher_selects_host_values_when_not_simulated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The publisher samples the local host only when simulated is false."""
    _fake_host(monkeypatch, [5.0])

    real = HealthTagPublisher("minion-a", simulated=False)
    simulated = HealthTagPublisher("minion-a", simulated=True)

    assert isinstance(real._values, HostHealthValues)
    assert isinstance(simulated._values, health.SyntheticHealthValues)


def test_minion_configuration_defaults_to_simulated(tmp_path: Path) -> None:
    """Simulated mode is the default for the minion configuration."""
    config = MinionConfiguration(master="valinor", minion_id="minion-a", state_dir=tmp_path)

    assert config.simulated is True


@pytest.mark.parametrize(("argument", "expected"), [(None, True), ("false", False), ("true", True)])
def test_run_passes_simulated_flag(
    argument: str | None, expected: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run command forwards --simulated, defaulting to true."""
    captured: dict[str, Any] = {}

    class FakeMinion:
        def __init__(self, configuration: MinionConfiguration, **kwargs: Any) -> None:
            del kwargs
            captured["simulated"] = configuration.simulated

        def start(self) -> None:
            raise RuntimeError("stop after configuration")

    @click.group()
    def test_cli() -> None:
        pass

    register_managed_client_commands(test_cli)
    monkeypatch.setattr("slcli.managed_client.TestMinion", FakeMinion)
    args = ["managed-client", "run", "--master", "valinor", "--minion-id", "minion-a"]
    args += ["--state-dir", str(tmp_path)]
    if argument is not None:
        args += ["--simulated", argument]
    CliRunner().invoke(test_cli, args)

    assert captured["simulated"] is expected

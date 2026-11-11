"""Host identity and resource sampling for managed-client test minions."""

from __future__ import annotations

import importlib
import os
import platform
import socket
from pathlib import Path
from typing import Any

import psutil

from .handlers import MOCK_SYSTEM_GRAINS

SIMULATED_VENDOR = "NI"
SIMULATED_MODEL = "Simulated managed client"
SIMULATED_IPV4 = "127.0.0.1"
_DMI_DIRECTORY = Path("/sys/class/dmi/id")


def identity_grains(minion_id: str, simulated: bool) -> dict[str, Any]:
    """Return the identity grains a minion advertises to the master.

    Args:
        minion_id: The minion identity, used as the host, alias, and localhost in simulated mode.
        simulated: When true, return the fixed simulated identity. When false, return
            values read from the local host.

    Returns:
        Grain names mapped to identity values.
    """
    if simulated:
        return {
            **MOCK_SYSTEM_GRAINS,
            "host": minion_id,
            "alias": minion_id,
            "fqdn": minion_id,
            "localhost": minion_id,
            "manufacturer": SIMULATED_VENDOR,
            "productname": SIMULATED_MODEL,
            "ip4_interfaces": {"lo": [SIMULATED_IPV4]},
        }
    system = platform.system() or "Unknown"
    hostname = socket.gethostname()
    vendor, model = _hardware_identity()
    return {
        "host": hostname,
        "localhost": hostname,
        "alias": hostname,
        "fqdn": socket.getfqdn(),
        "kernel": system,
        "os": system,
        "os_family": system,
        "cpuarch": platform.machine() or "Unknown",
        "manufacturer": vendor,
        "productname": model,
        "ip4_interfaces": _ipv4_interfaces(),
    }


def _read_dmi(name: str, directory: Path = _DMI_DIRECTORY) -> str:
    """Read one Linux DMI identity value, returning ``Unknown`` when it is unavailable."""
    try:
        return (directory / name).read_text(encoding="utf-8").strip() or "Unknown"
    except OSError:
        return "Unknown"


def _windows_bios_identity() -> tuple[str, str]:
    """Return the Windows BIOS manufacturer and product name from the registry."""
    winreg = importlib.import_module("winreg")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as key:
            vendor = str(winreg.QueryValueEx(key, "SystemManufacturer")[0]).strip()
            model = str(winreg.QueryValueEx(key, "SystemProductName")[0]).strip()
    except OSError:
        return "Unknown", "Unknown"
    return vendor or "Unknown", model or "Unknown"


def _hardware_identity() -> tuple[str, str]:
    """Return the system vendor and model reported by the local firmware."""
    if platform.system() == "Windows":
        return _windows_bios_identity()
    return _read_dmi("sys_vendor"), _read_dmi("product_name")


def _ipv4_interfaces() -> dict[str, list[str]]:
    """Map each non-loopback network interface to its IPv4 addresses."""
    interfaces: dict[str, list[str]] = {}
    for name, addresses in psutil.net_if_addrs().items():
        ipv4 = [
            address.address
            for address in addresses
            if address.family == socket.AF_INET and not address.address.startswith("127.")
        ]
        if ipv4:
            interfaces[name] = ipv4
    return interfaces


def _system_root() -> str:
    """Return the filesystem root whose usage represents the host's system disk."""
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


class HostHealthValues:
    """Sample the local host's CPU, memory, and system disk usage."""

    def __init__(self) -> None:
        """Prime per-CPU utilization so the first sample reflects recent activity."""
        psutil.cpu_percent(interval=None, percpu=True)

    def sample(self) -> dict[str, float | int]:
        """Read current host metrics using the same keys as the synthetic sampler.

        Returns:
            Metric suffixes mapped to values in the client beacon's units.
        """
        per_cpu = [round(value, 1) for value in psutil.cpu_percent(interval=None, percpu=True)]
        if not per_cpu:
            per_cpu = [0.0]
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(_system_root())
        values: dict[str, float | int] = {
            "CPU.Count": len(per_cpu),
            "CPU.MeanUsePercentage": round(sum(per_cpu) / len(per_cpu), 1),
            "Memory.Total": float(memory.total),
            "Memory.Used": float(memory.used),
            "Memory.Available": float(memory.available),
            "Memory.Free": float(memory.free),
            "Memory.UsePercentage": round(float(memory.percent), 1),
            "Disk.Total": float(disk.total),
            "Disk.Used": float(disk.used),
            "Disk.Free": float(disk.free),
            "Disk.UsePercentage": round(float(disk.percent), 1),
        }
        values.update({f"CPU.{index}.UsePercentage": value for index, value in enumerate(per_cpu)})
        return values

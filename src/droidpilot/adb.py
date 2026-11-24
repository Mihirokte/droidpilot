"""Thin wrapper around the adb binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import Blocked, DeviceError, NeedsHuman

__all__ = ["Adb", "AdbDevice", "Blocked", "DeviceError", "NeedsHuman", "find_adb", "list_devices"]


def find_adb() -> str:
    candidates = [
        os.environ.get("ADB"),
        str(Path.home() / ".local/opt/platform-tools/adb"),
        shutil.which("adb"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    raise DeviceError(
        "adb not found. Set $ADB or install platform-tools "
        "(see env.sh in the project root)."
    )


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str  # device | unauthorized | offline | ...
    detail: str


def list_devices(adb: str | None = None) -> list[AdbDevice]:
    adb = adb or find_adb()
    out = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL).stdout
    devices: list[AdbDevice] = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append(AdbDevice(parts[0], parts[1], " ".join(parts[2:])))
    return devices


class Adb:
    """adb bound to one device serial."""

    def __init__(self, serial: str, adb: str | None = None) -> None:
        self.adb = adb or find_adb()
        self.serial = serial

    def _base(self) -> list[str]:
        return [self.adb, "-s", self.serial]

    def run(self, *args: str, timeout: float = 30) -> str:
        proc = subprocess.run(
            [*self._base(), *args], capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,  # adb would otherwise consume the MCP server's stdin
        )
        if proc.returncode != 0:
            raise DeviceError(f"adb {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
        return proc.stdout

    def shell(self, command: str, timeout: float = 30) -> str:
        return self.run("shell", command, timeout=timeout)

    def exec_out(self, command: str, timeout: float = 30) -> bytes:
        proc = subprocess.run(
            [*self._base(), "exec-out", command], capture_output=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            raise DeviceError(f"adb exec-out {command} failed: {proc.stderr.decode(errors='replace').strip()}")
        return proc.stdout

    def popen_shell(self, command: str) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [*self._base(), "shell", command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

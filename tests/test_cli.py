"""Command line entry point."""

from __future__ import annotations

import subprocess
import sys

import droidpilot


def test_unknown_command_prints_usage_and_exits_2() -> None:
    out = subprocess.run([sys.executable, "-m", "droidpilot", "nope"], capture_output=True, text=True)
    assert out.returncode == 2 and "usage: droidpilot [serve|doctor|clean]" in out.stderr


def test_doctor_fails_cleanly_without_adb() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "droidpilot", "doctor"], capture_output=True, text=True,
        env={"ADB": "/nonexistent/adb", "PATH": "/usr/bin:/bin", "HOME": "/tmp/dp-cli-home"},
    )
    assert out.returncode == 1 and out.stdout.startswith(("FAIL", "PASS"))


def test_package_exposes_main_and_version() -> None:
    assert callable(droidpilot.main) and droidpilot.__version__ == "0.2.0"

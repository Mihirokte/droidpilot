"""Remove everything droidpilot leaves on the phone and on the Mac."""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path

from . import store
from .adb import Adb, find_adb, list_devices
from .errors import DeviceError
from .scrcpy import REMOTE_JAR

HOME_OPT = Path.home() / ".local/opt"
HEAVY = ("android-sdk", "avd", "jdk")  # only needed for the emulator


def _size(path: Path) -> int:
    out = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return int(out.stdout.split()[0]) * 1024 if out.returncode == 0 and out.stdout else 0


def clean_device(adb: Adb) -> list[str]:
    done: list[str] = []
    try:  # pkill may be missing or find nothing; neither is an error
        adb.shell("pkill -f com.genymobile.scrcpy.Server")
        done.append("stopped stale scrcpy servers on phone")
    except DeviceError:
        pass
    with contextlib.suppress(DeviceError):
        adb.shell("pkill -f u2.jar")  # uiautomator2 server, if the fast tree backend started it
    adb.shell(f"rm -f {REMOTE_JAR}")  # every per-launch jar
    done.append(f"removed {REMOTE_JAR} from phone")
    adb.shell("rm -rf /data/local/tmp/u2 /data/local/tmp/u2.jar")
    done.append("removed uiautomator2 files (u2.jar) from phone")
    for line in adb.run("forward", "--list").splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2].startswith("localabstract:scrcpy_"):
            adb.run("forward", "--remove", parts[1])
            done.append(f"removed adb forward {parts[1]}")
    return done


def clean_host() -> list[str]:
    done: list[str] = []
    n = store.clear("traces")  # run logs only. knowledge/ (notes, recipes) is never touched
    if n:
        done.append(f"removed {n} trace file(s) from {store.ROOT / 'traces'}")
    return done


def report_heavy() -> list[str]:
    """Report only. Deleting the emulator stack is a user decision."""
    lines = []
    for name in HEAVY:
        p = HOME_OPT / name
        if p.exists():
            lines.append(f"{name}: {_size(p) / 1e9:.1f} GB at {p} (remove with: rm -rf {p})")
    return lines


def run() -> int:
    try:
        find_adb()
        for d in list_devices():
            if d.state == "device":
                for line in clean_device(Adb(d.serial)):
                    print(f"{d.serial}: {line}")
    except DeviceError as exc:
        print(f"phone cleanup skipped: {exc}")
    for line in clean_host():
        print(line)
    for line in report_heavy():
        print("kept " + line)
    return 0

"""Command line: `droidpilot serve | doctor | clean`."""

from __future__ import annotations

import json
import sys

USAGE = "usage: droidpilot [serve|doctor|clean]"


def doctor() -> int:
    """Check every layer and print one PASS/FAIL line per step."""
    from .adb import find_adb, list_devices
    from .errors import DeviceError
    from .phone import Phone

    def line(ok: bool, msg: str) -> None:
        print(("PASS " if ok else "FAIL ") + msg)

    try:
        adb = find_adb()
    except DeviceError as exc:
        line(False, str(exc))
        return 1
    line(True, f"adb: {adb}")
    devices = list_devices(adb)
    for d in devices:
        line(d.state == "device", f"device {d.serial} state={d.state} {d.detail}")
    if not any(d.state == "device" for d in devices):
        line(False, Phone.no_device_hint(devices))
        return 1
    phone = Phone()
    try:
        print(json.dumps(phone.status(), indent=2))
        phone.observe()
        line(True, f"ui tree readable ({len(phone.elements)} elements, backend={phone.tree_backend})")
        line(True, f"home key: {phone.press_key('home')}")
        line(True, f"scroll: {phone.scroll('down', 0.3)}")
    except DeviceError as exc:
        line(False, str(exc))
        return 1
    finally:
        phone.close()
    return 0


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "serve"
    if cmd == "serve":
        from .server import run  # imported here: doctor and clean do not need the MCP SDK

        run()
    elif cmd == "doctor":
        sys.exit(doctor())
    elif cmd == "clean":
        from .cleanup import run as clean

        sys.exit(clean())
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)

"""droidpilot: full-touch Android control for AI agents, over MCP."""

from __future__ import annotations

import json
import sys


def doctor() -> int:
    """Check the whole chain and print a pass/fail line per step."""
    from .adb import DeviceError, find_adb, list_devices
    from .phone import Phone

    def line(ok: bool, msg: str) -> None:
        print(("PASS " if ok else "FAIL ") + msg)

    try:
        adb = find_adb()
        line(True, f"adb: {adb}")
    except DeviceError as exc:
        line(False, str(exc))
        return 1
    devices = list_devices(adb)
    for d in devices:
        line(d.state == "device", f"device {d.serial} state={d.state} {d.detail}")
    if not any(d.state == "device" for d in devices):
        line(False, Phone._no_device_hint(devices))
        return 1
    phone = Phone()
    try:
        print(json.dumps(phone.status(), indent=2))
        phone.observe()
        line(True, f"ui tree readable ({len(phone.elements)} elements, backend={phone.tree_backend})")
        out = phone.press_key("home")
        line(True, f"home key: {out}")
        out = phone.scroll("down", 0.3)
        line(True, f"scroll: {out}")
    except DeviceError as exc:
        line(False, str(exc))
        return 1
    finally:
        phone.close()
    return 0


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "doctor":
        sys.exit(doctor())
    if cmd == "serve":
        from .server import run

        run()
        return
    if cmd == "clean":
        from .cleanup import run

        sys.exit(run())
    print("usage: droidpilot [serve|doctor|clean]", file=sys.stderr)
    sys.exit(2)

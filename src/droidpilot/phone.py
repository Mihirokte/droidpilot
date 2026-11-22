"""High-level phone controller: gestures, text, keys, apps, observe/verify."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from PIL import Image

from . import perception as P
from . import scrcpy as S
from .adb import Adb, DeviceError, list_devices

KEYCODES = {
    "home": 3, "back": 4, "call": 5, "endcall": 6, "volume_up": 24, "volume_down": 25,
    "power": 26, "camera": 27, "tab": 61, "space": 62, "enter": 66, "delete": 67,
    "backspace": 67, "menu": 82, "search": 84, "recents": 187, "app_switch": 187,
    "escape": 111, "forward_delete": 112, "page_up": 92, "page_down": 93,
    "dpad_up": 19, "dpad_down": 20, "dpad_left": 21, "dpad_right": 22, "dpad_center": 23,
    "wakeup": 224, "sleep": 223, "mute": 164, "notifications": 83,
}

COMPACT = os.environ.get("DROIDPILOT_COMPACT", "1") != "0"  # merge card children into one line
FRAME_MS = 16  # ~60 Hz touch sampling


@dataclass
class Outcome:
    message: str
    changed: bool | None = None
    settled_ms: int | None = None

    def __str__(self) -> str:
        parts = [self.message]
        if self.changed is not None:
            parts.append(f"screen_changed={'yes' if self.changed else 'NO'}")
        if self.settled_ms is not None:
            parts.append(f"settled_after={self.settled_ms}ms")
        return "; ".join(parts)


class Phone:
    def __init__(self, serial: str | None = None) -> None:
        self._requested_serial = serial or os.environ.get("DROIDPILOT_SERIAL")
        self.view_long_side = int(os.environ.get("DROIDPILOT_VIEW_LONG_SIDE", "1600"))
        self.adb: Adb | None = None
        self.control: S.ScrcpyControl | None = None
        self.geo: P.Geometry | None = None
        self.elements: list[P.UiElement] = []
        self.input_backend = "unconnected"

    # ---- connection -------------------------------------------------------
    def connect(self) -> Adb:
        if self.adb:
            return self.adb
        devices = list_devices()
        ready = [d for d in devices if d.state == "device"]
        if self._requested_serial:
            ready = [d for d in ready if d.serial == self._requested_serial]
        if not ready:
            raise DeviceError(self._no_device_hint(devices))
        self.adb = Adb(ready[0].serial)
        return self.adb

    @staticmethod
    def _no_device_hint(devices: list) -> str:
        if not devices:
            return (
                "No Android device visible to adb. On the phone: enable Developer options > USB debugging "
                "(and 'Disable permission monitoring' on realme/Oppo), set USB mode to File transfer "
                "(not USB tethering), replug, and tap Allow on the debugging prompt."
            )
        return "adb sees devices but none are ready: " + ", ".join(f"{d.serial}={d.state}" for d in devices) + (
            ". For 'unauthorized', unlock the phone and accept the RSA prompt."
        )

    def _control(self) -> S.ScrcpyControl | None:
        """Start scrcpy control once; fall back to `adb shell input` if it cannot start."""
        adb = self.connect()
        if self.control and self.control.connected:
            return self.control
        if self.input_backend == "adb-input":
            return None
        try:
            ctl = S.ScrcpyControl(adb)
            ctl.start()
            self.control = ctl
            self.input_backend = "scrcpy"
            return ctl
        except DeviceError as exc:
            self.input_backend = "adb-input"
            self.backend_note = f"scrcpy unavailable ({exc}); using adb input fallback (no multi-touch)"
            return None

    backend_note = ""

    # ---- perception -------------------------------------------------------
    def grab(self) -> Image.Image:
        img = P.capture(self.connect())
        self.geo = P.Geometry(img.width, img.height, self.view_long_side)
        return img

    def screenshot_jpeg(self) -> bytes:
        img = self.grab()
        assert self.geo
        return P.to_view_jpeg(img, self.geo)

    def refresh_ui(self) -> str:
        adb = self.connect()
        if not self.geo:
            self.grab()
        assert self.geo
        full = P.dump_ui(adb)
        self.elements = P.compact(full, self.geo.width, self.geo.height) if COMPACT else full
        return P.format_ui(self.elements, self.geo)

    def status(self) -> dict[str, object]:
        adb = self.connect()
        img = self.grab()
        assert self.geo
        ctl = self._control()
        props = {
            k: adb.shell(f"getprop {p}").strip()
            for k, p in (("model", "ro.product.model"), ("android", "ro.build.version.release"), ("sdk", "ro.build.version.sdk"))
        }
        return {
            "serial": adb.serial,
            **props,
            "device_px": [img.width, img.height],
            "view_px": list(self.geo.view_size),
            "input_backend": self.input_backend,
            "multi_touch": ctl is not None,
            "note": self.backend_note,
            "current_app": self.current_app(),
        }

    def current_app(self) -> str:
        out = self.connect().shell("dumpsys window | grep -E 'mCurrentFocus|mFocusedApp'", timeout=15)
        m = re.search(r"([\w.]+)/([\w.$]+)", out)
        return f"{m.group(1)}/{m.group(2)}" if m else "unknown"

    # ---- verification -----------------------------------------------------
    def _acting(self, label: str, fn) -> Outcome:
        """Run `fn` (which injects input), then report whether the screen changed and settled."""
        before = P.signature(self.grab())
        fn()
        start = time.monotonic()
        time.sleep(0.12)
        prev = P.signature(self.grab())
        changed = P.diff(before, prev) > 0.8
        stable = 0
        while time.monotonic() - start < 4.0 and stable < 2:
            time.sleep(0.15)
            cur = P.signature(self.grab())
            if P.diff(prev, cur) > 0.5:
                changed = changed or P.diff(before, cur) > 0.8
                stable = 0
            else:
                stable += 1
            prev = cur
        changed = changed or P.diff(before, prev) > 0.8
        return Outcome(label, changed, int((time.monotonic() - start) * 1000))

    def wait_settled(self, max_ms: int = 4000) -> Outcome:
        start = time.monotonic()
        prev = P.signature(self.grab())
        stable = 0
        while (time.monotonic() - start) * 1000 < max_ms and stable < 2:
            time.sleep(0.15)
            cur = P.signature(self.grab())
            stable = stable + 1 if P.diff(prev, cur) <= 0.5 else 0
            prev = cur
        return Outcome("wait complete", None, int((time.monotonic() - start) * 1000))

    # ---- gestures ---------------------------------------------------------
    def _perform(self, paths: list[list[tuple[float, float]]], duration_ms: int) -> None:
        """Move N fingers along polylines (view coords) in lockstep over duration_ms."""
        assert self.geo
        geo = self.geo
        dev_paths = [[geo.to_device(x, y) for x, y in path] for path in paths]
        ctl = self._control()
        if ctl is None:
            self._perform_fallback(dev_paths, duration_ms)
            return

        def at(path: list[tuple[int, int]], t: float) -> tuple[int, int]:
            if len(path) == 1:
                return path[0]
            pos = t * (len(path) - 1)
            i = min(int(pos), len(path) - 2)
            f = pos - i
            (x0, y0), (x1, y1) = path[i], path[i + 1]
            return round(x0 + (x1 - x0) * f), round(y0 + (y1 - y0) * f)

        def send(action: int, finger: int, pos: tuple[int, int], pressure: float) -> None:
            ctl.send(S.encode_touch(action, finger, pos[0], pos[1], geo.width, geo.height, pressure))

        for i, path in enumerate(dev_paths):
            send(S.ACTION_DOWN, i, path[0], 1.0)
        steps = max(1, duration_ms // FRAME_MS)
        t0 = time.monotonic()
        for step in range(1, steps + 1):
            time.sleep(max(0.0, t0 + step * FRAME_MS / 1000 - time.monotonic()))
            t = step / steps
            for i, path in enumerate(dev_paths):
                send(S.ACTION_MOVE, i, at(path, t), 1.0)
        for i, path in enumerate(dev_paths):
            send(S.ACTION_UP, i, at(path, 1.0), 0.0)

    def _perform_fallback(self, dev_paths: list[list[tuple[int, int]]], duration_ms: int) -> None:
        adb = self.connect()
        if len(dev_paths) != 1:
            raise DeviceError("multi-touch needs the scrcpy backend, which failed to start: " + self.backend_note)
        path = dev_paths[0]
        (x0, y0), (x1, y1) = path[0], path[-1]
        if len(path) == 1 or (x0, y0) == (x1, y1):
            if duration_ms > 200:
                adb.shell(f"input swipe {x0} {y0} {x0} {y0} {duration_ms}")
            else:
                adb.shell(f"input tap {x0} {y0}")
        else:
            adb.shell(f"input swipe {x0} {y0} {x1} {y1} {duration_ms}")

    def tap(self, x: float, y: float) -> Outcome:
        return self._acting(f"tapped ({x:.0f},{y:.0f})", lambda: self._perform([[(x, y)]], 60))

    def double_tap(self, x: float, y: float) -> Outcome:
        def run() -> None:
            self._perform([[(x, y)]], 50)
            time.sleep(0.07)
            self._perform([[(x, y)]], 50)

        return self._acting(f"double-tapped ({x:.0f},{y:.0f})", run)

    def long_press(self, x: float, y: float, duration_ms: int = 900) -> Outcome:
        return self._acting(f"long-pressed ({x:.0f},{y:.0f}) {duration_ms}ms", lambda: self._perform([[(x, y)]], duration_ms))

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration_ms: int = 300) -> Outcome:
        return self._acting(
            f"swiped ({x1:.0f},{y1:.0f})->({x2:.0f},{y2:.0f}) {duration_ms}ms",
            lambda: self._perform([[(x1, y1), (x2, y2)]], duration_ms),
        )

    def scroll(self, direction: str, amount: float = 0.5, duration_ms: int = 350) -> Outcome:
        """Reveal content in `direction` (down = see content below = finger moves up)."""
        if not self.geo:
            self.grab()
        assert self.geo
        w, h = self.geo.view_size
        cx, cy = w / 2, h / 2
        dx, dy = {"down": (0, -1), "up": (0, 1), "right": (-1, 0), "left": (1, 0)}[direction]
        span = amount * (h if dx == 0 else w)
        start = (cx - dx * span / 2, cy - dy * span / 2)
        end = (cx + dx * span / 2, cy + dy * span / 2)
        return self.swipe(start[0], start[1], end[0], end[1], duration_ms)

    def pinch(self, x: float, y: float, scale: float, duration_ms: int = 400) -> Outcome:
        """scale > 1 zooms in (fingers spread), < 1 zooms out."""
        if not self.geo:
            self.grab()
        assert self.geo
        w, h = self.geo.view_size
        base = 0.15 * min(w, h)
        start_d, end_d = (base, base * scale) if scale >= 1 else (base * 1.0, base * scale)
        if scale >= 1:
            end_d = min(end_d, 0.45 * w)
        paths = [
            [(x - start_d, y), (x - end_d, y)],
            [(x + start_d, y), (x + end_d, y)],
        ]
        return self._acting(f"pinched at ({x:.0f},{y:.0f}) scale={scale}", lambda: self._perform(paths, duration_ms))

    def gesture(self, strokes: list[list[tuple[float, float]]], duration_ms: int = 400) -> Outcome:
        """Arbitrary multi-finger gesture: one polyline per finger, all moving in lockstep."""
        return self._acting(f"gesture with {len(strokes)} finger(s)", lambda: self._perform(strokes, duration_ms))

    # ---- text / keys / apps ----------------------------------------------
    def type_text(self, text: str, submit: bool = False) -> Outcome:
        def run() -> None:
            ctl = self._control()
            if ctl is None:
                if not text.isascii():
                    raise DeviceError("non-ASCII text needs the scrcpy backend")
                self.connect().shell("input text " + _shell_quote(text.replace(" ", "%s")))
            elif text.isascii() and len(text) <= S.INJECT_TEXT_MAX:
                ctl.send(S.encode_text(text))
            else:
                ctl.send(S.encode_set_clipboard(text, paste=True))
            if submit:
                self._key(KEYCODES["enter"])

        return self._acting(f"typed {len(text)} chars", run)

    def _key(self, keycode: int) -> None:
        ctl = self._control()
        if ctl is None:
            self.connect().shell(f"input keyevent {keycode}")
        else:
            ctl.send(S.encode_key(S.KEY_DOWN, keycode))
            ctl.send(S.encode_key(S.KEY_UP, keycode))

    def press_key(self, name: str) -> Outcome:
        key = name.lower()
        if key not in KEYCODES:
            raise DeviceError(f"unknown key {name!r}; known: {', '.join(sorted(KEYCODES))}")
        return self._acting(f"pressed {key}", lambda: self._key(KEYCODES[key]))

    def open_app(self, package: str) -> Outcome:
        adb = self.connect()

        def run() -> None:
            out = adb.shell(f"monkey -p {_shell_quote(package)} -c android.intent.category.LAUNCHER 1", timeout=20)
            if "No activities found" in out or "monkey aborted" in out:
                raise DeviceError(f"cannot launch {package!r}: not installed or has no launcher activity")

        return self._acting(f"opened {package}", run)

    def list_apps(self, include_system: bool = False) -> list[str]:
        flag = "" if include_system else "-3"
        out = self.connect().shell(f"pm list packages {flag}".strip())
        return sorted(line.removeprefix("package:").strip() for line in out.splitlines() if line.startswith("package:"))

    def close(self) -> None:
        if self.control:
            self.control.stop()


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

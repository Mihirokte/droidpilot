"""High-level phone controller: state, observe, gestures, text, keys, apps.

Imperative shell. The decisions live in pure modules: snapshot, guard, state, perception.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from PIL import Image

from . import guard as G
from . import knowledge as K
from . import recipes as R
from . import perception as P
from . import scrcpy as S
from . import snapshot as SN
from . import state as ST
from .adb import Adb, Blocked, DeviceError, NeedsHuman, list_devices
from .fasttree import FastTree

KEYCODES = {
    "home": 3, "back": 4, "call": 5, "endcall": 6, "volume_up": 24, "volume_down": 25,
    "power": 26, "camera": 27, "tab": 61, "space": 62, "enter": 66, "delete": 67,
    "backspace": 67, "menu": 82, "search": 84, "recents": 187, "app_switch": 187,
    "escape": 111, "forward_delete": 112, "page_up": 92, "page_down": 93,
    "dpad_up": 19, "dpad_down": 20, "dpad_left": 21, "dpad_right": 22, "dpad_center": 23,
    "wakeup": 224, "sleep": 223, "mute": 164, "notifications": 83,
}

TREE = os.environ.get("DROIDPILOT_TREE", "auto")  # auto | shell | u2
COMPACT = os.environ.get("DROIDPILOT_COMPACT", "1") != "0"  # merge card children into one line
VERIFY = os.environ.get("DROIDPILOT_VERIFY", "off")  # off: fixed wait | full: screenshot diff loop
SETTLE_MS = int(os.environ.get("DROIDPILOT_SETTLE_MS", "400"))
FRAME_MS = 16  # ~60 Hz touch sampling
READY_TTL = 15.0  # seconds before the wake/lock check runs again
SNAPSHOT_TTL = 3.0  # seconds a snapshot may be reused by tap_text
GUARD_TTL = 30.0  # seconds a snapshot may be used to name the element under a raw tap


@dataclass
class Outcome:
    message: str
    changed: bool | None = None  # None means not verified
    settled_ms: int | None = None

    def __str__(self) -> str:
        if self.changed is None:
            return f"{self.message}; not verified (waited {self.settled_ms}ms). observe reports changed=yes/NO"
        return f"{self.message}; screen_changed={'yes' if self.changed else 'NO'}; settled_after={self.settled_ms}ms"


class Phone:
    def __init__(self, serial: str | None = None) -> None:
        self._requested_serial = serial or os.environ.get("DROIDPILOT_SERIAL")
        self.view_long_side = int(os.environ.get("DROIDPILOT_VIEW_LONG_SIDE", "1600"))
        self.adb: Adb | None = None
        self.control: S.ScrcpyControl | None = None
        self.geo: P.Geometry | None = None
        self.snapshot: SN.Snapshot | None = None
        self.elements: list[P.UiElement] = []
        self.input_backend = "unconnected"
        self.backend_note = ""
        self._snap_time = 0.0
        self._fast: FastTree | None = None
        self.tree_backend = "unconnected"
        self._state: ST.DeviceState | None = None
        self._ready_at = 0.0
        self._wakes = 0
        self.last_tap: tuple[str, int] | None = None  # (text, nth) of the last tapped element, for recording

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

    # ---- device state -----------------------------------------------------
    def state(self) -> ST.DeviceState:
        st = ST.parse(self.connect().shell(ST.PROBE, timeout=20))
        if st.size:
            self.geo = P.Geometry(st.size[0], st.size[1], self.view_long_side)
        self._state = st
        return st

    def _ready(self, fresh: bool = False) -> ST.DeviceState:
        """Make sure the phone is awake and unlocked. Raise NeedsHuman if a PIN blocks it."""
        if not fresh and self._state and time.monotonic() - self._ready_at < READY_TTL:
            return self._state
        st = self.state()
        if not st.awake or st.locked:
            st = self._wake(st)
        self._state, self._ready_at = st, time.monotonic()
        return st

    def _wake(self, st: ST.DeviceState) -> ST.DeviceState:
        self._wakes += 1
        adb = self.connect()
        if not st.awake:
            adb.shell("input keyevent 224")
            time.sleep(0.6)
            st = self.state()
        if st.locked and self.geo:
            w, h = self.geo.view_size
            self._perform([[(w / 2, 0.85 * h), (w / 2, 0.25 * h)]], 250)  # swipe up: dismisses a plain lock screen
            time.sleep(0.8)
            st = self.state()
        if not st.awake or st.locked:
            raise NeedsHuman(
                "The phone is locked (PIN, pattern, password or biometric). Ask the user to unlock it, then retry."
            )
        return st

    def status(self) -> dict[str, object]:
        adb = self.connect()
        st = self._ready(fresh=True)
        ctl = self._control()
        props = {
            k: adb.shell(f"getprop {p}").strip()
            for k, p in (("model", "ro.product.model"), ("android", "ro.build.version.release"), ("sdk", "ro.build.version.sdk"))
        }
        return {
            "serial": adb.serial,
            **props,
            "device_px": list(st.size) if st.size else None,
            "view_px": list(self.geo.view_size) if self.geo else None,
            "rotation": st.rotation,
            "input_backend": self.input_backend,
            "tree_backend": self.tree_backend,
            "multi_touch": ctl is not None,
            "note": self.backend_note,
            "current_app": st.app,
        }

    def current_app(self) -> str:
        return self.state().app or "unknown"

    # ---- perception -------------------------------------------------------
    def _tree_xml(self) -> str:
        """UI hierarchy XML from the fastest backend that works. Fall back to the shell dump."""
        adb = self.connect()
        if TREE != "shell" and self.tree_backend in ("unconnected", "u2"):
            try:
                if self._fast is None:
                    self._fast = FastTree(adb.serial)
                xml = self._fast.xml()
                self.tree_backend = "u2"
                return xml
            except DeviceError as exc:
                self._fast = None
                self.tree_backend = "shell"
                self.backend_note = (self.backend_note + " " if self.backend_note else "") + f"fast tree off: {exc}"
        if self.tree_backend == "unconnected":
            self.tree_backend = "shell"
        return P.fetch_xml_shell(adb)

    def grab(self) -> Image.Image:
        img = P.capture(self.connect())
        self.geo = P.Geometry(img.width, img.height, self.view_long_side)
        return img

    def screenshot_jpeg(self) -> bytes:
        self._ready()
        img = self.grab()
        assert self.geo
        return P.to_view_jpeg(img, self.geo)

    def observe(self, diff_only: bool = False) -> str:
        """Dump the UI, make a snapshot, and report what changed since the previous one."""
        self.connect()
        wakes = self._wakes
        with ThreadPoolExecutor(max_workers=1) as pool:  # read the tree while the state probe runs
            xml_future = pool.submit(self._tree_xml)
            st = self._ready(fresh=True)
            xml = xml_future.result()
        if self._wakes != wakes:  # the phone was asleep or locked: the tree we read was the lock screen
            xml = self._tree_xml()
        assert self.geo
        full = P.parse_ui(xml)
        els = P.compact(full, self.geo.width, self.geo.height) if COMPACT else full
        if any({"edit", "focused"} <= set(e.flags) for e in els):  # only then is the keyboard query worth 0.65 s
            kb = "mInputShown=true" in self.connect().shell(ST.KEYBOARD_PROBE, timeout=15)
            st = replace(st, keyboard=kb)
        prev = self.snapshot
        snap = SN.Snapshot((prev.id + 1) if prev else 1, st.app, tuple(els), SN.digest(els))
        d = SN.diff(prev, snap) if prev else None
        self.snapshot, self._snap_time, self.elements = snap, time.monotonic(), list(els)

        w, h = self.geo.view_size
        head = f"snapshot={snap.id} screen={w}x{h} {st.banner()}"
        pkg = st.app.split("/")[0] if st.app else ""
        if pkg and K.has_notes(pkg):
            head += "\nnotes: saved for this app. Call notes() to read them."
        if d is None:
            head += "\nchanged=first observe"
        elif not d.changed:
            head += "\nchanged=NO (same screen as the previous snapshot)"
        else:
            head += f"\nchanged=yes (+{len(d.added)} new labels, -{len(d.removed)} gone)"
        if diff_only and d and d.changed and prev and prev.app == snap.app:
            body = P.format_ui(list(d.added), self.geo)
            if d.removed:
                body += "\ngone: " + "; ".join(r[:40] for r in d.removed[:12])
            return head + "\n(showing only new elements; indices still valid for tap_element)\n" + body
        return head + "\n" + P.format_ui(els, self.geo)

    def refresh_ui(self) -> str:
        return self.observe()

    # ---- action wrapper ---------------------------------------------------
    def _acting(self, label: str, fn) -> Outcome:
        """Run `fn` (injects input). Default: fixed short wait. DROIDPILOT_VERIFY=full: screenshot diff loop."""
        self._ready()
        if VERIFY != "full":
            fn()
            time.sleep(SETTLE_MS / 1000)
            return Outcome(label, None, SETTLE_MS)
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
        self._ready()
        start = time.monotonic()
        prev = P.signature(self.grab())
        stable = 0
        while (time.monotonic() - start) * 1000 < max_ms and stable < 2:
            time.sleep(0.15)
            cur = P.signature(self.grab())
            stable = stable + 1 if P.diff(prev, cur) <= 0.5 else 0
            prev = cur
        return Outcome("wait complete", True, int((time.monotonic() - start) * 1000))

    def wait_for(self, text: str, timeout_ms: int = 5000) -> str:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            self.observe()
            assert self.snapshot
            hits = SN.find(self.snapshot, text)
            if hits:
                return f"found {text!r}: [{hits[0].index}] {SN.label(hits[0])[:60]!r} (snapshot={self.snapshot.id})"
            if time.monotonic() >= deadline:
                return f"NOT FOUND after {timeout_ms}ms: {text!r}"
            time.sleep(0.3)

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

    def _check_guard(self, x: float, y: float, confirm: bool) -> None:
        """Refuse a tap on a buy/pay/send/delete element unless confirm=True."""
        snap = self.snapshot
        if confirm or not snap or not self.geo or time.monotonic() - self._snap_time > GUARD_TTL:
            return
        el = SN.element_at(snap, *self.geo.to_device(x, y))
        hit = G.check(SN.words(el)) if el else None
        if hit:
            raise Blocked(
                f"This tap is on {SN.words(el)[:70]!r}, which looks like a purchase, payment, send or delete "
                f"(matched {hit!r}). Repeat the call with confirm=true only if the user asked for it."
            )

    def tap(self, x: float, y: float, confirm: bool = False) -> Outcome:
        self._ready()
        self._check_guard(x, y, confirm)
        self.last_tap = None
        if self.snapshot and self.geo and time.monotonic() - self._snap_time <= GUARD_TTL:
            el = SN.element_at(self.snapshot, *self.geo.to_device(x, y))
            if el:
                self.last_tap = R.selector_for(self.snapshot, el)
        return self._acting(f"tapped ({x:.0f},{y:.0f})", lambda: self._perform([[(x, y)]], 60))

    def tap_element(self, index: int, snapshot_id: int | None = None, confirm: bool = False) -> Outcome:
        snap = self.snapshot
        if snap is None:
            raise DeviceError("No snapshot yet. Call observe first.")
        if snapshot_id is not None and snapshot_id != snap.id:
            raise DeviceError(f"Snapshot {snapshot_id} is old (current is {snap.id}). Call observe again.")
        if not 0 <= index < len(snap.elements):
            raise DeviceError(f"No element [{index}] in snapshot {snap.id}. Call observe again.")
        now = self._ready(fresh=True)
        if snap.app and now.app and now.app != snap.app:
            raise DeviceError(f"The foreground app changed ({snap.app} -> {now.app}) since snapshot {snap.id}. Call observe again.")
        assert self.geo
        x, y = self.geo.to_view(*snap.elements[index].center)
        return self.tap(x, y, confirm)

    def tap_text(self, text: str, nth: int = 0, confirm: bool = False) -> Outcome:
        if not self.snapshot or time.monotonic() - self._snap_time > SNAPSHOT_TTL:
            self.observe()
        assert self.snapshot and self.geo
        hits = SN.find(self.snapshot, text)
        if not 0 <= nth < len(hits):
            seen = [SN.label(e)[:30] for e in self.snapshot.elements if SN.label(e)][:15]
            raise DeviceError(f"No element matching {text!r} (match #{nth}). Visible labels: {seen}")
        x, y = self.geo.to_view(*hits[nth].center)
        return self.tap(x, y, confirm)

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
        self._ready()
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
        self._ready()
        assert self.geo
        w, h = self.geo.view_size
        base = 0.15 * min(w, h)
        start_d, end_d = base, base * scale
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

    def open_url(self, url: str, package: str | None = None) -> Outcome:
        """Open a link in an app (a deep link when the app handles it). Only safe schemes are allowed."""
        if not url.split(":", 1)[0].lower() in {"http", "https", "geo", "mailto", "tel", "sms", "smsto", "market"}:
            raise DeviceError("open_url allows http, https, geo, mailto, tel, sms, smsto and market links only")
        adb = self.connect()

        def run() -> None:
            cmd = f"am start -W -a android.intent.action.VIEW -d {_shell_quote(url)}"
            if package:
                cmd += f" {_shell_quote(package)}"
            out = adb.shell(cmd, timeout=30)
            if "Error" in out or "unable to resolve" in out.lower():
                raise DeviceError(f"cannot open {url!r}: {out.strip()[:200]}")

        return self._acting(f"opened link {url[:60]}", run)

    def list_apps(self, include_system: bool = False) -> list[str]:
        flag = "" if include_system else "-3"
        out = self.connect().shell(f"pm list packages {flag}".strip())
        return sorted(line.removeprefix("package:").strip() for line in out.splitlines() if line.startswith("package:"))

    def close(self) -> None:
        if self.control:
            self.control.stop()
        if self._fast:
            self._fast.stop()


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

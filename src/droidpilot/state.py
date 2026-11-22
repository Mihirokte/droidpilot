"""Device state from one adb call: wake state, lock, foreground app, rotation, keyboard, size."""

from __future__ import annotations

import re
from dataclasses import dataclass

# One shell call. grep on the phone keeps the transfer small.
PROBE = (
    "dumpsys power | grep -E 'mWakefulness='; "
    "dumpsys window | grep -E 'mCurrentFocus=|mFocusedApp=|isKeyguardShowing=|mRotation=[0-9]'; "
    "dumpsys input_method | grep -E 'mInputShown='; "
    "wm size"
)


@dataclass(frozen=True)
class DeviceState:
    wakefulness: str  # Awake | Dozing | Asleep | Unknown
    locked: bool  # keyguard showing
    focus: str  # focused window name
    app: str  # "package/activity" of the focused app
    rotation: int  # 0..3
    keyboard: bool
    size: tuple[int, int] | None  # (width, height) in the current orientation

    @property
    def awake(self) -> bool:
        return self.wakefulness == "Awake"

    def banner(self) -> str:
        return (
            f"app={self.app or 'unknown'} focus={self.focus or 'unknown'} "
            f"rotation={self.rotation} keyboard={'open' if self.keyboard else 'closed'}"
            + (" LOCKED" if self.locked else "")
        )


def parse(text: str) -> DeviceState:
    def first(pattern: str, default: str = "") -> str:
        m = re.search(pattern, text)
        return m.group(1) if m else default

    focus = first(r"mCurrentFocus=Window\{\S+ \S+ ([^}]+)\}")
    app = first(r"mFocusedApp=ActivityRecord\{\S+ \S+ ([\w.]+/[\w.$]+)")
    if not app and "/" in focus:
        app = focus.split()[-1]
    rotation = int(first(r"mRotation=(\d)", "0"))
    # `wm size` prints "Physical size" and, if changed, "Override size". Override wins.
    sizes = re.findall(r"(?:Physical|Override) size: (\d+)x(\d+)", text)
    size = None
    if sizes:
        w, h = map(int, sizes[-1])
        size = (h, w) if rotation in (1, 3) else (w, h)
    return DeviceState(
        wakefulness=first(r"mWakefulness=(\w+)", "Unknown"),
        locked=first(r"isKeyguardShowing=(\w+)") == "true",
        focus=focus,
        app=app,
        rotation=rotation,
        keyboard=first(r"mInputShown=(\w+)") == "true",
        size=size,
    )

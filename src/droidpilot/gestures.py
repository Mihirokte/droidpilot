"""Pure touch geometry: where each finger is at each moment. No I/O.

Paths are lists of points. A finger moves along its path at constant speed by segment count.
"""

from __future__ import annotations

Point = tuple[float, float]
Path = list[Point]

KEYCODES = {
    "home": 3, "back": 4, "call": 5, "endcall": 6, "volume_up": 24, "volume_down": 25,
    "power": 26, "camera": 27, "tab": 61, "space": 62, "enter": 66, "delete": 67,
    "backspace": 67, "menu": 82, "search": 84, "recents": 187, "app_switch": 187,
    "escape": 111, "forward_delete": 112, "page_up": 92, "page_down": 93,
    "dpad_up": 19, "dpad_down": 20, "dpad_left": 21, "dpad_right": 22, "dpad_center": 23,
    "wakeup": 224, "sleep": 223, "mute": 164, "notifications": 83,
}
DIRECTIONS = ("down", "up", "left", "right")


def point_at(path: list[tuple[int, int]], t: float) -> tuple[int, int]:
    """Position along `path` at time fraction t in [0, 1], linear between points."""
    if len(path) == 1:
        return path[0]
    pos = max(0.0, min(1.0, t)) * (len(path) - 1)
    i = min(int(pos), len(path) - 2)
    f = pos - i
    (x0, y0), (x1, y1) = path[i], path[i + 1]
    return round(x0 + (x1 - x0) * f), round(y0 + (y1 - y0) * f)


def steps_for(duration_ms: int, frame_ms: int) -> int:
    return max(1, duration_ms // frame_ms)


def scroll_path(direction: str, amount: float, width: float, height: float) -> Path:
    """One-finger path that reveals content in `direction`. 'down' moves the finger up."""
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}")
    cx, cy = width / 2, height / 2
    dx, dy = {"down": (0, -1), "up": (0, 1), "right": (-1, 0), "left": (1, 0)}[direction]
    span = amount * (height if dx == 0 else width)
    return [(cx - dx * span / 2, cy - dy * span / 2), (cx + dx * span / 2, cy + dy * span / 2)]


def pinch_paths(x: float, y: float, scale: float, width: float, height: float) -> list[Path]:
    """Two horizontal finger paths around (x, y). scale > 1 spreads (zoom in), < 1 closes."""
    base = 0.15 * min(width, height)
    end = base * scale
    if scale >= 1:
        end = min(end, 0.45 * width)
    return [[(x - base, y), (x - end, y)], [(x + base, y), (x + end, y)]]


def fallback_command(path: list[tuple[int, int]], duration_ms: int) -> str:
    """`adb shell input` command for a one-finger path (no multi-touch)."""
    (x0, y0), (x1, y1) = path[0], path[-1]
    if len(path) == 1 or (x0, y0) == (x1, y1):
        return f"input swipe {x0} {y0} {x0} {y0} {duration_ms}" if duration_ms > 200 else f"input tap {x0} {y0}"
    return f"input swipe {x0} {y0} {x1} {y1} {duration_ms}"

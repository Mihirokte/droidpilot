"""MCP server (stdio) exposing the phone to any MCP-capable coding agent."""

from __future__ import annotations

import functools
import json
import subprocess
from typing import Annotated

from mcp.server.fastmcp import FastMCP, Image
from pydantic import Field

from .adb import DeviceError
from .phone import Phone

INSTRUCTIONS = """\
Controls a real Android phone through touch, exactly like a finger.
Loop: call `observe`, pick ONE action, act, read the result line, repeat.
- All coordinates are in screenshot space (the image `observe`/`screenshot` returns).
- Prefer `tap_element(index)` from the last `observe`/`ui_tree` output; use raw `tap(x, y)` when the
  element list is empty or wrong (games, WebViews, canvas UIs).
- Every action reports `screen_changed=yes/NO`. If NO, the action had no visible effect: do not repeat
  it blindly. Re-observe and try a different approach.
- Use `scroll` to find off-screen content, `pinch` to zoom, `gesture` for custom multi-finger input.
"""

mcp = FastMCP("droidpilot", instructions=INSTRUCTIONS)
_phone = Phone()

X = Annotated[float, Field(description="x in screenshot space")]
Y = Annotated[float, Field(description="y in screenshot space")]


def _guard(fn):
    """Return device errors as tool text instead of crashing the server."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DeviceError as exc:
            return f"ERROR: {exc}"
        except subprocess.TimeoutExpired as exc:
            return f"ERROR: adb command timed out after {exc.timeout}s (phone locked, asleep, or adb stuck?)"

    return wrapper


def tool(fn):
    return mcp.tool()(_guard(fn))


@tool
def device_status() -> str:
    """Show the connected phone, screen size, input backend (scrcpy multi-touch or adb fallback) and foreground app."""
    return json.dumps(_phone.status(), indent=2)


@tool
def observe() -> list:
    """Screenshot plus numbered list of tappable/readable UI elements. Call this before deciding what to do."""
    tree = _phone.refresh_ui()  # first, so geometry is fresh
    jpeg = _phone.screenshot_jpeg()
    w, h = _phone.geo.view_size
    header = f"screen {w}x{h} (coordinate space for all tools); app={_phone.current_app()}\n"
    return [header + tree, Image(data=jpeg, format="jpeg")]


@tool
def screenshot() -> Image:
    """Screenshot only (fast, no UI tree)."""
    return Image(data=_phone.screenshot_jpeg(), format="jpeg")


@tool
def ui_tree() -> str:
    """Numbered UI elements from the accessibility hierarchy, with centers and flags (click, scroll, edit...)."""
    _phone.grab()
    return _phone.refresh_ui()


@tool
def tap(x: X, y: Y) -> str:
    """Single tap at a point."""
    return str(_phone.tap(x, y))


@tool
def tap_element(index: Annotated[int, Field(description="[n] index from the latest observe/ui_tree")]) -> str:
    """Tap the center of a UI element listed by the most recent observe/ui_tree call."""
    if not 0 <= index < len(_phone.elements):
        return "ERROR: no such element; call observe first (the screen may have changed)"
    assert _phone.geo
    el = _phone.elements[index]
    x, y = _phone.geo.to_view(*el.center)
    return str(_phone.tap(x, y))


@tool
def double_tap(x: X, y: Y) -> str:
    """Double tap (zoom in maps/photos, select a word)."""
    return str(_phone.double_tap(x, y))


@tool
def long_press(x: X, y: Y, duration_ms: int = 900) -> str:
    """Press and hold (context menus, drag handles, selection)."""
    return str(_phone.long_press(x, y, duration_ms))


@tool
def swipe(x1: X, y1: Y, x2: X, y2: Y, duration_ms: int = 300) -> str:
    """Drag one finger from (x1,y1) to (x2,y2). Short duration = fling, long = precise drag (sliders, reorder)."""
    return str(_phone.swipe(x1, y1, x2, y2, duration_ms))


@tool
def scroll(
    direction: Annotated[str, Field(description="down | up | left | right: which content to reveal")] = "down",
    amount: Annotated[float, Field(description="fraction of the screen to travel, 0.1 to 0.9")] = 0.5,
) -> str:
    """Scroll the view. 'down' reveals content below (finger moves up)."""
    if direction not in ("down", "up", "left", "right"):
        return "ERROR: direction must be down, up, left or right"
    return str(_phone.scroll(direction, amount))


@tool
def pinch(x: X, y: Y, scale: Annotated[float, Field(description=">1 zoom in, <1 zoom out")], duration_ms: int = 400) -> str:
    """Two-finger pinch centred at (x,y). Needs the scrcpy backend (see device_status)."""
    return str(_phone.pinch(x, y, scale, duration_ms))


@tool
def gesture(
    strokes: Annotated[list[list[list[float]]], Field(description="One polyline per finger: [[[x,y],[x,y],...], ...]")],
    duration_ms: int = 400,
) -> str:
    """Arbitrary multi-finger gesture. All fingers move in lockstep over duration_ms (rotate, three-finger swipe, curves)."""
    return str(_phone.gesture([[(p[0], p[1]) for p in s] for s in strokes], duration_ms))


@tool
def type_text(text: str, submit: Annotated[bool, Field(description="press Enter afterwards")] = False) -> str:
    """Type into the focused field (tap the field first). Handles non-ASCII via clipboard paste."""
    return str(_phone.type_text(text, submit))


@tool
def press_key(key: Annotated[str, Field(description="home, back, recents, enter, delete, tab, escape, volume_up, volume_down, power, notifications, wakeup, dpad_*...")]) -> str:
    """Press a hardware/navigation key."""
    return str(_phone.press_key(key))


@tool
def open_app(package: Annotated[str, Field(description="Android package name, e.g. com.android.settings; see list_apps")]) -> str:
    """Launch an app by package name."""
    return str(_phone.open_app(package))


@tool
def list_apps(include_system: bool = False) -> str:
    """Installed package names (third-party only unless include_system)."""
    return "\n".join(_phone.list_apps(include_system))


@tool
def wait(ms: Annotated[int, Field(description="max wait, 100-10000")] = 1500) -> str:
    """Wait until the screen stops changing (loading spinners, animations)."""
    return str(_phone.wait_settled(max(100, min(ms, 10000))))


def run() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        _phone.close()

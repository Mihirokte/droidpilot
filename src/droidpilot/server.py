"""MCP server (stdio) exposing the phone to any MCP-capable coding agent."""

from __future__ import annotations

import functools
import inspect
import json
import subprocess
import time
from typing import Annotated

from mcp.server.fastmcp import FastMCP, Image
from pydantic import Field

from .adb import Blocked, DeviceError, NeedsHuman
from .phone import Phone
from .trace import Trace

INSTRUCTIONS = """\
Controls a real Android phone through touch, like a finger.
Loop: `observe`, choose ONE action, act, `observe` again.
- `observe` returns numbered elements and a `snapshot` id. It also says if the screen changed since the last one.
- Prefer `tap_text("Add to cart")` or `tap_element(index, snapshot)`. Use raw `tap(x, y)` only when the list is empty (games, web views).
- Coordinates are in screenshot space. Ask for the image only when the list is not enough: `observe(image=true)`.
- Actions do not check the screen. Call `observe` to see the result. `changed=NO` means the action did nothing.
- A result that starts with BLOCKED means the safety guard stopped a buy/pay/send/delete tap. Repeat with confirm=true only if the user asked.
- A result that starts with NEEDS_HUMAN means stop and ask the user (lock screen PIN, CAPTCHA, OTP).
"""

mcp = FastMCP("droidpilot", instructions=INSTRUCTIONS)
_phone = Phone()
_trace = Trace()

X = Annotated[float, Field(description="x in screenshot space")]
Y = Annotated[float, Field(description="y in screenshot space")]
Confirm = Annotated[bool, Field(description="true only if the user asked for this buy/pay/send/delete action")]


def tool(fn):
    """Register `fn` as an MCP tool. Turn device errors into text. Log name, args, time and status."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        status = "ok"
        try:
            result = fn(*args, **kwargs)
        except NeedsHuman as exc:
            status, result = "needs_human", f"NEEDS_HUMAN: {exc}"
        except Blocked as exc:
            status, result = "blocked", f"BLOCKED: {exc}"
        except DeviceError as exc:
            status, result = "error", f"ERROR: {exc}"
        except subprocess.TimeoutExpired as exc:
            status, result = "error", f"ERROR: adb command timed out after {exc.timeout}s (phone locked, asleep, or adb stuck?)"
        try:
            bound = sig.bind_partial(*args, **kwargs).arguments
            size = len(result) if isinstance(result, str) else sum(len(p) for p in result if isinstance(p, str))
            _trace.log(fn.__name__, bound, (time.perf_counter() - start) * 1000, status, size)
        except OSError:
            pass  # a full disk must never break a tool call
        return result

    return mcp.tool()(wrapper)


@tool
def device_status() -> str:
    """Show the phone, screen size, rotation, input backend (scrcpy multi-touch or adb fallback) and foreground app."""
    return json.dumps(_phone.status(), indent=2)


@tool
def observe(
    image: Annotated[bool, Field(description="also return a screenshot")] = False,
    diff_only: Annotated[bool, Field(description="list only elements that are new since the last observe")] = False,
):
    """Numbered UI elements, a snapshot id, app/rotation/keyboard state and whether the screen changed. Call before acting."""
    text = _phone.observe(diff_only)
    return [text, Image(data=_phone.screenshot_jpeg(), format="jpeg")] if image else [text]


@tool
def screenshot():
    """Screenshot only, without the element list."""
    return Image(data=_phone.screenshot_jpeg(), format="jpeg")


@tool
def tap_text(
    text: Annotated[str, Field(description="visible label to tap, case-insensitive, partial match")],
    nth: Annotated[int, Field(description="which match to tap when several, starting at 0")] = 0,
    confirm: Confirm = False,
) -> str:
    """Tap the element whose label contains `text`. One call instead of observe, read index, tap."""
    return str(_phone.tap_text(text, nth, confirm))


@tool
def tap_element(
    index: Annotated[int, Field(description="[n] index from the latest observe")],
    snapshot: Annotated[int | None, Field(description="snapshot id from that observe. Rejects the tap if the screen was re-read since")] = None,
    confirm: Confirm = False,
) -> str:
    """Tap the center of an element from the latest observe."""
    return str(_phone.tap_element(index, snapshot, confirm))


@tool
def tap(x: X, y: Y, confirm: Confirm = False) -> str:
    """Single tap at a point."""
    return str(_phone.tap(x, y, confirm))


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


@tool
def wait_for(
    text: Annotated[str, Field(description="label to wait for")],
    timeout_ms: Annotated[int, Field(description="1000-30000")] = 5000,
) -> str:
    """Wait until an element with this label appears."""
    return _phone.wait_for(text, max(1000, min(timeout_ms, 30000)))


def run() -> None:
    try:
        mcp.run(transport="stdio")
    finally:
        _phone.close()

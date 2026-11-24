"""MCP server (stdio). Each tool is a thin call into Phone, Chrome, recipes or vision.

Results are plain text. Failures start with ERROR, BLOCKED or NEEDS_HUMAN so the agent can react.
Every call is logged to the run log (trace) and, while recording, to the recorder.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import json
import subprocess
import threading
import time
from collections.abc import Callable
from typing import Annotated, Any

import anyio
from mcp.server.fastmcp import Context, FastMCP, Image
from pydantic import Field

from . import guard as G
from . import knowledge as K
from . import recipes as R
from . import vision as V
from . import web as W
from .errors import Blocked, DeviceError, NeedsHuman
from .phone import Phone
from .recorder import Recorder
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
_recorder = Recorder()

X = Annotated[float, Field(description="x in screenshot space")]
Y = Annotated[float, Field(description="y in screenshot space")]
Confirm = Annotated[bool, Field(description="true only if the user asked for this buy/pay/send/delete action")]


# ---- plumbing ----------------------------------------------------------------
def _as_text(exc: Exception) -> tuple[str, str]:
    """(status, result text) for a failure."""
    if isinstance(exc, NeedsHuman):
        return "needs_human", f"NEEDS_HUMAN: {exc}"
    if isinstance(exc, Blocked):
        return "blocked", f"BLOCKED: {exc}"
    if isinstance(exc, subprocess.TimeoutExpired):
        return "error", f"ERROR: adb command timed out after {exc.timeout}s (phone locked, asleep, or adb stuck?)"
    return "error", f"ERROR: {exc}"


def _log(name: str, args: dict, start: float, status: str, result: Any) -> None:
    """Write the run log and feed the recorder. A full disk must never break a tool call."""
    size = len(result) if isinstance(result, str) else sum(len(p) for p in result if isinstance(p, str))
    with contextlib.suppress(OSError):
        _trace.log(name, args, (time.perf_counter() - start) * 1000, status, size)
    if status == "ok":
        _recorder.capture(name, args, result, _phone.last_tap)


def tool(fn: Callable) -> Callable:
    """Register `fn` as an MCP tool with error-to-text conversion and logging."""
    sig = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start, status = time.perf_counter(), "ok"
        try:
            result = fn(*args, **kwargs)
        except (DeviceError, subprocess.TimeoutExpired) as exc:
            status, result = _as_text(exc)
        _log(fn.__name__, dict(sig.bind_partial(*args, **kwargs).arguments), start, status, result)
        return result

    return mcp.tool()(wrapper)


def _package() -> str:
    return _phone.state().app.split("/")[0]


# ---- look ----------------------------------------------------------------------
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


# ---- touch ---------------------------------------------------------------------
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


# ---- keys, text, apps ----------------------------------------------------------
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
def open_url(
    url: Annotated[str, Field(description="http(s), geo, mailto, tel, sms or market link")],
    package: Annotated[str | None, Field(description="force this app to handle the link, e.g. in.amazon.mShop.android.shopping")] = None,
) -> str:
    """Open a link. Many apps open the matching screen directly (a deep link), which skips many taps."""
    return str(_phone.open_url(url, package))


# ---- memory: notes and recipes -------------------------------------------------
@tool
def notes(
    add: Annotated[str | None, Field(description="one short tip to save, e.g. 'Back does not close the filter panel'")] = None,
    package: Annotated[str | None, Field(description="app package. Default: the foreground app")] = None,
) -> str:
    """Read the saved tips for an app, or save one. Tips are plain text kept on this Mac."""
    pkg = package or _package()
    if add:
        return f"saved ({K.add_note(pkg, add)} bytes used for {pkg})"
    return K.get_notes(pkg) or f"(no notes for {pkg})"


@tool
def record(
    action: Annotated[str, Field(description="start | stop")],
    name: Annotated[str | None, Field(description="recipe name when stopping: a-z, 0-9, - or _")] = None,
    params: Annotated[dict[str, str] | None, Field(description="on stop: {param_name: literal value used while recording}")] = None,
    description: str = "",
) -> str:
    """Record the next tool calls as a recipe. Do the task once, then stop. Coordinates and typed text are never stored."""
    if action == "start":
        _recorder.start()
        return "recording. Do the task, then call record(action='stop', name=..., params=...)."
    if action != "stop":
        return "ERROR: action must be start or stop"
    if not _recorder.active:
        return "ERROR: not recording"
    if not name:
        return "ERROR: give a name to save the recipe"
    calls, skipped = _recorder.stop()
    steps = R.compile_steps(calls, params or {})
    K.save_recipe(name, _package(), description, steps)
    note = f". {skipped} coordinate action(s) were not stored." if skipped else ""
    return f"saved recipe {name!r}: {len(steps)} step(s), parameters {R.required_params(steps)}{note}"


@tool
def recipes(
    run: Annotated[str | None, Field(description="recipe name to run. Omit to list recipes")] = None,
    params: Annotated[dict[str, str] | None, Field(description="values for the recipe parameters")] = None,
) -> str:
    """List saved recipes, or run one. A run stops at the first failure and tells you where."""
    if not run:
        rows = K.list_recipes()
        return "\n".join(f"{r['name']} ({r['app']}): {r['description']} params={R.required_params(r['steps'])}" for r in rows) or "(no recipes yet)"
    return str(R.run(_phone, K.load_recipe(run)["steps"], params or {}))


# ---- vision ------------------------------------------------------------------
async def _look(question: str, ctx: Context) -> str:
    jpeg = await anyio.to_thread.run_sync(_phone.screenshot_jpeg)
    w, h = _phone.geo.view_size if _phone.geo else (0, 0)
    q = f"{question}\n(The image is {w}x{h} pixels. That is also the tap coordinate space.)"
    try:
        answer = await V.ask_host(ctx.session, q, jpeg)
        note = "" if answer else "client has no sampling; "
    except DeviceError as exc:
        answer, note = None, f"{exc}; "
    if answer:
        return answer
    if cfg := V.endpoint_config():
        return f"{await anyio.to_thread.run_sync(V.ask_endpoint, q, jpeg)} [via {cfg[1]}]"
    raise DeviceError(note + "no vision backend. Set DROIDPILOT_VISION_URL, or call observe(image=true) and look yourself.")


@mcp.tool()
async def look(question: Annotated[str, Field(description="one question about the screen, e.g. 'Is a filter panel open?' or 'Where is the play button?'")], ctx: Context) -> str:
    """Ask a small vision model one question about the screen. You get a short answer, not the image. Use it when observe's list is not enough (games, canvas, images)."""
    start, status = time.perf_counter(), "ok"
    try:
        out = await _look(question, ctx)
    except DeviceError as exc:
        status, out = _as_text(exc)
    _log("look", {"question": question}, start, status, out)
    return out


# ---- Chrome ------------------------------------------------------------------
@tool
def web_read() -> str:
    """Chrome only: the front tab as text, plus a numbered list of links, buttons and fields. Faster and more exact than the UI tree for web pages."""
    return W.Chrome(_phone.connect()).read()


@tool
def web_click(
    text: Annotated[str, Field(description="visible text of the link or button, partial match")],
    nth: int = 0,
    confirm: Confirm = False,
) -> str:
    """Chrome only: click a link or button by its text. The buy/pay/send/delete guard applies."""
    hit = G.check(text)
    if hit and not confirm:
        raise Blocked(f"{text!r} looks like a purchase, payment, send or delete (matched {hit!r}). Repeat with confirm=true only if the user asked.")
    out = W.Chrome(_phone.connect()).click(text, nth)
    if not out.get("ok"):
        return f"ERROR: no visible link or button matching {text!r} (found {out.get('count', 0)}). Call web_read."
    hit = G.check(out.get("name"))
    return f"clicked {out['name']!r}" + (f" (it matched the guard word {hit!r} but you confirmed)" if hit else "")


@tool
def web_fill(
    field: Annotated[str, Field(description="name, id, placeholder or label of the input")],
    value: Annotated[str, Field(description="text to put in the field")],
) -> str:
    """Chrome only: set a form field's value."""
    out = W.Chrome(_phone.connect()).fill(field, value)
    return f"filled {out['field']!r}" if out.get("ok") else f"ERROR: no input matching {field!r}. Call web_read."


# ---- waiting -----------------------------------------------------------------
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
    threading.Thread(target=_phone.warm_up, name="droidpilot-warm-up", daemon=True).start()
    try:
        mcp.run(transport="stdio")
    finally:
        _phone.close()

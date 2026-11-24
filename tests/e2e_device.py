"""End-to-end check through the real MCP stdio server against whatever device adb sees.

Run: source env.sh && uv run python tests/e2e_device.py
Not collected by pytest (needs a device). Prints the time of every call.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def text_of(res) -> str:
    return "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "droidpilot"], env=dict(os.environ, DROIDPILOT_HOME=tempfile.mkdtemp()))  # keep test logs and recipes out of the real store
    failures: list[str] = []

    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()

        async def call(tool: str, **args) -> str:
            t = time.perf_counter()
            res = await s.call_tool(tool, args)
            out = text_of(res)
            print(f"--- {time.perf_counter() - t:5.2f}s {tool}({args}) -> {out[:230]!r}")
            return out

        def check(ok: bool, what: str) -> None:
            print(("PASS " if ok else "FAIL ") + what)
            if not ok:
                failures.append(what)

        check('"scrcpy"' in await call("device_status"), "scrcpy backend active")
        await call("press_key", key="home")  # start from a known screen
        out = await call("observe")  # also proves auto-wake: the phone may start asleep
        check("snapshot=" in out and "changed=first observe" in out, "observe returns snapshot + banner")
        first_id = int(re.search(r"snapshot=(\d+)", out).group(1))
        check("LOCKED" not in out, "phone is unlocked after observe (auto-wake)")
        out = await call("press_key", key="home")
        check("not verified" in out, "action returns fast and says it is not verified")
        out = await call("open_app", package="com.android.settings")
        out = await call("observe")
        check("changed=yes" in out, "observe reports changed=yes after opening Settings")
        out = await call("observe")
        check("changed=NO" in out, "second observe reports changed=NO")
        sid = int(re.search(r"snapshot=(\d+)", out).group(1))
        label = re.search(r"\[\d+\] \w+ '([^']{3,25})' click", out)
        if label:
            out = await call("tap_text", text=label.group(1))
            check(not out.startswith(("ERROR", "BLOCKED")), f"tap_text({label.group(1)!r}) works")
            await call("press_key", key="back")
        old = await call("tap_element", index=0, snapshot=sid - 1)
        check(old.startswith("ERROR") and "old" in old, "tap_element rejects an old snapshot id")
        out = await call("tap_text", text="zzzz-not-on-screen")
        check(out.startswith("ERROR") and "Visible labels" in out, "tap_text miss lists visible labels")
        out = await call("scroll", direction="down", amount=0.6)
        out = await call("observe", diff_only=True)
        check("snapshot=" in out and int(re.search(r"snapshot=(\d+)", out).group(1)) > first_id, "diff_only observe works")
        out = await call("pinch", x=360, y=800, scale=2.0)
        check(out.startswith("pinched"), "pinch runs (two fingers)")
        out = await call("gesture", strokes=[[[200, 800], [200, 600]], [[360, 800], [360, 600]], [[520, 800], [520, 600]]])
        check(out.startswith("gesture with 3"), "3-finger gesture runs")
        out = await call("wait_for", text="zzzz-not-on-screen", timeout_ms=1000)
        check(out.startswith("NOT FOUND"), "wait_for times out cleanly")
        # recipes: record two steps, replay them, check params and notes
        await call("press_key", key="home")
        await call("record", action="start")
        await call("open_app", package="com.android.settings")
        await call("wait_for", text="Settings", timeout_ms=8000)
        out = await call("record", action="stop", name="open-settings", params={"pkg": "com.android.settings"})
        check("2 step(s)" in out and "pkg" in out, "record stop saves 2 steps with a parameter")
        await call("press_key", key="home")
        out = await call("recipes", run="open-settings")
        check("Missing parameters" in out, "recipe without params does nothing")
        out = await call("recipes", run="open-settings", params={"pkg": "com.android.settings"})
        check(out.startswith("Recipe finished"), "recipe replays with params")
        out = await call("observe")
        check("com.android.settings" in out, "replay opened Settings")
        out = await call("notes", add="Settings: scroll to find rarely used items")
        out2 = await call("observe")
        check("notes: saved" in out2, "observe hints that notes exist")
        out = await call("open_url", url="file:///etc/passwd")
        check(out.startswith("ERROR"), "open_url refuses file links")
        # Chrome through DevTools
        await call("open_url", url="https://example.com", package="com.android.chrome")
        out = await call("wait_for", text="Example Domain", timeout_ms=10000)
        out = await call("web_read")
        check("title: Example Domain" in out and "Learn more" in out, "web_read reads the Chrome page")
        out = await call("web_click", text="Learn more")
        check(out.startswith("clicked"), "web_click clicks a link")
        out = await call("web_click", text="Buy now")
        check(out.startswith("BLOCKED"), "web_click guard blocks buy")
        out = await call("look", question="What is on screen?")
        check(out.startswith(("ERROR", "NEEDS_HUMAN")) or "[via" in out, "look answers or explains the missing backend")
        await call("press_key", key="home")
    print("\nFAILED: " + "; ".join(failures) if failures else "\nALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

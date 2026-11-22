"""End-to-end check through the real MCP stdio server against whatever device adb sees.

Run: source env.sh && uv run python tests/e2e_device.py
Not collected by pytest (needs a device).
"""

from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def text_of(res) -> str:
    return "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "droidpilot"])
    failures: list[str] = []

    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()

        async def call(name: str, **args) -> str:
            res = await s.call_tool(name, args)
            out = text_of(res)
            kinds = [c.type for c in res.content]
            print(f"--- {name}({args}) -> {out[:600]}  [{kinds}]")
            return out

        def check(ok: bool, what: str) -> None:
            print(("PASS " if ok else "FAIL ") + what)
            if not ok:
                failures.append(what)

        check('"scrcpy"' in await call("device_status"), "scrcpy backend active")
        await call("press_key", key="home")
        out = await call("open_app", package="com.android.settings")
        check("screen_changed=yes" in out, "open_app changes screen")
        obs = await call("observe")
        check("Settings" in obs or "Network" in obs, "observe lists Settings UI")
        check("[0]" in obs, "observe has numbered elements")
        out = await call("scroll", direction="down", amount=0.6)
        check("screen_changed=yes" in out, "scroll down changes screen")
        out = await call("scroll", direction="up", amount=0.6)
        check("screen_changed=yes" in out, "scroll up changes screen")
        out = await call("long_press", x=360, y=800, duration_ms=700)
        check(out.startswith("long-pressed"), "long_press runs")
        out = await call("pinch", x=360, y=800, scale=2.0)
        check(out.startswith("pinched"), "pinch runs (two fingers)")
        out = await call("gesture", strokes=[[[200, 800], [200, 600]], [[360, 800], [360, 600]], [[520, 800], [520, 600]]])
        check(out.startswith("gesture with 3"), "3-finger gesture runs")
        out = await call("press_key", key="back")
        out = await call("press_key", key="home")
        check("screen_changed" in out, "home reports verification")
        out = await call("tap", x=360, y=1590)  # empty-ish spot, expect NO change or change; must not error
        check(not out.startswith("ERROR"), "tap on screen works")
        out = await call("tap_element", index=9999)
        check(out.startswith("ERROR"), "bad element index returns error")
    print("\nFAILED: " + "; ".join(failures) if failures else "\nALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

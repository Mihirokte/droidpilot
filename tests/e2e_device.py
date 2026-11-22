"""End-to-end check through the real MCP stdio server against whatever device adb sees.

Run: source env.sh && uv run python tests/e2e_device.py
Not collected by pytest (needs a device). Prints the time of every call.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time

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
            t = time.perf_counter()
            res = await s.call_tool(name, args)
            out = text_of(res)
            print(f"--- {time.perf_counter() - t:5.2f}s {name}({args}) -> {out[:230]!r}")
            return out

        def check(ok: bool, what: str) -> None:
            print(("PASS " if ok else "FAIL ") + what)
            if not ok:
                failures.append(what)

        check('"scrcpy"' in await call("device_status"), "scrcpy backend active")
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
        await call("press_key", key="home")
    print("\nFAILED: " + "; ".join(failures) if failures else "\nALL PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

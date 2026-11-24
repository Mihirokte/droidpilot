"""The MCP server over real stdio."""

from __future__ import annotations

import asyncio
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_handshake_lists_tools_and_reports_missing_device() -> None:
    async def run() -> tuple[set[str], str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "droidpilot"],
            env={"DROIDPILOT_SERIAL": "no-such-device", "DROIDPILOT_HOME": tempfile.mkdtemp(), "PATH": "/usr/bin:/bin"},
        )
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            tools = await session.list_tools()
            res = await session.call_tool("device_status", {})
            obs = await session.call_tool("observe", {})  # error path must be text, not a schema failure
            return {t.name for t in tools.tools}, res.content[0].text + "||" + obs.content[0].text  # type: ignore[union-attr]

    names, text = asyncio.run(run())
    assert {"observe", "tap", "tap_element", "swipe", "scroll", "pinch", "gesture", "type_text", "press_key", "open_app"} <= names
    status, observed = text.split("||")
    assert status.startswith("ERROR:") and observed.startswith("ERROR:")
    assert {"tap_text", "wait_for", "look", "web_read", "web_click", "web_fill", "open_url", "notes", "record", "recipes"} <= names and "ui_tree" not in names

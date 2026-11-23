"""Tests that need no phone: wire format, parsing, geometry, MCP handshake."""

from __future__ import annotations

import asyncio
import struct
import sys
import tempfile

import numpy as np
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from droidpilot import perception as P
from droidpilot import scrcpy as S

HIERARCHY = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
 <node class="android.widget.FrameLayout" text="" content-desc="" bounds="[0,0][1080,2400]" clickable="false">
  <node class="android.widget.Button" text="Send" resource-id="com.x:id/send" clickable="true" bounds="[100,200][300,300]"/>
  <node class="android.widget.EditText" text="" content-desc="Message" bounds="[0,400][1080,500]"/>
  <node class="android.view.View" text="" content-desc="" bounds="[0,0][10,10]"/>
 </node>
</hierarchy>
UI hierchary dumped to: /dev/tty"""


class FakeAdb:
    def exec_out(self, command: str, timeout: float = 30) -> bytes:
        return HIERARCHY.encode()


def test_touch_message_is_32_bytes_and_roundtrips() -> None:
    msg = S.encode_touch(S.ACTION_DOWN, 1, 540, 1200, 1080, 2400, 1.0)
    assert len(msg) == 32
    t, action, pid, x, y, w, h, pressure, ab, buttons = struct.unpack(">BBqiiHHHii", msg)
    assert (t, action, pid, x, y, w, h, pressure) == (2, 0, 1, 540, 1200, 1080, 2400, 0xFFFF)


def test_up_event_has_zero_pressure() -> None:
    msg = S.encode_touch(S.ACTION_UP, 0, 1, 1, 10, 10, 0.0)
    assert struct.unpack(">BBqiiHHHii", msg)[7] == 0


def test_key_text_scroll_clipboard_layouts() -> None:
    assert len(S.encode_key(S.KEY_DOWN, 4)) == 14
    assert S.encode_text("hi") == b"\x01\x00\x00\x00\x02hi"
    assert len(S.encode_scroll(1, 1, 10, 10, 0, -5)) == 1 + 8 + 4 + 4 + 4
    clip = S.encode_set_clipboard("é", paste=True)
    assert clip[0] == 9 and clip[9] == 1 and clip[-2:] == "é".encode()


def test_ui_parse_filters_noise_and_flags() -> None:
    els = P.dump_ui(FakeAdb())  # type: ignore[arg-type]
    assert [e.cls for e in els] == ["Button", "EditText"]
    assert els[0].flags == ("click",) and els[0].center == (200, 250)
    assert "edit" in els[1].flags


def test_geometry_roundtrip_and_clamp() -> None:
    geo = P.Geometry(1080, 2400, 1600)
    assert geo.view_size == (720, 1600)
    assert geo.to_device(360, 800) == (540, 1200)
    assert geo.to_device(99999, -5) == (1079, 0)
    assert geo.to_view(540, 1200) == (360, 800)


def test_signature_diff_detects_change_ignores_status_bar() -> None:
    from PIL import Image

    a = Image.new("RGB", (100, 200), (0, 0, 0))
    b = a.copy()
    b.paste((255, 255, 255), (0, 0, 100, 5))  # status bar only
    c = a.copy()
    c.paste((255, 255, 255), (0, 100, 100, 160))
    assert P.diff(P.signature(a), P.signature(b)) < 0.5
    assert P.diff(P.signature(a), P.signature(c)) > 5
    assert isinstance(P.signature(a), np.ndarray)


def test_mcp_handshake_lists_tools_and_reports_missing_device() -> None:
    async def run() -> tuple[set[str], str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "droidpilot"],
            env={"DROIDPILOT_SERIAL": "no-such-device", "DROIDPILOT_HOME": tempfile.mkdtemp(), "PATH": "/usr/bin:/bin"},
        )
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = await session.list_tools()
                res = await session.call_tool("device_status", {})
                obs = await session.call_tool("observe", {})  # error path must be text, not a schema failure
                return {t.name for t in tools.tools}, res.content[0].text + "||" + obs.content[0].text  # type: ignore[union-attr]

    names, text = asyncio.run(run())
    assert {"observe", "tap", "tap_element", "swipe", "scroll", "pinch", "gesture", "type_text", "press_key", "open_app"} <= names
    status, observed = text.split("||")
    assert status.startswith("ERROR:") and observed.startswith("ERROR:")
    assert {"tap_text", "wait_for"} <= names and "ui_tree" not in names


def _el(i, cls, text, flags, b):
    return P.UiElement(i, cls, text, "", "", tuple(flags), b)


def test_compact_merges_card_children_and_keeps_nested_buttons() -> None:
    els = [
        _el(0, "WebView", "", ["click", "scroll"], (0, 0, 1080, 2300)),  # too big: never a merge target
        _el(1, "View", "", ["click"], (0, 400, 500, 900)),  # card
        _el(2, "TextView", "Levi's", [], (10, 410, 400, 450)),
        _el(3, "TextView", "512 Slim Jeans", [], (10, 460, 400, 500)),
        _el(4, "TextView", "512 Slim Jeans", [], (10, 505, 400, 540)),  # duplicate label
        _el(5, "Button", "Add to cart", ["click"], (10, 800, 490, 880)),  # nested button stays
        _el(6, "TextView", "Loose text", [], (600, 1000, 900, 1040)),  # no clickable parent, stays
    ]
    out = P.compact(els, 1080, 2400)
    assert [e.index for e in out] == list(range(len(out)))
    labels = [e.text for e in out]
    assert "Levi's | 512 Slim Jeans" in labels
    assert "Add to cart" in labels and "Loose text" in labels
    assert len(out) == 4  # webview, card, button, loose text


def test_parse_ui_matches_dump_ui_on_same_xml() -> None:
    xml = HIERARCHY[HIERARCHY.index("<?xml") : HIERARCHY.rindex("</hierarchy>") + len("</hierarchy>")]
    assert P.parse_ui(xml) == P.dump_ui(FakeAdb())  # type: ignore[arg-type]


def test_tree_falls_back_to_shell_when_fast_backend_fails(monkeypatch) -> None:
    from droidpilot import phone as phone_mod
    from droidpilot.adb import DeviceError

    class Broken:
        def __init__(self, serial):
            raise DeviceError("no u2")

    monkeypatch.setattr(phone_mod, "FastTree", Broken)
    monkeypatch.setattr(P, "fetch_xml_shell", lambda adb: "<hierarchy/>")
    ph = phone_mod.Phone()
    ph.adb = type("A", (), {"serial": "x"})()  # type: ignore[assignment]
    assert ph._tree_xml() == "<hierarchy/>"
    assert ph.tree_backend == "shell" and "fast tree off" in ph.backend_note
    assert ph._tree_xml() == "<hierarchy/>"  # stays on the shell backend, no retry storm

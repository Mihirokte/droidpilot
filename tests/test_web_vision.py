"""WebSocket framing, DevTools page summary, web guard, and the vision endpoint backend."""

from __future__ import annotations

import json
import struct
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from droidpilot import vision as V
from droidpilot import web as W
from droidpilot.adb import DeviceError


# ---- WebSocket framing -----------------------------------------------------
def test_frame_masks_payload_and_parse_roundtrips_unmasked() -> None:
    f = W.frame(b"hi", mask=b"\x01\x02\x03\x04")
    assert f[:2] == bytes([0x81, 0x82]) and f[2:6] == b"\x01\x02\x03\x04"
    assert bytes(b ^ m for b, m in zip(f[6:], b"\x01\x02", strict=True)) == b"hi"
    server = bytes([0x81, 5]) + b"hello" + b"extra"
    assert W.parse_frame(server) == (1, b"hello", 7)


def test_parse_frame_handles_16_and_64_bit_lengths_and_partial_input() -> None:
    mid = b"x" * 300
    buf = bytes([0x81, 126]) + struct.pack(">H", 300) + mid
    assert W.parse_frame(buf) == (1, mid, len(buf))
    assert W.parse_frame(buf[:-1]) is None  # incomplete payload
    big = b"y" * 70000
    buf = bytes([0x81, 127]) + struct.pack(">Q", 70000) + big
    assert W.parse_frame(buf)[1] == big
    assert W.parse_frame(b"\x81") is None
    long_client = W.frame(b"z" * 200, mask=b"\0\0\0\0")
    assert long_client[1] == 0x80 | 126 and struct.unpack(">H", long_client[2:4])[0] == 200


def test_summarize_lists_items_and_truncates() -> None:
    data = {"url": "https://x", "title": "T", "text": "a" * 50,
            "items": [{"tag": "a", "type": "", "name": "Learn more", "href": "https://y"},
                      {"tag": "input", "type": "search", "name": "", "href": ""}]}
    out = W.summarize(data, limit=10)
    assert "title: T" in out and "40 more characters" in out
    assert "[0] a 'Learn more' -> https://y" in out and "[1] input[search] ''" in out


def test_web_click_guard_blocks_before_touching_the_phone(monkeypatch) -> None:
    from droidpilot import server

    def boom(*a, **k):
        raise AssertionError("must not reach Chrome")

    monkeypatch.setattr(W, "Chrome", boom)
    out = server.web_click("Place your order")
    assert out.startswith("BLOCKED")


# ---- vision endpoint -------------------------------------------------------
def test_build_request_and_parse_response() -> None:
    body = V.build_request("m", "where?", b"\xff\xd8jpeg")
    assert body["model"] == "m" and body["max_tokens"] == V.MAX_TOKENS
    url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert V.parse_response({"choices": [{"message": {"content": " ok "}}]}) == "ok"
    with pytest.raises(DeviceError):
        V.parse_response({"error": "x"})


def test_endpoint_url_must_be_https_or_localhost(monkeypatch) -> None:
    monkeypatch.setenv("DROIDPILOT_VISION_URL", "http://evil.example.com/v1")
    with pytest.raises(DeviceError, match="https"):
        V.endpoint_config()
    monkeypatch.delenv("DROIDPILOT_VISION_URL")
    assert V.endpoint_config() is None


def test_ask_endpoint_against_local_stub(monkeypatch) -> None:
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            got["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got["auth"] = self.headers.get("Authorization")
            out = json.dumps({"choices": [{"message": {"content": "The cart has 1 item."}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DROIDPILOT_VISION_URL", f"http://127.0.0.1:{srv.server_port}/v1/chat/completions")
        monkeypatch.setenv("DROIDPILOT_VISION_MODEL", "qwen2.5vl")
        monkeypatch.setenv("DROIDPILOT_VISION_KEY", "k")
        assert V.ask_endpoint("How many items?", b"jpeg") == "The cart has 1 item."
        assert got["body"]["model"] == "qwen2.5vl" and got["auth"] == "Bearer k"
    finally:
        srv.shutdown()

"""The look() endpoint backend."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from droidpilot import config
from droidpilot import vision as V
from droidpilot.errors import DeviceError


def test_build_request_and_parse_response() -> None:
    body = V.build_request("m", "where?", b"\xff\xd8jpeg")
    assert body["model"] == "m" and body["max_tokens"] == V.MAX_TOKENS
    url = body["messages"][1]["content"][1]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert V.parse_response({"choices": [{"message": {"content": " ok "}}]}) == "ok"
    with pytest.raises(DeviceError):
        V.parse_response({"error": "x"})



def test_endpoint_url_must_be_https_or_localhost(monkeypatch) -> None:
    monkeypatch.setattr(config, "VISION_URL", "http://evil.example.com/v1")
    with pytest.raises(DeviceError, match="https"):
        V.endpoint_config()
    monkeypatch.setattr(config, "VISION_URL", "")
    assert V.endpoint_config() is None



def test_ask_endpoint_against_local_stub(monkeypatch) -> None:
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
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
        monkeypatch.setattr(config, "VISION_URL", f"http://127.0.0.1:{srv.server_port}/v1/chat/completions")
        monkeypatch.setattr(config, "VISION_MODEL", "qwen2.5vl")
        monkeypatch.setattr(config, "VISION_KEY", "k")
        assert V.ask_endpoint("How many items?", b"jpeg") == "The cart has 1 item."
        assert got["body"]["model"] == "qwen2.5vl" and got["auth"] == "Bearer k"
    finally:
        srv.shutdown()

"""Chrome on the phone through the DevTools protocol, over adb. No extra install.

Chrome for Android opens the abstract socket `chrome_devtools_remote` when USB debugging is on.
adb forwards it to a local port. We speak plain JSON over a minimal WebSocket client.

Use it for web pages in Chrome: read the page as text, find links and buttons, run a CSS click,
fill a field. Touch tools still work on the same page. This is a supplement, not a replacement.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import re
import socket
import struct
from dataclasses import dataclass

from .adb import Adb
from .errors import DeviceError

SOCKET = "chrome_devtools_remote"
MAX_TEXT = 6000  # characters of page text returned to the agent


# ---- minimal WebSocket client (RFC 6455, client side, text frames only) -----
def frame(payload: bytes, opcode: int = 0x1, mask: bytes | None = None) -> bytes:
    """One final, masked client frame. Pure function; `mask` is injectable for tests."""
    mask = mask or os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def parse_frame(buf: bytes) -> tuple[int, bytes, int] | None:
    """Parse one unmasked server frame from the start of `buf`.
    Return (opcode, payload, bytes used), or None if `buf` holds less than one full frame."""
    if len(buf) < 2:
        return None
    opcode, n, i = buf[0] & 0x0F, buf[1] & 0x7F, 2
    if n == 126:
        if len(buf) < 4:
            return None
        n, i = struct.unpack(">H", buf[2:4])[0], 4
    elif n == 127:
        if len(buf) < 10:
            return None
        n, i = struct.unpack(">Q", buf[2:10])[0], 10
    if buf[1] & 0x80:  # servers must not mask, but handle it
        mask, i = buf[i : i + 4], i + 4
        if len(buf) < i + n:
            return None
        return opcode, bytes(b ^ mask[k % 4] for k, b in enumerate(buf[i : i + n])), i + n
    if len(buf) < i + n:
        return None
    return opcode, buf[i : i + n], i + n


class WebSocket:
    def __init__(self, host: str, port: int, path: str, timeout: float = 10) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise DeviceError("Chrome closed the DevTools connection during the handshake")
            head += chunk
        status, _, self._buf = head.partition(b"\r\n\r\n")
        if b" 101 " not in status.split(b"\r\n")[0]:
            raise DeviceError(f"DevTools handshake failed: {status.splitlines()[0].decode(errors='replace')}")

    def send(self, text: str) -> None:
        self.sock.sendall(frame(text.encode()))

    def recv(self) -> str:
        parts: list[bytes] = []
        while True:
            got = parse_frame(self._buf)
            if got is None:
                chunk = self.sock.recv(65536)
                if not chunk:
                    raise DeviceError("Chrome closed the DevTools connection")
                self._buf += chunk
                continue
            opcode, payload, used = got
            self._buf = self._buf[used:]
            if opcode == 0x9:  # ping -> pong
                self.sock.sendall(frame(payload, 0xA))
            elif opcode == 0x8:
                raise DeviceError("Chrome closed the DevTools connection")
            elif opcode in (0x1, 0x0, 0x2):
                parts.append(payload)
                return b"".join(parts).decode("utf-8", errors="replace")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()


# ---- page scripts (run in the page; return JSON-able values) ----------------
READ_JS = r"""
(() => {
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const name = e => (e.innerText || e.value || e.getAttribute('aria-label') || e.title || e.placeholder || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  const items = [];
  document.querySelectorAll('a[href],button,input,select,textarea,[role=button],[onclick]').forEach(e => {
    if (!vis(e)) return;
    const n = name(e); if (!n && e.tagName !== 'INPUT') return;
    items.push({tag: e.tagName.toLowerCase(), type: e.type || '', name: n, href: e.href ? String(e.href).slice(0, 120) : ''});
  });
  return {url: location.href, title: document.title, text: (document.body ? document.body.innerText : '').replace(/\n{3,}/g, '\n\n'), items: items.slice(0, 80)};
})()
"""

CLICK_JS = r"""
((needle, nth) => {
  const vis = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const name = e => (e.innerText || e.value || e.getAttribute('aria-label') || e.title || '').trim().replace(/\s+/g, ' ');
  const want = needle.toLowerCase();
  const hits = [...document.querySelectorAll('a[href],button,input[type=submit],input[type=button],[role=button],[onclick]')]
    .filter(e => vis(e) && name(e).toLowerCase().includes(want));
  hits.sort((a, b) => (name(a).toLowerCase() !== want) - (name(b).toLowerCase() !== want));
  const e = hits[nth]; if (!e) return {ok: false, count: hits.length};
  e.scrollIntoView({block: 'center'}); e.click();
  return {ok: true, name: name(e).slice(0, 80), count: hits.length};
})
"""

FILL_JS = r"""
((needle, value) => {
  const want = needle.toLowerCase();
  const label = e => [e.name, e.id, e.placeholder, e.getAttribute('aria-label'),
    (e.labels && e.labels[0] ? e.labels[0].innerText : '')].filter(Boolean).join(' ').toLowerCase();
  const e = [...document.querySelectorAll('input,textarea')].find(x => label(x).includes(want));
  if (!e) return {ok: false};
  e.focus();
  const proto = e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, value);  // works with React-style inputs
  e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true}));
  return {ok: true, field: label(e).slice(0, 60)};
})
"""


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    ws_path: str


def summarize(data: dict, limit: int = MAX_TEXT) -> str:
    """Format the READ_JS result for the agent. Pure."""
    text = data.get("text") or ""
    lines = [f"url: {data.get('url', '')}", f"title: {data.get('title', '')}", ""]
    lines.append(text[:limit] + (f"\n... ({len(text) - limit} more characters)" if len(text) > limit else ""))
    items = data.get("items") or []
    if items:
        lines.append("\ninteractive:")
        for i, it in enumerate(items):
            kind = it["tag"] + (f"[{it['type']}]" if it.get("type") and it["tag"] == "input" else "")
            lines.append(f"[{i}] {kind} {it['name']!r}" + (f" -> {it['href']}" if it.get("href") else ""))
    return "\n".join(lines)


class Chrome:
    """One DevTools session per call. Cheap: a forward plus one WebSocket."""

    def __init__(self, adb: Adb) -> None:
        self.adb = adb

    def _port(self) -> int:
        try:
            return int(self.adb.run("forward", "tcp:0", f"localabstract:{SOCKET}").strip())
        except (DeviceError, ValueError) as exc:
            raise DeviceError(f"Chrome DevTools is not reachable ({exc}). Open Chrome on the phone first.") from exc

    def _pages(self, port: int) -> list[Page]:
        sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        try:
            sock.sendall(b"GET /json/list HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
            raw = b""
            while True:  # Chrome keeps the socket open, so stop at Content-Length
                head, sep, body = raw.partition(b"\r\n\r\n")
                if sep:
                    m = re.search(rb"(?i)content-length:\s*(\d+)", head)
                    if m and len(body) >= int(m.group(1)):
                        break
                chunk = sock.recv(65536)
                if not chunk:
                    break
                raw += chunk
        finally:
            sock.close()
        body = raw.partition(b"\r\n\r\n")[2]
        try:
            targets = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise DeviceError("Chrome is not running. Open Chrome on the phone first.") from exc
        pages = []
        for t in targets:
            ws = t.get("webSocketDebuggerUrl") or ""
            if t.get("type") == "page" and ws:
                pages.append(Page(t.get("url", ""), t.get("title", ""), "/" + ws.split("/", 3)[3]))
        return pages

    def evaluate(self, expression: str) -> object:
        """Run JavaScript in the front Chrome tab and return the value."""
        port = self._port()
        try:
            pages = self._pages(port)
            if not pages:
                raise DeviceError("Chrome has no open tab")
            ws = WebSocket("127.0.0.1", port, pages[0].ws_path)  # /json/list puts the front tab first
            try:
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                    "params": {"expression": expression, "returnByValue": True, "awaitPromise": True}}))
                while True:
                    msg = json.loads(ws.recv())
                    if msg.get("id") == 1:
                        break
            finally:
                ws.close()
        finally:
            with contextlib.suppress(DeviceError):
                self.adb.run("forward", "--remove", f"tcp:{port}")
        result = msg.get("result", {})
        if "exceptionDetails" in result:
            raise DeviceError(f"page script failed: {result['exceptionDetails'].get('text', 'error')}")
        return result.get("result", {}).get("value")

    def read(self) -> str:
        data = self.evaluate(READ_JS)
        if not isinstance(data, dict):
            raise DeviceError("could not read the page")
        return summarize(data)

    def click(self, text: str, nth: int = 0) -> dict:
        out = self.evaluate(f"({CLICK_JS})({json.dumps(text)}, {int(nth)})")
        return out if isinstance(out, dict) else {"ok": False, "count": 0}

    def fill(self, field: str, value: str) -> dict:
        out = self.evaluate(f"({FILL_JS})({json.dumps(field)}, {json.dumps(value)})")
        return out if isinstance(out, dict) else {"ok": False}

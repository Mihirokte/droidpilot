"""Minimal scrcpy control-socket client (control only, no video).

Protocol source: scrcpy ControlMessageReader.java (v5.0.1). The wire format is
internal to scrcpy and changes between versions, so SERVER_VERSION is pinned and
must equal the version of the scrcpy-server jar we push.
"""

from __future__ import annotations

import os
import random
import socket
import struct
import threading
import time
from pathlib import Path

from .adb import Adb, DeviceError

SERVER_VERSION = "5.0.1"
DEFAULT_SERVER = Path.home() / ".local/opt/scrcpy-macos-x86_64-v5.0.1/scrcpy-server"
REMOTE_JAR = "/data/local/tmp/droidpilot-scrcpy-server.jar"

# MotionEvent actions
ACTION_DOWN, ACTION_UP, ACTION_MOVE = 0, 1, 2
# KeyEvent actions
KEY_DOWN, KEY_UP = 0, 1

TYPE_KEYCODE, TYPE_TEXT, TYPE_TOUCH, TYPE_SCROLL = 0, 1, 2, 3
TYPE_SET_CLIPBOARD = 9
INJECT_TEXT_MAX = 300


def encode_touch(
    action: int, pointer_id: int, x: int, y: int, width: int, height: int,
    pressure: float, action_button: int = 0, buttons: int = 0,
) -> bytes:
    fixed = 0xFFFF if pressure >= 1.0 else int(max(0.0, pressure) * 0x10000)
    return struct.pack(">BBqiiHHHii", TYPE_TOUCH, action, pointer_id, x, y, width, height, fixed, action_button, buttons)


def encode_key(action: int, keycode: int, repeat: int = 0, meta: int = 0) -> bytes:
    return struct.pack(">BBiii", TYPE_KEYCODE, action, keycode, repeat, meta)


def encode_text(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack(">BI", TYPE_TEXT, len(data)) + data


def encode_scroll(x: int, y: int, width: int, height: int, h: float, v: float, buttons: int = 0) -> bytes:
    def fx(value: float) -> int:
        return max(-32768, min(32767, int(value / 16.0 * 32767)))

    return struct.pack(">BiiHHhhi", TYPE_SCROLL, x, y, width, height, fx(h), fx(v), buttons)


def encode_set_clipboard(text: str, paste: bool, sequence: int = 1) -> bytes:
    data = text.encode("utf-8")
    return struct.pack(">BqBI", TYPE_SET_CLIPBOARD, sequence, 1 if paste else 0, len(data)) + data


class ScrcpyControl:
    """Persistent control socket to an on-device scrcpy server."""

    def __init__(self, adb: Adb, server_jar: str | None = None) -> None:
        self.adb = adb
        self.server_jar = Path(server_jar or os.environ.get("SCRCPY_SERVER_PATH") or DEFAULT_SERVER)
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._proc = None
        self._port: int | None = None

    @property
    def connected(self) -> bool:
        return self._sock is not None

    def start(self, timeout: float = 10.0) -> None:
        if self.connected:
            return
        if not self.server_jar.exists():
            raise DeviceError(f"scrcpy-server jar not found at {self.server_jar}")
        self.adb.run("push", str(self.server_jar), REMOTE_JAR)
        scid = random.randint(1, 0x7FFFFFFF)
        socket_name = f"scrcpy_{scid:08x}"
        port_text = self.adb.run("forward", "tcp:0", f"localabstract:{socket_name}").strip()
        self._port = int(port_text)
        command = (
            f"CLASSPATH={REMOTE_JAR} app_process / com.genymobile.scrcpy.Server {SERVER_VERSION} "
            f"scid={scid:08x} log_level=info video=false audio=false control=true "
            "tunnel_forward=true cleanup=false send_device_meta=false"
        )
        self._proc = self.adb.popen_shell(command)
        deadline = time.monotonic() + timeout
        last_error = "no connection attempt"
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                out = self._proc.stdout.read().decode(errors="replace") if self._proc.stdout else ""
                raise DeviceError(f"scrcpy server exited early: {out.strip()[-500:]}")
            try:
                sock = socket.create_connection(("127.0.0.1", self._port), timeout=2)
                sock.settimeout(2)
                dummy = sock.recv(1)  # forward tunnel sends one dummy byte once the server accepts
                if not dummy:
                    raise ConnectionError("empty dummy byte")
                sock.settimeout(None)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._sock = sock
                threading.Thread(target=self._drain, args=(sock,), daemon=True).start()
                return
            except (OSError, ConnectionError) as exc:
                last_error = str(exc)
                time.sleep(0.2)
        self.stop()
        raise DeviceError(f"could not connect to scrcpy server: {last_error}")

    def _drain(self, sock: socket.socket) -> None:
        """Discard device->client messages (clipboard events) so the socket never blocks."""
        try:
            while sock.recv(4096):
                pass
        except OSError:
            pass
        if self._sock is sock:
            self._sock = None

    def send(self, payload: bytes) -> None:
        if not self._sock:
            raise DeviceError("scrcpy control socket is not connected")
        with self._lock:
            try:
                self._sock.sendall(payload)
            except OSError as exc:
                self._sock = None
                raise DeviceError(f"scrcpy control socket lost: {exc}") from exc

    def stop(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None
        if self._port is not None:
            try:
                self.adb.run("forward", "--remove", f"tcp:{self._port}")
            except DeviceError:
                pass
            self._port = None

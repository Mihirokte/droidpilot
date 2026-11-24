"""scrcpy wire format and WebSocket framing."""

from __future__ import annotations

import struct

from droidpilot import scrcpy as S
from droidpilot import web as W


def test_touch_message_is_32_bytes_and_roundtrips() -> None:
    msg = S.encode_touch(S.ACTION_DOWN, 1, 540, 1200, 1080, 2400, 1.0)
    assert len(msg) == 32
    t, action, pid, x, y, w, h, pressure, _ab, _buttons = struct.unpack(">BBqiiHHHii", msg)
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

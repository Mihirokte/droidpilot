"""Phone controller logic that needs no phone: locking, connect races, backend fallback."""

from __future__ import annotations

import pytest

from droidpilot import perception as P
from droidpilot.errors import DeviceError


def test_second_controller_on_same_phone_is_refused(tmp_path) -> None:
    import subprocess
    import sys

    from droidpilot.devlock import DeviceLock

    first = DeviceLock("b9a16a4d", tmp_path)
    first.acquire()
    other = subprocess.run(  # a separate process, like a second MCP server
        [sys.executable, "-c", f"from droidpilot.devlock import DeviceLock; from pathlib import Path; DeviceLock('b9a16a4d', Path({str(tmp_path)!r})).acquire(wait_s=0.3)"],
        capture_output=True, text=True,
    )
    assert other.returncode != 0 and "Another droidpilot is controlling this phone" in other.stderr
    DeviceLock("other-serial", tmp_path).acquire()  # a different phone is fine
    import threading
    import time as _time

    threading.Timer(0.5, first.release).start()  # the holder shuts down shortly after
    t = _time.monotonic()
    again = DeviceLock("b9a16a4d", tmp_path)
    again.acquire(wait_s=5)  # waits for the release instead of failing
    assert 0.3 < _time.monotonic() - t < 3
    again.release()



def test_parallel_connect_in_one_process_does_not_lock_itself_out(tmp_path, monkeypatch) -> None:
    """The warm-up thread and the first tool call both call connect()."""
    import threading

    from droidpilot import phone as phone_mod
    from droidpilot.adb import AdbDevice
    from droidpilot.devlock import DeviceLock

    monkeypatch.setattr(phone_mod, "list_devices", lambda: [AdbDevice("s1", "device", "")])
    monkeypatch.setattr(phone_mod, "Adb", lambda serial: type("FakeAdb", (), {"serial": serial})())  # CI has no adb
    monkeypatch.setattr(phone_mod, "DeviceLock", lambda serial: DeviceLock(serial, tmp_path))
    p = phone_mod.Phone()
    errors: list[Exception] = []

    def go() -> None:
        try:
            p.connect()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and p.adb is not None
    p._lock.release()



def test_connect_failure_does_not_leave_the_phone_locked(tmp_path, monkeypatch) -> None:
    import pytest

    from droidpilot import phone as phone_mod
    from droidpilot.adb import AdbDevice, DeviceError
    from droidpilot.devlock import DeviceLock

    def no_adb(serial):
        raise DeviceError("adb not found")

    monkeypatch.setattr(phone_mod, "list_devices", lambda: [AdbDevice("s2", "device", "")])
    monkeypatch.setattr(phone_mod, "Adb", no_adb)
    monkeypatch.setattr(phone_mod, "DeviceLock", lambda serial: DeviceLock(serial, tmp_path))
    with pytest.raises(DeviceError, match="adb not found"):
        phone_mod.Phone().connect()
    free = DeviceLock("s2", tmp_path)
    free.acquire(wait_s=0)  # nobody holds it
    free.release()



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



def test_open_url_rejects_unsafe_schemes() -> None:
    from droidpilot.phone import Phone

    for bad in ("file:///etc/passwd", "javascript:alert(1)", "intent://x#Intent;end", "content://x"):
        with pytest.raises(DeviceError, match="allows"):
            Phone().open_url(bad)


def test_scrcpy_start_is_retried_and_fallback_recovers_later(monkeypatch) -> None:
    from droidpilot import phone as phone_mod

    attempts = {"n": 0}

    class Flaky:
        connected = True

        def __init__(self, adb):
            pass

        def start(self):
            attempts["n"] += 1
            if attempts["n"] <= 2:  # both tries of the first call fail
                raise DeviceError("server still shutting down")

    monkeypatch.setattr(phone_mod.S, "ScrcpyControl", Flaky)
    monkeypatch.setattr(phone_mod.time, "sleep", lambda s: None)
    p = phone_mod.Phone()
    p.adb = object()  # type: ignore[assignment]
    assert p._control() is None and p.input_backend == "adb-input" and attempts["n"] == 2
    assert p._control() is None and attempts["n"] == 2  # inside the retry window: no new attempt
    p._scrcpy_retry_at = 0  # the window has passed
    assert p._control() is not None and p.input_backend == "scrcpy" and p.backend_note == ""

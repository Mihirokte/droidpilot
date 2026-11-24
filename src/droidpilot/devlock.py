"""One controller per phone. A second droidpilot server on the same phone gets a clear error
instead of fighting the first one (two agents tapping one screen give nonsense to both)."""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

from . import store
from .errors import DeviceError


class DeviceLock:
    def __init__(self, serial: str, directory: Path | None = None) -> None:
        safe = "".join(c if c.isalnum() else "_" for c in serial)
        self.path = (directory or store.subdir("locks")) / f"{safe}.lock"
        self._fh = None

    def acquire(self, wait_s: float = 5.0) -> None:
        """Take the lock. Wait up to `wait_s` first: a server that is shutting down
        (an agent restart) still holds it for a moment."""
        if self._fh:
            return
        fh = open(self.path, "a+")  # noqa: SIM115 - held open for the life of the server
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() < deadline:
                    time.sleep(0.2)
                    continue
                fh.seek(0)
                owner = fh.read().strip() or "another process"
                fh.close()
                raise DeviceError(
                    f"Another droidpilot is controlling this phone ({owner}). "
                    "Only one agent can drive a phone at a time. Stop the other one, then retry."
                ) from None
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid {os.getpid()}")
        fh.flush()
        self._fh = fh  # the OS releases the lock if this process dies

    def release(self) -> None:
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None

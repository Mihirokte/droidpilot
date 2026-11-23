"""Optional fast UI-tree backend: uiautomator2 (install with `pip install droidpilot[fast]`).

`uiautomator dump` starts a new process on the phone for every call (about 2.7 s).
uiautomator2 keeps one server running and answers in about 0.6 s. It installs no app.
It pushes `u2.jar` to /data/local/tmp. droidpilot clean removes it.
"""

from __future__ import annotations

from .adb import DeviceError


class FastTree:
    def __init__(self, serial: str) -> None:
        try:
            import uiautomator2 as u2
        except ImportError as exc:  # optional dependency
            raise DeviceError("uiautomator2 is not installed (pip install 'droidpilot[fast]')") from exc
        try:
            self._d = u2.connect(serial)
            self._d.info  # forces the server to start now, so a failure shows up here
        except Exception as exc:  # u2 raises many types
            raise DeviceError(f"uiautomator2 could not start: {exc}") from exc

    def xml(self) -> str:
        try:
            return self._d.dump_hierarchy()
        except Exception as exc:
            raise DeviceError(f"uiautomator2 dump failed: {exc}") from exc

    def stop(self) -> None:
        try:
            self._d.stop_uiautomator()
        except Exception:  # best effort at shutdown
            pass

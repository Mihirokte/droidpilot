"""Every setting droidpilot reads from the environment, in one place.

Values are read when the module is imported. Tests that need other values patch the attributes.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


# Device
SERIAL: str | None = os.environ.get("DROIDPILOT_SERIAL") or None
VIEW_LONG_SIDE = int(_env("DROIDPILOT_VIEW_LONG_SIDE", "1600"))  # screenshot long side = coordinate space

# Perception
TREE = _env("DROIDPILOT_TREE", "auto")  # auto | shell | u2
COMPACT = _env("DROIDPILOT_COMPACT", "1") != "0"  # merge card children into one line

# Actions
VERIFY = _env("DROIDPILOT_VERIFY", "off")  # off: fixed wait | full: screenshot diff loop
SETTLE_MS = int(_env("DROIDPILOT_SETTLE_MS", "400"))
GUARD = _env("DROIDPILOT_GUARD", "on") != "off"

# Storage
HOME = Path(os.environ.get("DROIDPILOT_HOME") or Path.home() / ".cache" / "droidpilot")

# Vision (look)
VISION_URL = os.environ.get("DROIDPILOT_VISION_URL", "").strip()
VISION_MODEL = _env("DROIDPILOT_VISION_MODEL", "llava")
VISION_KEY = os.environ.get("DROIDPILOT_VISION_KEY", "")

"""Safety guard: refuse taps that look like buying, paying, sending or deleting.

A false alarm costs one retry with confirm=true. A missed purchase costs money.
"""

from __future__ import annotations

import os
import re

RISKY = re.compile(
    r"\b(buy now|buy for|buy with|place (your )?order|order now|pay now|make payment|proceed to pay|"
    r"confirm (order|payment|purchase)|purchase|send|delete|uninstall|factory reset|transfer|withdraw|subscribe)\b",
    re.IGNORECASE,
)
ENABLED = os.environ.get("DROIDPILOT_GUARD", "on") != "off"


def check(label: str | None) -> str | None:
    """Return the risky phrase found in `label`, or None."""
    if not ENABLED or not label:
        return None
    m = RISKY.search(label)
    return m.group(0) if m else None

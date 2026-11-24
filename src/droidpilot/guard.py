"""Safety guard: refuse taps that look like buying, paying, sending, booking or deleting.

A false alarm costs one retry with confirm=true. A missed purchase costs money.
The rules cover checkout steps too ("Proceed to Buy", "Checkout"), not only the final button,
and labels common in Indian apps (UPI, Pay, Book ticket, Place order).
"""

from __future__ import annotations

import re

from . import config

RISKY = re.compile(
    r"\b("
    # buying and checkout
    r"buy|purchase|checkout|check out|proceed to (buy|pay|checkout|payment)|place (your )?order|order now|confirm (order|purchase|booking)|"
    r"continue to (pay|payment|checkout)|"
    # paying and money movement
    r"pay|pay now|make payment|payment|upi|transfer|withdraw|send money|recharge now|top ?up|"
    # booking
    r"book( now| ticket| tickets| ride| cab)?|reserve|"
    # messages and posts
    r"send|post|share now|publish|reply all|"
    # destruction and account changes
    r"delete|remove account|uninstall|factory reset|erase|unsubscribe|subscribe|cancel (order|booking|subscription)|log ?out|sign ?out"
    r")\b",
    re.IGNORECASE,
)
# Safe navigation that contains a risky word. A segment is skipped only if it is exactly one of these
# (after trimming), so "Place your order" is never mistaken for "Your orders".
SAFE = re.compile(
    r"(add to (cart|bag|basket|wishlist|list)( button)?|save for later|buy again|"
    r"view (cart|bag|orders?)|go to cart|your orders?|order history|track (order|package)|booking history)",
    re.IGNORECASE,
)


def check(label: str | None) -> str | None:
    """Return the risky phrase found in `label`, or None."""
    if not config.GUARD or not label:
        return None
    # Labels from the tree are "a | b | c" (text, description, id). Judge each part on its own.
    for segment in label.split("|"):
        part = segment.strip()
        if SAFE.fullmatch(part):
            continue
        m = RISKY.search(part)
        if m:
            return m.group(0)
    return None

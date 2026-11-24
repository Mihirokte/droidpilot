"""The safety guard, alone and wired into the tap and web paths."""

from __future__ import annotations

import time

from droidpilot import guard
from droidpilot import snapshot as SN
from droidpilot import web as W
from tests.conftest import el, snap

CARD = el(0, "View", "Levi's | 511 Slim", ["click"], (0, 400, 500, 900))


BUY = el(1, "Button", "Buy Now", ["click"], (10, 800, 490, 880))



def test_guard_flags_buying_and_not_cart() -> None:
    assert guard.check("Buy Now")
    assert guard.check("Buy for ₹863")
    assert guard.check("Place your order")
    assert guard.check("Send")
    assert guard.check("Delete account")
    assert guard.check(None) is None
    risky = [
        "Proceed to Buy (1 item)", "Proceed to checkout", "Checkout", "Place Order", "Pay ₹1,439",
        "Pay via UPI", "Pay with Google Pay", "Continue to payment", "Book Ticket", "Book Ride", "Send",
        "Send money", "Post", "Delete", "Log out", "Recharge now", "Confirm booking",
    ]
    for label in risky:
        assert guard.check(label), label
    safe = [
        "Add to cart", "Add to Cart | add to cart button", "Save for later", "Go to Cart", "Your Orders",
        "Track order", "Search Amazon.in", "Settings", "Booking history", "Payday deals ends soon",
    ]
    for label in safe:
        assert guard.check(label) is None, label



def test_tap_on_buy_button_is_blocked_unless_confirmed() -> None:
    import pytest

    from droidpilot import perception as P
    from droidpilot.adb import Blocked
    from droidpilot.phone import Phone

    phone = Phone()
    phone.geo = P.Geometry(1080, 2400, 1600)
    phone.snapshot = snap(3, [CARD, BUY])
    phone._snap_time = time.monotonic()
    vx, vy = phone.geo.to_view(250, 840)  # centre of the Buy Now button
    with pytest.raises(Blocked, match="Buy Now"):
        phone._check_guard(vx, vy, confirm=False)
    phone._check_guard(vx, vy, confirm=True)  # explicit confirm passes
    cx, cy = phone.geo.to_view(250, 420)  # card title area: not risky
    phone._check_guard(cx, cy, confirm=False)
    phone._snap_time = time.monotonic() - 999  # old snapshot: guard stays silent rather than guess
    phone._check_guard(vx, vy, confirm=False)



def test_id_only_buttons_are_found_and_guarded() -> None:
    """Amazon labels both buttons 'Submit'. Only the id says what they do."""
    import pytest

    from droidpilot import perception as P
    from droidpilot.adb import Blocked
    from droidpilot.phone import Phone

    add = el(0, "Button", "Submit", ["click"], (30, 849, 690, 935), rid="add-to-cart-button")
    buy = el(1, "Button", "Submit", ["click"], (30, 961, 690, 1047), rid="buy-now-button")
    s = snap(1, [add, buy])
    assert SN.find(s, "Add to cart")[0].index == 0
    assert SN.find(s, "buy now")[0].index == 1
    phone = Phone()
    phone.geo = P.Geometry(1080, 2400, 1600)
    phone.snapshot, phone._snap_time = s, time.monotonic()
    with pytest.raises(Blocked):
        phone._check_guard(*phone.geo.to_view(360, 1000), confirm=False)
    phone._check_guard(*phone.geo.to_view(360, 890), confirm=False)  # add-to-cart is allowed



def test_tap_element_rejects_old_snapshot_id() -> None:
    import pytest

    from droidpilot.adb import DeviceError
    from droidpilot.phone import Phone

    phone = Phone()
    phone.snapshot = snap(5, [CARD])
    with pytest.raises(DeviceError, match="old"):
        phone.tap_element(0, snapshot_id=4)
    with pytest.raises(DeviceError, match="No element"):
        phone.tap_element(9, snapshot_id=5)



def test_web_click_guard_blocks_before_touching_the_phone(monkeypatch) -> None:
    from droidpilot import server

    def boom(*a, **k):
        raise AssertionError("must not reach Chrome")

    monkeypatch.setattr(W, "Chrome", boom)
    out = server.web_click("Place your order")
    assert out.startswith("BLOCKED")

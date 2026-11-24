"""Pure-logic tests: snapshot, guard, state parser (real phone output), store, trace."""

from __future__ import annotations

import json
import os
import time

from droidpilot import guard, snapshot as SN, state, store
from droidpilot.perception import UiElement
from droidpilot.trace import Trace, redact

# Captured from a realme 9 (Android 14) with the screen off and the lock screen up.
REAL_LOCKED = """  mWakefulness=Dozing
  mCurrentFocus=Window{572d778 u0 NotificationShade}
  mFocusedApp=ActivityRecord{53d5723 u0 in.amazon.mShop.android.shopping/com.amazon.mShop.navigation.MainActivity t24}
        isKeyguardShowing=true
    mRotation=0 mDeferredRotationPauseCount=0
  mInputShown=false
Physical size: 1080x2400
"""
REAL_AWAKE_LANDSCAPE = """  mWakefulness=Awake
  mCurrentFocus=Window{a1b2c3 u0 com.android.settings/com.android.settings.Settings}
  mFocusedApp=ActivityRecord{ff u0 com.android.settings/com.android.settings.Settings t9}
        isKeyguardShowing=false
    mRotation=1 mDeferredRotationPauseCount=0
  mInputShown=true
Physical size: 1080x2400
"""


def el(i, cls, text, flags, bounds, desc="", rid=""):
    return UiElement(i, cls, text, desc, rid, tuple(flags), bounds)


def snap(id_, elements, app="a/b"):
    els = tuple(elements)
    return SN.Snapshot(id_, app, els, SN.digest(els))


# ---- state -----------------------------------------------------------------
def test_state_parses_real_locked_screen_off() -> None:
    st = state.parse(REAL_LOCKED)
    assert not st.awake and st.locked and st.rotation == 0 and not st.keyboard
    assert st.focus == "NotificationShade"
    assert st.app == "in.amazon.mShop.android.shopping/com.amazon.mShop.navigation.MainActivity"
    assert st.size == (1080, 2400)


def test_state_swaps_size_in_landscape_and_reads_keyboard() -> None:
    st = state.parse(REAL_AWAKE_LANDSCAPE)
    assert st.awake and not st.locked and st.keyboard
    assert st.rotation == 1 and st.size == (2400, 1080)
    assert st.app == "com.android.settings/com.android.settings.Settings"
    assert "keyboard=open" in st.banner()


def test_state_survives_empty_output() -> None:
    st = state.parse("")
    assert st.wakefulness == "Unknown" and not st.awake and st.size is None


# ---- snapshot --------------------------------------------------------------
CARD = el(0, "View", "Levi's | 511 Slim", ["click"], (0, 400, 500, 900))
BUY = el(1, "Button", "Buy Now", ["click"], (10, 800, 490, 880))
SEARCH = el(2, "EditText", "", ["click", "edit"], (0, 100, 1000, 160), desc="Search")


def test_diff_same_screen_is_unchanged_and_new_labels_are_found() -> None:
    a = snap(1, [CARD, BUY])
    assert not SN.diff(a, snap(2, [CARD, BUY])).changed
    d = SN.diff(a, snap(2, [CARD, SEARCH]))
    assert d.changed and [SN.label(e) for e in d.added] == ["Search"] and d.removed == ("Buy Now",)


def test_scrolled_screen_counts_as_changed_but_has_no_new_labels() -> None:
    moved = el(0, "View", "Levi's | 511 Slim", ["click"], (0, 100, 500, 600))
    d = SN.diff(snap(1, [CARD]), snap(2, [moved]))
    assert d.changed and d.added == () and d.removed == ()


def test_find_prefers_exact_then_interactive_then_small() -> None:
    plain = el(5, "TextView", "Add to cart", [], (0, 0, 50, 20))
    button = el(6, "Button", "Add to cart", ["click"], (0, 0, 400, 100))
    longer = el(7, "Button", "Add to cart - gift", ["click"], (0, 0, 90, 30))
    hits = SN.find(snap(1, [plain, longer, button]), "add to cart")
    assert [e.index for e in hits] == [6, 5, 7]


def test_element_at_picks_smallest_interactive() -> None:
    s = snap(1, [CARD, BUY])
    assert SN.element_at(s, 100, 850).index == 1  # the button inside the card
    assert SN.element_at(s, 100, 420).index == 0
    assert SN.element_at(s, 900, 2000) is None


# ---- guard -----------------------------------------------------------------
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


# ---- store and trace -------------------------------------------------------
def test_enforce_cap_deletes_oldest_first(tmp_path) -> None:
    for i in range(4):
        f = tmp_path / f"f{i}"
        f.write_bytes(b"x" * 100)
        os.utime(f, (time.time() - (10 - i), time.time() - (10 - i)))
    assert store.enforce_cap(tmp_path, 250) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["f2", "f3"]


def test_trace_redacts_typed_text_and_rotates(tmp_path, monkeypatch) -> None:
    assert redact({"text": "my password", "x": 1}, "type_text") == {"text": "<11 chars>", "x": 1}
    assert redact({"text": "Add to cart"}, "tap_text") == {"text": "Add to cart"}  # tap labels stay readable
    assert redact({"params": {"q": "x"}}, "recipes") == {"params": "<1 values>"}
    t = Trace(tmp_path)
    t.log("type_text", {"text": "secret"}, 12.3, "ok", 5)
    line = json.loads(t.path.read_text().splitlines()[0])
    assert line["args"]["text"] == "<6 chars>" and "secret" not in t.path.read_text()
    assert redact({"value": "p@ss"}, "web_fill") == {"value": "<4 chars>"}  # web_fill values are redacted too
    monkeypatch.setattr("droidpilot.trace.MAX_FILE", 50)
    t.log("tap", {"x": 1}, 1, "ok")
    t.log("tap", {"x": 2}, 1, "ok")
    assert len(list(tmp_path.glob("trace-*.jsonl"))) >= 1


# ---- guard wired into the tap path ----------------------------------------
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


def test_find_matches_hyphenated_labels_and_compacted_segments() -> None:
    wifi = el(0, "View", "Wi-Fi | A005_5G", ["click"], (0, 0, 500, 100))
    s = snap(1, [wifi])
    for q in ("Wi-Fi", "wi fi", "Wi-Fi | A005_5G", "a005 5g"):
        assert SN.find(s, q) and SN.find(s, q)[0].index == 0, q


def test_status_bar_is_dropped_but_app_and_shade_stay() -> None:
    from droidpilot.perception import parse_ui

    xml = """<hierarchy rotation="0">
 <node class="android.widget.FrameLayout" package="com.android.systemui" resource-id="com.android.systemui:id/status_bar" bounds="[0,0][1080,80]">
  <node class="android.widget.TextView" text="11:33" resource-id="com.android.systemui:id/clock" bounds="[10,10][100,70]"/>
  <node class="android.widget.ImageView" content-desc="Battery 91 percent" bounds="[900,10][1000,70]"/>
 </node>
 <node class="android.widget.TextView" package="com.android.systemui" text="Charging notification" resource-id="com.android.systemui:id/notification_text" bounds="[0,100][1080,200]"/>
 <node class="android.widget.Button" package="com.android.settings" text="Wi-Fi" clickable="true" bounds="[0,300][1080,400]"/>
</hierarchy>"""
    labels = [e.text or e.desc for e in parse_ui(xml)]
    assert labels == ["Charging notification", "Wi-Fi"]


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
    monkeypatch.setattr(phone_mod, "DeviceLock", lambda serial: DeviceLock(serial, tmp_path))
    p = phone_mod.Phone()
    errors: list[Exception] = []

    def go() -> None:
        try:
            p.connect()
        except Exception as exc:  # noqa: BLE001 - collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == [] and p.adb is not None
    p._lock.release()

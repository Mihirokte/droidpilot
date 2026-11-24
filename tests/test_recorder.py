"""Recorder: what is captured between record(start) and record(stop)."""

from __future__ import annotations

from droidpilot.recorder import Recorder


def test_records_only_while_active_and_only_successes() -> None:
    r = Recorder()
    r.capture("open_app", {"package": "x"}, "opened", None)
    assert not r.active and r.stop() == ([], 0)
    r.start()
    r.capture("open_app", {"package": "x"}, "opened x", None)
    r.capture("tap_text", {"text": "Buy"}, "BLOCKED: ...", None)
    r.capture("wait_for", {"text": "y"}, "NOT FOUND after 5000ms", None)
    calls, skipped = r.stop()
    assert calls == [("open_app", {"package": "x"})] and skipped == 0 and not r.active


def test_coordinates_are_counted_not_stored_and_tap_element_becomes_text() -> None:
    r = Recorder()
    r.start()
    r.capture("tap", {"x": 1, "y": 2}, "tapped", None)
    r.capture("swipe", {"x1": 1}, "swiped", None)
    r.capture("tap_element", {"index": 4}, "tapped", ("Add to cart", 0))
    r.capture("tap_element", {"index": 5}, "tapped", ("Add", 1))
    r.capture("tap_text", {"text": "Next", "nth": 0}, "tapped", None)
    r.capture("observe", {}, "snapshot=1", None)  # read-only tools are not steps
    calls, skipped = r.stop()
    assert skipped == 2
    assert calls == [
        ("tap_text", {"text": "Add to cart"}),
        ("tap_text", {"text": "Add", "nth": 1}),
        ("tap_text", {"text": "Next"}),
    ]

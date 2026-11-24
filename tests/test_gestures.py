"""Pure touch geometry."""

from __future__ import annotations

import pytest

from droidpilot import gestures as GE


def test_point_at_interpolates_and_clamps() -> None:
    path = [(0, 0), (100, 0), (100, 100)]
    assert GE.point_at(path, 0) == (0, 0)
    assert GE.point_at(path, 0.25) == (50, 0)
    assert GE.point_at(path, 0.75) == (100, 50)
    assert GE.point_at(path, 1) == (100, 100)
    assert GE.point_at(path, 7) == (100, 100)  # clamped
    assert GE.point_at([(5, 5)], 0.5) == (5, 5)


def test_scroll_down_moves_finger_up_and_stays_centred() -> None:
    (x1, y1), (x2, y2) = GE.scroll_path("down", 0.5, 720, 1600)
    assert x1 == x2 == 360 and y1 > y2 and y1 - y2 == 800
    (x1, _), (x2, _) = GE.scroll_path("right", 0.5, 720, 1600)
    assert x1 > x2  # finger moves left to reveal content on the right
    with pytest.raises(ValueError):
        GE.scroll_path("sideways", 0.5, 720, 1600)


def test_pinch_spreads_for_zoom_in_and_closes_for_zoom_out() -> None:
    (l0, l1), (r0, r1) = (p for p in GE.pinch_paths(360, 800, 2.0, 720, 1600))
    assert l1[0] < l0[0] and r1[0] > r0[0]
    (l0, l1), (r0, r1) = (p for p in GE.pinch_paths(360, 800, 0.5, 720, 1600))
    assert l1[0] > l0[0] and r1[0] < r0[0]
    wide = GE.pinch_paths(360, 800, 50.0, 720, 1600)
    assert wide[1][1][0] - 360 <= 0.45 * 720  # capped to stay on screen


def test_fallback_command_for_tap_hold_and_swipe() -> None:
    assert GE.fallback_command([(10, 20)], 60) == "input tap 10 20"
    assert GE.fallback_command([(10, 20), (10, 20)], 900) == "input swipe 10 20 10 20 900"
    assert GE.fallback_command([(10, 20), (30, 40)], 300) == "input swipe 10 20 30 40 300"


def test_steps_and_keycodes() -> None:
    assert GE.steps_for(300, 16) == 18 and GE.steps_for(5, 16) == 1
    assert GE.KEYCODES["home"] == 3 and GE.KEYCODES["back"] == 4 and GE.KEYCODES["enter"] == 66

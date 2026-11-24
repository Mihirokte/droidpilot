"""Snapshots: change detection, text lookup, the element under a finger."""

from __future__ import annotations

from droidpilot import snapshot as SN
from tests.conftest import el, snap

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



def test_find_matches_hyphenated_labels_and_compacted_segments() -> None:
    wifi = el(0, "View", "Wi-Fi | A005_5G", ["click"], (0, 0, 500, 100))
    s = snap(1, [wifi])
    for q in ("Wi-Fi", "wi fi", "Wi-Fi | A005_5G", "a005 5g"):
        assert SN.find(s, q) and SN.find(s, q)[0].index == 0, q



def test_element_at_picks_smallest_interactive() -> None:
    s = snap(1, [CARD, BUY])
    assert SN.element_at(s, 100, 850).index == 1  # the button inside the card
    assert SN.element_at(s, 100, 420).index == 0
    assert SN.element_at(s, 900, 2000) is None


def test_header_reports_change_state_notes_and_chrome_hint() -> None:
    a = snap(1, [CARD])
    first = SN.header(a, None, (720, 1600), "app=a/b", has_notes=False)
    assert first.splitlines() == ["snapshot=1 screen=720x1600 app=a/b", "changed=first observe"]
    same = SN.header(snap(2, [CARD]), SN.diff(a, snap(2, [CARD])), (720, 1600), "b", has_notes=True)
    assert "notes: saved" in same and same.endswith("changed=NO (same screen as the previous snapshot)")
    chrome = snap(3, [BUY], app="com.android.chrome/org.chromium.Main")
    assert "web_read" in SN.header(chrome, SN.diff(a, chrome), (720, 1600), "b", has_notes=False)
    assert "changed=yes (+1 new labels, -1 gone)" in SN.header(chrome, SN.diff(a, chrome), (720, 1600), "b", False)

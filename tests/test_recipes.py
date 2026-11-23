"""Recipes, selectors, notes and the knowledge store."""

from __future__ import annotations

import json

import pytest

from droidpilot import knowledge as K
from droidpilot import recipes as R
from droidpilot import snapshot as SN
from droidpilot import store
from droidpilot.adb import Blocked, DeviceError
from droidpilot.perception import UiElement


def el(i, cls, text, flags, bounds, desc="", rid=""):
    return UiElement(i, cls, text, desc, rid, tuple(flags), bounds)


def snap(elements):
    els = tuple(elements)
    return SN.Snapshot(1, "a/b", els, SN.digest(els))


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path)


# ---- selectors -------------------------------------------------------------
def test_selector_picks_short_unique_text_not_the_price() -> None:
    a = el(0, "View", "Levi's | 511 Slim | ₹1,704", ["click"], (0, 0, 300, 300))
    b = el(1, "View", "Levi's | 512 Tapered | ₹1,120", ["click"], (300, 0, 600, 300))
    s = snap([a, b])
    assert R.selector_for(s, a) == ("511 Slim", 0)  # unique segment, shorter than the full label
    assert R.selector_for(s, b) == ("512 Tapered", 0)


def test_selector_uses_id_when_text_is_generic_and_nth_when_repeated() -> None:
    add = el(0, "Button", "Submit", ["click"], (0, 0, 100, 50), rid="add-to-cart-button")
    buy = el(1, "Button", "Submit", ["click"], (0, 60, 100, 110), rid="buy-now-button")
    s = snap([add, buy])
    assert R.selector_for(s, add) == ("add to cart button", 0)
    one = el(0, "Button", "Add", ["click"], (0, 0, 100, 50))
    two = el(1, "Button", "Add", ["click"], (0, 60, 100, 110))
    assert R.selector_for(snap([one, two]), two) == ("Add", 1)


# ---- compile and params ----------------------------------------------------
def test_compile_replaces_param_values_and_never_stores_typed_literals() -> None:
    calls = [
        ("open_url", {"url": "https://x.in/s?k=black+jeans&rh=p_123%3A339433"}),
        ("type_text", {"text": "hunter2"}),  # not covered by any param
        ("type_text", {"text": "black jeans", "submit": True}),
        ("tap_text", {"text": "Add to cart"}),
        ("tap", {"x": 1, "y": 2}),  # coordinates are not recordable
    ]
    steps = R.compile_steps(calls, {"query": "black jeans", "brand": "339433"})
    blob = json.dumps(steps)
    assert "hunter2" not in blob and "black jeans" not in blob and "339433" not in blob
    assert steps[0]["url"] == "https://x.in/s?k=black+jeans&rh=p_123%3A{brand}"  # "black+jeans" is not the param value "black jeans"
    assert steps[1]["text"] == "{text_1}" and steps[2]["text"] == "{query}"
    assert R.required_params(steps) == ["brand", "text_1", "query"]
    assert all(s["do"] != "tap" for s in steps)


def test_substitute_requires_every_param() -> None:
    assert R.substitute("k={q}&b={b}", {"q": "a", "b": "c"}) == "k=a&b=c"
    with pytest.raises(R.MissingParam):
        R.substitute("{q}", {})


# ---- replay ----------------------------------------------------------------
class FakePhone:
    def __init__(self, fail_at=None, blocked_at=None):
        self.calls, self.fail_at, self.blocked_at = [], fail_at, blocked_at

    def _do(self, name, *a):
        if self.fail_at == name:
            raise DeviceError(f"{name} failed")
        if self.blocked_at == name:
            raise Blocked("looks like a purchase")
        self.calls.append((name, *a))

    def open_url(self, url, package=None): self._do("open_url", url)
    def open_app(self, package): self._do("open_app", package)
    def tap_text(self, text, nth=0, confirm=False):
        assert confirm is False, "a recipe must never confirm"
        self._do("tap_text", text)
    def type_text(self, text, submit=False): self._do("type_text", text)
    def press_key(self, name): self._do("press_key", name)
    def scroll(self, direction, amount=0.5): self._do("scroll", direction)
    def wait_for(self, text, timeout_ms=5000): return "found" if self.fail_at != "wait_for" else "NOT FOUND after 1ms"


STEPS = [
    {"do": "open_url", "url": "https://x.in/s?k={query}"},
    {"do": "tap_text", "text": "511 Slim"},
    {"do": "tap_text", "text": "add to cart button"},
]


def test_run_success_fills_params() -> None:
    p = FakePhone()
    out = R.run(p, STEPS, {"query": "jeans"})
    assert out.ok and out.done == 3 and p.calls[0] == ("open_url", "https://x.in/s?k=jeans")


def test_run_missing_param_does_nothing() -> None:
    p = FakePhone()
    out = R.run(p, STEPS, {})
    assert not out.ok and p.calls == [] and "query" in out.message


def test_run_stops_at_first_failure_and_names_the_step() -> None:
    out = R.run(FakePhone(fail_at="tap_text"), STEPS, {"query": "q"})
    assert not out.ok and out.done == 1 and "step 2/3" in out.message and "observe" in out.message


def test_run_surfaces_guard_block_and_does_not_continue() -> None:
    p = FakePhone(blocked_at="tap_text")
    out = R.run(p, STEPS, {"query": "q"})
    assert not out.ok and "BLOCKED" in out.message and len(p.calls) == 1


def test_wait_for_not_found_fails_the_run() -> None:
    out = R.run(FakePhone(fail_at="wait_for"), [{"do": "wait_for", "text": "x"}], {})
    assert not out.ok and "NOT FOUND" in out.message


# ---- knowledge store -------------------------------------------------------
def test_notes_roundtrip_and_cap() -> None:
    assert K.get_notes("in.amazon") == "" and not K.has_notes("in.amazon")
    K.add_note("in.amazon", "Back does   not close\nthe filter panel")
    assert K.get_notes("in.amazon") == "- Back does not close the filter panel\n" and K.has_notes("in.amazon")
    with pytest.raises(DeviceError, match="full"):
        for _ in range(100):
            K.add_note("in.amazon", "x" * 250)


def test_bad_names_are_rejected_before_touching_disk() -> None:
    for bad in ("../evil", "A B", "", "x" * 41):
        with pytest.raises(DeviceError):
            K.save_recipe(bad, "app", "", [{"do": "press_key", "key": "home"}])
    with pytest.raises(DeviceError):
        K.get_notes("../../etc/passwd")


def test_recipe_save_load_list_and_empty_rejected() -> None:
    K.save_recipe("amazon-search", "in.amazon", "search with filters", STEPS)
    assert K.load_recipe("amazon-search")["steps"] == STEPS
    assert [r["name"] for r in K.list_recipes()] == ["amazon-search"]
    with pytest.raises(DeviceError, match="Nothing was recorded"):
        K.save_recipe("empty", "app", "", [])
    with pytest.raises(DeviceError, match="No recipe"):
        K.load_recipe("nope")


def test_clean_keeps_knowledge() -> None:
    K.add_note("a.b", "keep me")
    (store.subdir("traces") / "t.jsonl").write_text("x")
    assert store.clear("traces") == 1
    assert K.get_notes("a.b")


def test_open_url_rejects_unsafe_schemes() -> None:
    from droidpilot.phone import Phone

    for bad in ("file:///etc/passwd", "javascript:alert(1)", "intent://x#Intent;end", "content://x"):
        with pytest.raises(DeviceError, match="allows"):
            Phone().open_url(bad)

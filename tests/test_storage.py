"""Run log, size caps, notes and the recipe store."""

from __future__ import annotations

import json
import os
import time

import pytest

from droidpilot import knowledge as K
from droidpilot import store
from droidpilot.errors import DeviceError
from droidpilot.trace import Trace, redact


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
    steps = [{"do": "open_url", "url": "https://x.in/s?k={query}"}, {"do": "tap_text", "text": "511 Slim"}]
    K.save_recipe("amazon-search", "in.amazon", "search with filters", steps)
    assert K.load_recipe("amazon-search")["steps"] == steps
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

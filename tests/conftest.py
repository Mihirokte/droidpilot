"""Shared helpers and fixtures. Every test runs with its own droidpilot home directory."""

from __future__ import annotations

import pytest

from droidpilot import snapshot as SN
from droidpilot import store
from droidpilot.perception import UiElement


def el(i: int, cls: str, text: str, flags, bounds, desc: str = "", rid: str = "") -> UiElement:
    return UiElement(i, cls, text, desc, rid, tuple(flags), bounds)


def snap(id_or_elements, elements=None, app: str = "a/b") -> SN.Snapshot:
    """snap(1, [els]) or snap([els]) (id 1)."""
    if elements is None:
        id_, elements = 1, id_or_elements
    else:
        id_ = id_or_elements
    els = tuple(elements)
    return SN.Snapshot(id_, app, els, SN.digest(els))


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "ROOT", tmp_path / "home")

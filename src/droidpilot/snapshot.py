"""Immutable screen snapshots: stale-index protection, change detection, text lookup.

All functions are pure. They take UiElement tuples and return plain values.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from .perception import UiElement


def label(e: UiElement) -> str:
    return e.text or e.desc or e.resource_id


def words(e: UiElement) -> str:
    """Everything that names the element: text, description and id (ids use - or _ as separators).

    Some apps give every button the text "Submit" and put the meaning only in the id
    (Amazon: add-to-cart-button, buy-now-button).
    """
    ident = e.resource_id.replace("-", " ").replace("_", " ")
    return " | ".join(part for part in (e.text, e.desc, ident) if part)


@dataclass(frozen=True)
class Snapshot:
    id: int
    app: str  # "package/activity" at capture time
    elements: tuple[UiElement, ...]
    digest: str


@dataclass(frozen=True)
class Diff:
    changed: bool
    added: tuple[UiElement, ...]
    removed: tuple[str, ...]


def digest(elements: tuple[UiElement, ...] | list[UiElement]) -> str:
    h = hashlib.sha1()
    for e in elements:
        h.update(f"{e.cls}|{label(e)}|{e.flags}|{e.bounds}\n".encode())
    return h.hexdigest()[:12]


def diff(old: Snapshot, new: Snapshot) -> Diff:
    if old.digest == new.digest:
        return Diff(False, (), ())
    old_labels = Counter(label(e) for e in old.elements if label(e))
    new_labels = Counter(label(e) for e in new.elements if label(e))
    added = tuple(e for e in new.elements if label(e) and old_labels[label(e)] == 0)
    removed = tuple(lab for lab in old_labels if new_labels[lab] == 0)
    return Diff(True, added, removed)


def _area(e: UiElement) -> int:
    l, t, r, b = e.bounds
    return (r - l) * (b - t)


def find(snap: Snapshot, text: str) -> list[UiElement]:
    """Elements whose label contains `text` (case-insensitive). Best matches first:
    exact label, then interactive, then smaller area."""
    def norm(t: str) -> str:  # same rule on both sides: "Wi-Fi" matches "wi-fi", "wi fi" and an id "wi_fi"
        return " ".join(t.casefold().replace("-", " ").replace("_", " ").split())

    needle = norm(text)
    hits = [e for e in snap.elements if needle in norm(words(e))]
    return sorted(
        hits,
        key=lambda e: (label(e).casefold() != needle, not ({"click", "long-click", "edit"} & set(e.flags)), _area(e)),
    )


def element_at(snap: Snapshot, x: int, y: int) -> UiElement | None:
    """The element a finger would hit at device pixel (x, y): smallest interactive one, else smallest any."""
    inside = [e for e in snap.elements if e.bounds[0] <= x < e.bounds[2] and e.bounds[1] <= y < e.bounds[3]]
    interactive = [e for e in inside if {"click", "long-click", "edit"} & set(e.flags)]
    pool = interactive or inside
    return min(pool, key=_area) if pool else None

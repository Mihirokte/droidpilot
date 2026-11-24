"""Screen perception: screenshots, UI hierarchy, change/settle detection.

Coordinate spaces
-----------------
Device space: real pixels (e.g. 1080x2400).
View space:   what the agent sees. The screenshot is scaled so its long side is
              `view_long_side` pixels. All tool coordinates are in view space.
"""

from __future__ import annotations

import io
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace

import numpy as np
from PIL import Image

from .adb import Adb
from .errors import DeviceError

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass(frozen=True)
class Geometry:
    """Device pixel size plus the scale to the agent's view space."""

    width: int
    height: int
    view_long_side: int

    @property
    def scale(self) -> float:
        """Device pixels per view pixel (>= 1 means the view is smaller)."""
        return max(self.width, self.height) / self.view_long_side

    @property
    def view_size(self) -> tuple[int, int]:
        return round(self.width / self.scale), round(self.height / self.scale)

    def to_device(self, x: float, y: float) -> tuple[int, int]:
        dx = min(max(round(x * self.scale), 0), self.width - 1)
        dy = min(max(round(y * self.scale), 0), self.height - 1)
        return dx, dy

    def to_view(self, x: float, y: float) -> tuple[int, int]:
        return round(x / self.scale), round(y / self.scale)


@dataclass(frozen=True)
class UiElement:
    index: int
    cls: str
    text: str
    desc: str
    resource_id: str
    flags: tuple[str, ...]
    bounds: tuple[int, int, int, int]  # device px: left, top, right, bottom

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


def capture(adb: Adb) -> Image.Image:
    data = adb.exec_out("screencap -p", timeout=20)
    if not data.startswith(b"\x89PNG"):
        raise DeviceError("screencap returned no PNG (screen off, or app blocks capture with FLAG_SECURE?)")
    return Image.open(io.BytesIO(data)).convert("RGB")


def to_view_jpeg(img: Image.Image, geo: Geometry, quality: int = 80) -> bytes:
    resized = img.resize(geo.view_size, Image.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def signature(img: Image.Image) -> np.ndarray:
    """Small grayscale thumbnail, status bar cropped, for cheap change detection."""
    w, h = img.size
    cropped = img.crop((0, int(h * 0.04), w, h)).convert("L")
    return np.asarray(cropped.resize((48, 96)), dtype=np.int16)


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)))


def fetch_xml_shell(adb: Adb) -> str:
    """UI hierarchy through `uiautomator dump`. Reliable everywhere. About 2.7 s on a realme 9."""
    for _ in range(4):  # first dump after boot or a window change can return a null root
        raw = adb.exec_out("uiautomator dump /dev/tty", timeout=30).decode("utf-8", errors="replace")
        start, end = raw.find("<?xml"), raw.rfind("</hierarchy>")
        if start >= 0 and end >= 0:
            return raw[start : end + len("</hierarchy>")]
        time.sleep(0.8)
    raise DeviceError(f"uiautomator dump failed: {raw.strip()[:200]}")


STATUS_BAR = (
    "com.android.systemui:id/status_bar", "com.android.systemui:id/notification_icon_area",
    "com.android.systemui:id/system_icons", "com.android.systemui:id/clock",
)


def _status_bar_nodes(root: ET.Element) -> set[int]:
    """ids() of nodes inside the status bar. The clock and icons change every minute,
    so they would make every observe look changed. The notification shade stays (it is useful)."""
    skip: set[int] = set()
    for node in root.iter("node"):
        rid = node.get("resource-id") or ""
        if rid.startswith(STATUS_BAR) or rid.endswith(":id/status_bar_container"):
            skip.update(id(n) for n in node.iter("node"))
    return skip


def parse_ui(xml: str) -> list[UiElement]:
    """Parse a uiautomator XML hierarchy. Keep nodes that are interactive or carry text."""
    root = ET.fromstring(xml)
    skip = _status_bar_nodes(root)
    elements: list[UiElement] = []
    for node in root.iter("node"):
        if id(node) in skip:
            continue
        flags = tuple(
            name
            for name, attr in (
                ("click", "clickable"),
                ("long-click", "long-clickable"),
                ("scroll", "scrollable"),
                ("check", "checkable"),
                ("edit", None),
                ("focused", "focused"),
            )
            if (attr and node.get(attr) == "true") or (name == "edit" and "EditText" in (node.get("class") or ""))
        )
        text = (node.get("text") or "").strip()
        desc = (node.get("content-desc") or "").strip()
        if not (flags or text or desc):
            continue
        m = _BOUNDS.match(node.get("bounds") or "")
        if not m:
            continue
        left, top, right, bottom = map(int, m.groups())
        if right <= left or bottom <= top:
            continue
        elements.append(
            UiElement(
                index=len(elements),
                cls=(node.get("class") or "").rsplit(".", 1)[-1],
                text=text,
                desc=desc,
                resource_id=(node.get("resource-id") or "").rsplit("/", 1)[-1],
                flags=flags,
                bounds=(left, top, right, bottom),
            )
        )
    return elements


def dump_ui(adb: Adb) -> list[UiElement]:
    return parse_ui(fetch_xml_shell(adb))


def compact(elements: list[UiElement], screen_w: int, screen_h: int) -> list[UiElement]:
    """Merge label-only children into their small clickable parent and re-number.

    A product card is a clickable View holding several TextViews and an Image. Listing each
    child costs tokens and repeats the same words. One merged line per card is enough, and the
    index still points at a tappable element. Containers larger than 60% of the screen and
    scrollable containers are never merge targets (WebView, lists, full-screen overlays).
    """
    limit = 0.6 * screen_w * screen_h

    def area(b: tuple[int, int, int, int]) -> int:
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

    def inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
        return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]

    def is_target(e: UiElement) -> bool:
        return bool({"click", "long-click"} & set(e.flags)) and "scroll" not in e.flags and area(e.bounds) <= limit

    targets = [e for e in elements if is_target(e)]
    merged: dict[int, list[str]] = {}
    dropped: set[int] = set()
    for e in elements:
        if e.flags or not (e.text or e.desc):
            continue  # keep anything interactive
        parents = [t for t in targets if t.index != e.index and inside(e.bounds, t.bounds) and area(t.bounds) > area(e.bounds)]
        if not parents:
            continue
        parent = min(parents, key=lambda t: area(t.bounds))  # innermost clickable parent
        dropped.add(e.index)
        label = e.text or e.desc
        if label not in (parent.text or "") and label not in (parent.desc or ""):
            merged.setdefault(parent.index, []).append(label)

    result: list[UiElement] = []
    for e in elements:
        if e.index in dropped:
            continue
        extra = merged.get(e.index, [])
        if extra:
            joined = " | ".join(dict.fromkeys(([e.text or e.desc] if (e.text or e.desc) else []) + extra))
            e = replace(e, text=joined[:160])
        result.append(e)
    return [replace(e, index=i) for i, e in enumerate(result)]


def format_ui(elements: list[UiElement], geo: Geometry, limit: int = 120) -> str:
    if not elements:
        return "(no UI elements found: the app may draw its own UI (game/Flutter/WebView) or block the dump; use screenshot coordinates)"
    lines = []
    for e in elements[:limit]:
        left, top, right, bottom = (round(v / geo.scale) for v in e.bounds)
        cx, cy = geo.to_view(*e.center)
        label = e.text or e.desc or e.resource_id
        extras = []
        if e.desc and e.text and e.desc != e.text:
            extras.append(f"desc={e.desc!r}")
        if e.resource_id and e.resource_id != label:
            extras.append(f"id={e.resource_id}")
        lines.append(
            f"[{e.index}] {e.cls} {label[:80]!r} {','.join(e.flags)} center=({cx},{cy}) box=({left},{top},{right},{bottom})"
            + (" " + " ".join(extras) if extras else "")
        )
    if len(elements) > limit:
        lines.append(f"... {len(elements) - limit} more elements not shown")
    return "\n".join(lines)

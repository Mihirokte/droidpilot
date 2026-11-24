"""UI tree parsing, compaction, geometry and change signatures."""

from __future__ import annotations

import numpy as np

from droidpilot import perception as P
from tests.conftest import el

HIERARCHY = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
 <node class="android.widget.FrameLayout" text="" content-desc="" bounds="[0,0][1080,2400]" clickable="false">
  <node class="android.widget.Button" text="Send" resource-id="com.x:id/send" clickable="true" bounds="[100,200][300,300]"/>
  <node class="android.widget.EditText" text="" content-desc="Message" bounds="[0,400][1080,500]"/>
  <node class="android.view.View" text="" content-desc="" bounds="[0,0][10,10]"/>
 </node>
</hierarchy>
UI hierchary dumped to: /dev/tty"""


class FakeAdb:
    def exec_out(self, command: str, timeout: float = 30) -> bytes:
        return HIERARCHY.encode()



def test_ui_parse_filters_noise_and_flags() -> None:
    els = P.dump_ui(FakeAdb())  # type: ignore[arg-type]
    assert [e.cls for e in els] == ["Button", "EditText"]
    assert els[0].flags == ("click",) and els[0].center == (200, 250)
    assert "edit" in els[1].flags



def test_parse_ui_matches_dump_ui_on_same_xml() -> None:
    xml = HIERARCHY[HIERARCHY.index("<?xml") : HIERARCHY.rindex("</hierarchy>") + len("</hierarchy>")]
    assert P.parse_ui(xml) == P.dump_ui(FakeAdb())  # type: ignore[arg-type]



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



def test_compact_merges_card_children_and_keeps_nested_buttons() -> None:
    els = [
        el(0, "WebView", "", ["click", "scroll"], (0, 0, 1080, 2300)),  # too big: never a merge target
        el(1, "View", "", ["click"], (0, 400, 500, 900)),  # card
        el(2, "TextView", "Levi's", [], (10, 410, 400, 450)),
        el(3, "TextView", "512 Slim Jeans", [], (10, 460, 400, 500)),
        el(4, "TextView", "512 Slim Jeans", [], (10, 505, 400, 540)),  # duplicate label
        el(5, "Button", "Add to cart", ["click"], (10, 800, 490, 880)),  # nested button stays
        el(6, "TextView", "Loose text", [], (600, 1000, 900, 1040)),  # no clickable parent, stays
    ]
    out = P.compact(els, 1080, 2400)
    assert [e.index for e in out] == list(range(len(out)))
    labels = [e.text for e in out]
    assert "Levi's | 512 Slim Jeans" in labels
    assert "Add to cart" in labels and "Loose text" in labels
    assert len(out) == 4  # webview, card, button, loose text



def test_geometry_roundtrip_and_clamp() -> None:
    geo = P.Geometry(1080, 2400, 1600)
    assert geo.view_size == (720, 1600)
    assert geo.to_device(360, 800) == (540, 1200)
    assert geo.to_device(99999, -5) == (1079, 0)
    assert geo.to_view(540, 1200) == (360, 800)



def test_signature_diff_detects_change_ignores_status_bar() -> None:
    from PIL import Image

    a = Image.new("RGB", (100, 200), (0, 0, 0))
    b = a.copy()
    b.paste((255, 255, 255), (0, 0, 100, 5))  # status bar only
    c = a.copy()
    c.paste((255, 255, 255), (0, 100, 100, 160))
    assert P.diff(P.signature(a), P.signature(b)) < 0.5
    assert P.diff(P.signature(a), P.signature(c)) > 5
    assert isinstance(P.signature(a), np.ndarray)


def test_format_ui_prints_view_space_centre_box_flags_and_id() -> None:
    geo = P.Geometry(1080, 2400, 1600)  # view is 720x1600, scale 1.5
    e = P.UiElement(0, "Button", "Add to cart", "", "add-to-cart-button", ("click",), (30, 849, 690, 935))
    line = P.format_ui([e], geo)
    assert line == "[0] Button 'Add to cart' click center=(240,595) box=(20,566,460,623) id=add-to-cart-button"
    assert "no UI elements" in P.format_ui([], geo)

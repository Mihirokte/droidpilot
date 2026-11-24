"""Records successful tool calls between record(start) and record(stop), for recipes."""

from __future__ import annotations

from . import recipes as R

COORDINATE_TOOLS = frozenset({"tap", "double_tap", "long_press", "swipe", "pinch", "gesture"})
FAILED_PREFIXES = ("ERROR", "BLOCKED", "NEEDS_HUMAN", "NOT FOUND")


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] | None = None  # None: not recording
        self.skipped = 0  # coordinate gestures seen but not stored

    @property
    def active(self) -> bool:
        return self.calls is not None

    def start(self) -> None:
        self.calls, self.skipped = [], 0

    def stop(self) -> tuple[list[tuple[str, dict]], int]:
        """Return (calls, skipped) and stop recording."""
        calls, skipped = self.calls or [], self.skipped
        self.calls, self.skipped = None, 0
        return calls, skipped

    def capture(self, tool: str, args: dict, result: object, last_tap: tuple[str, int] | None) -> None:
        """Store one call. Coordinate gestures are counted, not stored: they break when the layout moves.
        A tap_element is stored as tap_text, using the text that names the tapped element."""
        if self.calls is None or not isinstance(result, str) or result.startswith(FAILED_PREFIXES):
            return
        if tool in COORDINATE_TOOLS:
            self.skipped += 1
        elif tool == "tap_element" and last_tap:
            text, nth = last_tap
            self.calls.append(("tap_text", {"text": text, **({"nth": nth} if nth else {})}))
        elif tool == "tap_text":
            self.calls.append(("tap_text", {"text": args["text"], **({"nth": args["nth"]} if args.get("nth") else {})}))
        elif tool in R.RECORDABLE:
            self.calls.append((tool, {k: v for k, v in args.items() if v is not None}))

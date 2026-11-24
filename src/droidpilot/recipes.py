"""Recipes: recorded action sequences that replay without the model.

Pure logic: selectors, parameters, compile, replay. Storage is in knowledge.py.

Rules:
- Steps name elements by text, never by coordinates.
- Typed text is never stored. It becomes a parameter, filled in at replay.
- Replay uses the normal tools, so the safety guard still applies. A recipe cannot confirm.
- Replay stops at the first failure and returns control to the agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from . import snapshot as SN
from .errors import DeviceError
from .perception import UiElement

RECORDABLE = {"open_url", "open_app", "tap_text", "type_text", "press_key", "scroll", "wait_for"}
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
GENERIC = {"submit", "ok", "button", "image", ""}  # labels that do not identify an element


class MissingParam(DeviceError):
    pass


_UNSTABLE = re.compile(r"₹|\$|€|%|\bbought\b|\bratings?\b|\bstars?\b|^\d[\d.,]*$", re.IGNORECASE)  # prices, counts, scores change between runs


def selector_for(snap: SN.Snapshot, el: UiElement) -> tuple[str, int]:
    """Text that finds `el` again. Prefer text that matches only this element, then the shortest.
    Skip prices and counts: they change between runs."""
    segments = [
        s.strip()
        for s in SN.words(el).split(" | ")
        if s.strip() and s.strip().lower() not in GENERIC and not _UNSTABLE.search(s)
    ]
    ranked = sorted(dict.fromkeys(segments), key=len)
    for text in ranked:  # 1. matches only this element
        hits = SN.find(snap, text)
        if len(hits) == 1 and hits[0].index == el.index:
            return text, 0
    for text in ranked:  # 2. this element is the first match
        hits = SN.find(snap, text)
        if hits and hits[0].index == el.index:
            return text, 0
    for text in ranked:  # 3. a later match: say which one
        hits = [h.index for h in SN.find(snap, text)]
        if el.index in hits:
            return text, hits.index(el.index)
    return SN.label(el), 0


def substitute(value: Any, params: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value

    def fill(m: re.Match) -> str:
        if m.group(1) not in params:
            raise MissingParam(f"Missing recipe parameter {m.group(1)!r}")
        return str(params[m.group(1)])

    return _PLACEHOLDER.sub(fill, value)


def required_params(steps: list[dict]) -> list[str]:
    names: list[str] = []
    for step in steps:
        for v in step.values():
            if isinstance(v, str):
                names += [n for n in _PLACEHOLDER.findall(v) if n not in names]
    return names


def compile_steps(calls: list[tuple[str, dict]], params: dict[str, str]) -> list[dict]:
    """Turn recorded calls into steps. Replace each literal param value by {name}.
    Typed text that no param covers becomes {text_1}, {text_2}... so no literal is ever stored."""
    ordered = sorted(params.items(), key=lambda kv: -len(kv[1]))  # longest value first
    steps: list[dict] = []
    typed = 0
    for tool, args in calls:
        if tool not in RECORDABLE:
            continue
        step: dict[str, Any] = {"do": tool}
        for key, val in args.items():
            if isinstance(val, str):
                for name, literal in ordered:
                    if literal:
                        val = val.replace(literal, "{" + name + "}")
            step[key] = val
        if tool == "type_text" and not _PLACEHOLDER.search(step.get("text", "")):
            typed += 1
            step["text"] = f"{{text_{typed}}}"
        steps.append(step)
    return steps


class PhoneLike(Protocol):
    def open_url(self, url: str, package: str | None = None) -> Any: ...
    def open_app(self, package: str) -> Any: ...
    def tap_text(self, text: str, nth: int = 0, confirm: bool = False) -> Any: ...
    def type_text(self, text: str, submit: bool = False) -> Any: ...
    def press_key(self, name: str) -> Any: ...
    def scroll(self, direction: str, amount: float = 0.5) -> Any: ...
    def wait_for(self, text: str, timeout_ms: int = 5000) -> str: ...


@dataclass(frozen=True)
class RunResult:
    ok: bool
    done: int
    total: int
    message: str

    def __str__(self) -> str:
        return self.message


def run(phone: PhoneLike, steps: list[dict], params: dict[str, str]) -> RunResult:
    missing = [n for n in required_params(steps) if n not in params]
    if missing:
        return RunResult(False, 0, len(steps), f"Missing parameters: {missing}. Nothing was done.")
    for i, step in enumerate(steps):
        a = {k: substitute(v, params) for k, v in step.items() if k != "do"}
        try:
            do = step["do"]
            if do == "open_url":
                phone.open_url(a["url"], a.get("package"))
            elif do == "open_app":
                phone.open_app(a["package"])
            elif do == "tap_text":
                phone.tap_text(a["text"], int(a.get("nth", 0)))  # never confirm=True from a recipe
            elif do == "type_text":
                phone.type_text(a["text"], bool(a.get("submit", False)))
            elif do == "press_key":
                phone.press_key(a["key"] if "key" in a else a["name"])
            elif do == "scroll":
                phone.scroll(a.get("direction", "down"), float(a.get("amount", 0.5)))
            elif do == "wait_for":
                out = phone.wait_for(a["text"], int(a.get("timeout_ms", 5000)))
                if out.startswith("NOT FOUND"):
                    raise DeviceError(out)
            else:
                raise DeviceError(f"unknown step type {do!r}")
        except DeviceError as exc:
            kind = type(exc).__name__.upper()
            return RunResult(False, i, len(steps), f"STOPPED at step {i + 1}/{len(steps)} ({step['do']}): {kind}: {exc}. {i} step(s) done. Call observe and continue by hand.")
    return RunResult(True, len(steps), len(steps), f"Recipe finished: {len(steps)} step(s) done. Call observe to check the result.")

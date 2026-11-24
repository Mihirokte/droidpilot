"""Disk storage for app notes and recipes, with size caps. `droidpilot clean` never deletes this."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import store
from .errors import DeviceError

MAX_NOTE_BYTES = 4_000  # per app. Notes are loaded into the agent context, so keep them short.
MAX_TOTAL_BYTES = 2_000_000
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_PACKAGE = re.compile(r"^[A-Za-z0-9._]{1,120}$")


def _dir(kind: str) -> Path:
    return store.subdir(f"knowledge/{kind}")


def _check_name(name: str) -> str:
    if not _NAME.match(name):
        raise DeviceError("Recipe name must be 1-40 characters: a-z, 0-9, - or _")
    return name


def get_notes(package: str) -> str:
    if not _PACKAGE.match(package):
        raise DeviceError("bad package name")
    f = _dir("notes") / f"{package}.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def has_notes(package: str) -> bool:
    return bool(_PACKAGE.match(package)) and (_dir("notes") / f"{package}.md").exists()


def add_note(package: str, text: str) -> int:
    """Append one line. Return the size of the note file in bytes."""
    if not _PACKAGE.match(package):
        raise DeviceError("bad package name")
    line = " ".join(text.split())[:300]
    f = _dir("notes") / f"{package}.md"
    body = (f.read_text(encoding="utf-8") if f.exists() else "") + f"- {line}\n"
    if len(body.encode()) > MAX_NOTE_BYTES:
        raise DeviceError(f"Notes for {package} are full ({MAX_NOTE_BYTES} bytes). Shorten them first.")
    f.write_text(body, encoding="utf-8")
    store.enforce_cap(store.ROOT / "knowledge", MAX_TOTAL_BYTES)
    return len(body.encode())


def save_recipe(name: str, app: str, description: str, steps: list[dict]) -> Path:
    _check_name(name)
    if not steps:
        raise DeviceError("Nothing was recorded. Do some actions between record start and stop.")
    path = _dir("recipes") / f"{name}.json"
    path.write_text(
        json.dumps({"name": name, "app": app, "description": description[:200], "created": int(time.time()), "steps": steps}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    store.enforce_cap(store.ROOT / "knowledge", MAX_TOTAL_BYTES)
    return path


def load_recipe(name: str) -> dict:
    path = _dir("recipes") / f"{_check_name(name)}.json"
    if not path.exists():
        raise DeviceError(f"No recipe named {name!r}. Call recipes() to list them.")
    return json.loads(path.read_text(encoding="utf-8"))


def list_recipes() -> list[dict]:
    out = []
    for f in sorted(_dir("recipes").glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out

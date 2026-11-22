"""Append-only JSONL run log. Records what was done and how long it took.

It never stores screen content or typed text. Only tool name, arguments, duration and status.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import store

MAX_FILE = 2_000_000  # rotate the active file at 2 MB
MAX_DIR = 10_000_000  # keep the whole directory under 10 MB
_REDACT = {"text"}  # argument names whose value is replaced by its length


def redact(args: dict) -> dict:
    return {k: (f"<{len(v)} chars>" if k in _REDACT and isinstance(v, str) else v) for k, v in args.items()}


class Trace:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or store.subdir("traces")
        self.path = self.directory / "trace.jsonl"

    def log(self, tool: str, args: dict, ms: float, status: str, result_chars: int = 0) -> None:
        if self.path.exists() and self.path.stat().st_size > MAX_FILE:
            self.path.replace(self.directory / f"trace-{int(time.time())}.jsonl")
            store.enforce_cap(self.directory, MAX_DIR)
        line = {"t": round(time.time(), 2), "tool": tool, "args": redact(args), "ms": round(ms), "status": status, "chars": result_chars}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

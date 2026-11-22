"""One place for everything droidpilot keeps on the Mac, with size caps.

Layout under ROOT:
  traces/     run logs. Safe to delete. `droidpilot clean` empties it.
  knowledge/  app notes and recipes (later). `droidpilot clean` never touches it.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("DROIDPILOT_HOME") or Path.home() / ".cache" / "droidpilot")


def subdir(name: str) -> Path:
    path = ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def dir_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def enforce_cap(path: Path, max_bytes: int) -> int:
    """Delete the oldest files until the directory fits. Return the number of files removed."""
    files = sorted((f for f in path.rglob("*") if f.is_file()), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    removed = 0
    for f in files:
        if total <= max_bytes:
            break
        total -= f.stat().st_size
        f.unlink()
        removed += 1
    return removed


def clear(name: str) -> int:
    path = ROOT / name
    count = 0
    if path.exists():
        for f in path.rglob("*"):
            if f.is_file():
                f.unlink()
                count += 1
    return count

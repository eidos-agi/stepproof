"""Atomic file writes.

Readers must never see a half-written JSON file, because a half-written
`runtime.url` or `active-run.json` causes enforcement to guess. Every write
goes to a temp file in the same directory, fsyncs, then renames over the
target. `os.replace` is atomic on POSIX and on Windows for same-volume
renames, which is what we require.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Serialize ``payload`` as JSON and atomically replace ``path``.

    Parent directory is created if missing. The temp file sits alongside the
    target so the rename stays on one filesystem.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def atomic_remove(path: Path) -> None:
    """Remove ``path`` if it exists. Never raises."""
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

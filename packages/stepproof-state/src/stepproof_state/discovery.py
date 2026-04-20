"""Runtime discovery via ``.stepproof/runtime.url``.

One runtime at a time. Its base URL, PID, and boot timestamp live in a
tiny JSON file. Any component that wants to talk to the runtime reads this
file; nobody hardcodes port 8787 anymore.

A stale ``runtime.url`` (PID dead, or URL not responding on ping) is worse
than none. Callers reading through :func:`resolve_runtime_url` that detect
staleness are expected to clear the file so the next reader gets a clean
slate.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .atomic import atomic_remove, atomic_write_json

RUNTIME_URL_FILE = "runtime.url"


def state_dir() -> Path:
    """Resolve the active StepProof state directory.

    Honors ``STEPPROOF_STATE_DIR`` for test isolation and for projects that
    deliberately relocate the directory. Otherwise ``$CWD/.stepproof``.
    """
    override = os.environ.get("STEPPROOF_STATE_DIR")
    if override:
        return Path(override)
    return Path.cwd() / ".stepproof"


@dataclass(frozen=True)
class RuntimeRecord:
    url: str
    pid: int
    started_at: str


def is_pid_alive(pid: int) -> bool:
    """Cheap PID liveness probe.

    Sending signal 0 on POSIX tests whether the process exists without
    actually delivering a signal. Returns ``False`` on any error, including
    permission-denied on foreign processes (we treat that as "don't know —
    assume not ours").
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return False
    except OSError:
        return False
    return True


def write_runtime_url(
    url: str,
    pid: int | None = None,
    started_at: str | None = None,
    base: Path | None = None,
) -> Path:
    """Atomically publish the runtime's URL.

    Callers should invoke this once the server has bound its port. The file
    survives only as long as the process that wrote it — ``clear_runtime_url``
    should be registered via ``atexit`` and the standard termination signals.
    """
    if pid is None:
        pid = os.getpid()
    if started_at is None:
        import time

        started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target = (base or state_dir()) / RUNTIME_URL_FILE
    atomic_write_json(
        target,
        {"url": url.rstrip("/"), "pid": int(pid), "started_at": started_at},
    )
    return target


def read_runtime_record(base: Path | None = None) -> RuntimeRecord | None:
    """Load ``runtime.url`` without liveness checks. Returns ``None`` if
    missing or malformed.
    """
    path = (base or state_dir()) / RUNTIME_URL_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return RuntimeRecord(
            url=str(data["url"]).rstrip("/"),
            pid=int(data.get("pid", 0)),
            started_at=str(data.get("started_at", "")),
        )
    except Exception:
        return None


def resolve_runtime_url(base: Path | None = None, clear_if_stale: bool = True) -> str | None:
    """Return the active runtime's URL, or ``None`` if no live runtime.

    Staleness is detected via PID liveness. The URL itself is not pinged
    here — callers that need a wire-level health check should do their own
    HTTP GET; this function's job is to answer "is there a process that
    claims to be serving the runtime right now?"
    """
    if os.environ.get("STEPPROOF_URL"):
        return os.environ["STEPPROOF_URL"].rstrip("/")

    record = read_runtime_record(base=base)
    if record is None:
        return None

    if record.pid and not is_pid_alive(record.pid):
        if clear_if_stale:
            clear_runtime_url(base=base)
        return None

    return record.url


def clear_runtime_url(base: Path | None = None) -> None:
    """Remove ``runtime.url``. Idempotent."""
    atomic_remove((base or state_dir()) / RUNTIME_URL_FILE)

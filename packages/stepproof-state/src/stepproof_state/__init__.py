"""StepProof state-directory primitives.

Thin, dependency-free layer over `.stepproof/`. Every StepProof component
reads and writes state through this module so there is one source of truth
for runtime discovery and active-run binding.
"""

from __future__ import annotations

from .atomic import atomic_write_json, atomic_remove
from .binding import (
    ActiveRun,
    clear_active_run,
    read_active_run,
    resolve_active_run,
    write_active_run,
)
from .discovery import (
    RuntimeRecord,
    clear_runtime_url,
    is_pid_alive,
    read_runtime_record,
    resolve_runtime_url,
    state_dir,
    write_runtime_url,
)

__all__ = [
    "ActiveRun",
    "RuntimeRecord",
    "atomic_remove",
    "atomic_write_json",
    "clear_active_run",
    "clear_runtime_url",
    "is_pid_alive",
    "read_active_run",
    "read_runtime_record",
    "resolve_active_run",
    "resolve_runtime_url",
    "state_dir",
    "write_active_run",
    "write_runtime_url",
]

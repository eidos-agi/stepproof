"""Active-run binding via ``.stepproof/active-run.json``.

When an agent has declared a plan or started a runbook, that choice is
persisted here so the PreToolUse hook can forward the correct ``run_id`` and
``current_step`` on every policy call without having to query the runtime
first. The MCP server is the writer; the hook is a reader.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .atomic import atomic_remove, atomic_write_json
from .discovery import state_dir

ACTIVE_RUN_FILE = "active-run.json"


@dataclass(frozen=True)
class ActiveRun:
    run_id: str
    current_step: str | None
    allowed_tools: list[str] = field(default_factory=list)
    template_id: str | None = None


def write_active_run(
    run_id: str,
    current_step: str | None,
    allowed_tools: list[str] | None = None,
    template_id: str | None = None,
    base: Path | None = None,
) -> Path:
    """Publish the currently bound run. Overwrites any prior binding."""
    target = (base or state_dir()) / ACTIVE_RUN_FILE
    payload = {
        "run_id": str(run_id),
        "current_step": current_step,
        "allowed_tools": list(allowed_tools or []),
        "template_id": template_id,
    }
    atomic_write_json(target, payload)
    return target


def read_active_run(base: Path | None = None) -> ActiveRun | None:
    path = (base or state_dir()) / ACTIVE_RUN_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ActiveRun(
            run_id=str(data["run_id"]),
            current_step=data.get("current_step"),
            allowed_tools=list(data.get("allowed_tools") or []),
            template_id=data.get("template_id"),
        )
    except Exception:
        return None


def resolve_active_run(base: Path | None = None) -> ActiveRun | None:
    """Return the bound run, or ``None`` if nothing is bound.

    Kept as a distinct name (vs. :func:`read_active_run`) so future versions
    can add liveness checks (e.g. cross-reference with the runtime) without
    churning call sites.
    """
    return read_active_run(base=base)


def clear_active_run(base: Path | None = None) -> None:
    """Remove ``active-run.json``. Idempotent."""
    atomic_remove((base or state_dir()) / ACTIVE_RUN_FILE)

"""Filesystem-backed persistence for StepProof runtime state.

Every run lives in its own directory on disk:

  .stepproof/runs/<run_id>/
    manifest.json      # WorkflowRun metadata (one file, rewritten on status change)
    step-<step_id>.json # Per-step state + evidence + verifier result
    events.jsonl       # Append-only audit stream for this run
    heartbeat.json     # Liveness tracker (rewritten on each heartbeat)

Every audit event also lands in ``.stepproof/events.jsonl`` at the root
for easy cross-run inspection. Per-run streams are authoritative; the
global stream is a convenience mirror.

Atomicity: every write goes through tmp-file + os.replace, so a reader
never sees a partial JSON document. Append-only streams use os.open
with O_APPEND plus fsync.

This replaces ``db.py`` which used aiosqlite. The runtime has a single
writer, the joins we once did in SQL are trivially expressed as reading
a run's directory, and the audit trail is now directly grep-able,
git-diffable, and mailable without tooling.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from .models import (
    AuditEvent,
    Heartbeat,
    LivenessStatus,
    RunStatus,
    StepRun,
    StepStatus,
    WorkflowRun,
)


# ---------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------


def state_dir() -> Path:
    """Resolve the .stepproof/ state directory.

    Matches the convention from ``stepproof-state``: honor
    ``STEPPROOF_STATE_DIR`` first, otherwise default to
    ``$CWD/.stepproof``.
    """
    override = os.environ.get("STEPPROOF_STATE_DIR")
    if override:
        return Path(override)
    return Path.cwd() / ".stepproof"


def runs_dir() -> Path:
    d = state_dir() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_dir(run_id: UUID | str) -> Path:
    d = runs_dir() / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def global_events_path() -> Path:
    return state_dir() / "events.jsonl"


# ---------------------------------------------------------------------
# Atomic write / append helpers
# ---------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Serialize to JSON atomically: tmp + fsync + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    data = json.dumps(payload, sort_keys=True, indent=2, default=_json_default).encode()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _append_jsonl(path: Path, record: Any) -> None:
    """Append one JSON record + newline. Creates parent + file if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, sort_keys=True, default=_json_default).encode() + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"{type(obj).__name__} not JSON serializable")


# ---------------------------------------------------------------------
# Run (manifest.json) operations
# ---------------------------------------------------------------------


def create_run(run: WorkflowRun, step_ids: list[str]) -> None:
    """Write the run manifest and initial per-step files."""
    d = run_dir(run.run_id)
    _atomic_write_json(d / "manifest.json", _run_to_manifest(run))
    for sid in step_ids:
        _atomic_write_json(d / f"step-{sid}.json", _empty_step(run.run_id, sid))


def _empty_step(run_id: UUID, step_id: str) -> dict:
    return {
        "run_id": str(run_id),
        "step_id": step_id,
        "status": StepStatus.PENDING.value,
        "evidence": {},
        "verification_result": None,
        "attempts": 0,
        "started_at": None,
        "ended_at": None,
    }


def _run_to_manifest(run: WorkflowRun) -> dict:
    return {
        "run_id": str(run.run_id),
        "template_id": run.template_id,
        "template_version": run.template_version,
        "owner_id": run.owner_id,
        "agent_id": run.agent_id,
        "environment": run.environment,
        "current_step": run.current_step,
        "status": run.status.value,
        "started_at": run.started_at.isoformat(),
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
    }


def _manifest_to_run(payload: dict) -> WorkflowRun:
    return WorkflowRun(
        run_id=UUID(payload["run_id"]),
        template_id=payload["template_id"],
        template_version=payload["template_version"],
        owner_id=payload["owner_id"],
        agent_id=payload["agent_id"],
        environment=payload["environment"],
        current_step=payload.get("current_step"),
        status=RunStatus(payload["status"]),
        started_at=datetime.fromisoformat(payload["started_at"]),
        ended_at=(
            datetime.fromisoformat(payload["ended_at"])
            if payload.get("ended_at")
            else None
        ),
    )


def get_run(run_id: UUID | str) -> WorkflowRun | None:
    p = runs_dir() / str(run_id) / "manifest.json"
    if not p.exists():
        return None
    try:
        return _manifest_to_run(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        return None


def update_run(run: WorkflowRun) -> None:
    _atomic_write_json(run_dir(run.run_id) / "manifest.json", _run_to_manifest(run))


def list_runs(limit: int = 50) -> list[WorkflowRun]:
    """Return runs sorted by started_at desc. Scans all run directories."""
    base = runs_dir()
    if not base.exists():
        return []
    runs: list[WorkflowRun] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        r = get_run(d.name)
        if r is not None:
            runs.append(r)
    runs.sort(key=lambda r: r.started_at, reverse=True)
    return runs[: max(1, min(limit, 200))]


# ---------------------------------------------------------------------
# Step (step-<id>.json) operations
# ---------------------------------------------------------------------


def _step_path(run_id: UUID | str, step_id: str) -> Path:
    return run_dir(run_id) / f"step-{step_id}.json"


def get_step(run_id: UUID | str, step_id: str) -> StepRun | None:
    p = _step_path(run_id, step_id)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return _step_payload_to_model(d)
    except Exception:
        return None


def _step_payload_to_model(d: dict) -> StepRun:
    return StepRun(
        run_id=UUID(d["run_id"]),
        step_id=d["step_id"],
        status=StepStatus(d["status"]),
        evidence=d.get("evidence") or {},
        verification_result=d.get("verification_result"),
        attempts=int(d.get("attempts", 0)),
        started_at=(
            datetime.fromisoformat(d["started_at"]) if d.get("started_at") else None
        ),
        ended_at=(
            datetime.fromisoformat(d["ended_at"]) if d.get("ended_at") else None
        ),
    )


def list_steps(run_id: UUID | str) -> list[StepRun]:
    d = runs_dir() / str(run_id)
    if not d.exists():
        return []
    out: list[StepRun] = []
    for p in sorted(d.glob("step-*.json")):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
            out.append(_step_payload_to_model(payload))
        except Exception:
            continue
    out.sort(key=lambda s: s.step_id)
    return out


def update_step(
    run_id: UUID | str,
    step_id: str,
    *,
    status: StepStatus | None = None,
    evidence: dict | None = None,
    verification_result: dict | None = None,
    bump_attempts: bool = False,
    set_started_at: datetime | None = None,
    set_ended_at: datetime | None = None,
) -> None:
    """Read-modify-write a single step file. Single writer (runtime), so
    no locking needed beyond the atomic rename in _atomic_write_json."""
    p = _step_path(run_id, step_id)
    current = (
        json.loads(p.read_text(encoding="utf-8"))
        if p.exists()
        else _empty_step(run_id if isinstance(run_id, UUID) else UUID(str(run_id)), step_id)
    )
    if status is not None:
        current["status"] = status.value
    if evidence is not None:
        current["evidence"] = evidence
    if verification_result is not None:
        current["verification_result"] = verification_result
    if bump_attempts:
        current["attempts"] = int(current.get("attempts", 0)) + 1
    if set_started_at is not None and current.get("started_at") is None:
        current["started_at"] = set_started_at.isoformat()
    if set_ended_at is not None:
        current["ended_at"] = set_ended_at.isoformat()
    _atomic_write_json(p, current)


def prior_steps_verified(
    run_id: UUID | str, template_step_ids: list[str], current_step: str | None
) -> bool:
    """True iff every step before current_step in template order is VERIFIED."""
    if current_step is None:
        return True
    required = []
    for sid in template_step_ids:
        if sid == current_step:
            break
        required.append(sid)
    if not required:
        return True
    for sid in required:
        step = get_step(run_id, sid)
        if step is None or step.status != StepStatus.VERIFIED:
            return False
    return True


# ---------------------------------------------------------------------
# Audit events (events.jsonl) operations
# ---------------------------------------------------------------------


def _event_to_record(event: AuditEvent) -> dict:
    return {
        "event_id": str(event.event_id),
        "timestamp": event.timestamp.isoformat(),
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "human_owner_id": event.human_owner_id,
        "run_id": str(event.run_id) if event.run_id else None,
        "step_id": event.step_id,
        "action_type": event.action_type,
        "tool": event.tool,
        "decision": event.decision.value if event.decision else None,
        "policy_id": event.policy_id,
        "reason": event.reason,
        "compliance_tags": list(event.compliance_tags or []),
        "payload_hash": event.payload_hash,
    }


def append_event(event: AuditEvent) -> None:
    """Append an event to the per-run stream and the global stream."""
    record = _event_to_record(event)
    # Per-run stream (authoritative for "what happened in this run").
    if event.run_id is not None:
        _append_jsonl(run_dir(event.run_id) / "events.jsonl", record)
    # Global stream (convenience mirror for cross-run queries).
    _append_jsonl(global_events_path(), record)


def list_events(run_id: UUID | str | None = None, limit: int = 100) -> list[dict]:
    """Return events (most recent first) up to limit."""
    if run_id is not None:
        path = run_dir(run_id) / "events.jsonl"
    else:
        path = global_events_path()
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[: max(1, min(limit, 500))]


# ---------------------------------------------------------------------
# Heartbeat (heartbeat.json) operations
# ---------------------------------------------------------------------


def write_heartbeat(hb: Heartbeat) -> None:
    _atomic_write_json(
        run_dir(hb.run_id) / "heartbeat.json",
        {
            "run_id": str(hb.run_id),
            "ttl_seconds": hb.ttl_seconds,
            "registered_at": hb.registered_at.isoformat(),
            "expires_at": hb.expires_at.isoformat(),
            "status": hb.status.value,
        },
    )


def read_heartbeat(run_id: UUID | str) -> Heartbeat | None:
    p = run_dir(run_id) / "heartbeat.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return Heartbeat(
            run_id=UUID(d["run_id"]),
            ttl_seconds=int(d["ttl_seconds"]),
            registered_at=datetime.fromisoformat(d["registered_at"]),
            expires_at=datetime.fromisoformat(d["expires_at"]),
            status=LivenessStatus(d["status"]),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------
# Reset (used by tests)
# ---------------------------------------------------------------------


def reset_state() -> None:
    """Delete all runs and the global events log. For tests only."""
    d = state_dir()
    if not d.exists():
        return
    for sub in ("runs", "events.jsonl"):
        target = d / sub
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            try:
                target.unlink()
            except FileNotFoundError:
                pass

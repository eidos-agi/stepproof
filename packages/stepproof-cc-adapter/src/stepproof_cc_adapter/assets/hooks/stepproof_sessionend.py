#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27"]
# ///
"""StepProof SessionEnd hook.

If a declared-plan run is bound to this session and still active, mark it as
abandoned so a future audit query sees why it stopped. Per ADR-0003, this is
more permissive than the heartbeat model (which suspends-then-expires) — a
clean session end is a definitive abandonment.

Exits 0 on any failure — must never break the session.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

DAEMON_URL = os.getenv("STEPPROOF_URL", "http://127.0.0.1:8787")
STATE_DIR = Path(os.getenv("STEPPROOF_STATE_DIR", ".stepproof"))
TIMEOUT_MS = int(os.getenv("STEPPROOF_TIMEOUT_MS", "2000"))


def _load_session(session_id: str) -> dict:
    p = STATE_DIR / "sessions" / f"{session_id}.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        exp = data.get("heartbeat_expires_at")
        if exp:
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if exp < now:
                return {}
        return data
    except Exception:
        return {}


def _call_abandon(run_id: str, reason: str) -> None:
    try:
        import httpx

        httpx.post(
            f"{DAEMON_URL.rstrip('/')}/runs/{run_id}/abandon",
            params={"reason": reason},
            timeout=TIMEOUT_MS / 1000,
        )
    except Exception:
        # Daemon unreachable — the run will eventually expire via heartbeat TTL.
        pass


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        session_id = event.get("session_id") or "unknown"
        reason = f"session_end:{event.get('reason', 'unknown')}"
        session = _load_session(session_id)
        run_id = session.get("run_id")
        if run_id:
            _call_abandon(run_id, reason)
        # Clean up local session file best-effort.
        try:
            p = STATE_DIR / "sessions" / f"{session_id}.json"
            if p.exists():
                p.unlink()
        except Exception:
            pass
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()

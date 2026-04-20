#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""StepProof SessionStart hook.

If a declared-plan run is bound to this session (via .stepproof/sessions/<id>.json),
inject its state into the worker's context at session boot via additionalContext.
This is how the worker knows where it is without having to rediscover it.

Exits 0 on any failure — must never break the session.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.getenv("STEPPROOF_STATE_DIR", ".stepproof"))


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


def _format_context(session: dict) -> str:
    lines = [
        "[StepProof] Active runbook detected for this session.",
        f"  run_id: {session.get('run_id', 'unknown')}",
        f"  template: {session.get('template_id', 'unknown')}",
        f"  current_step: {session.get('current_step', 'unknown')}",
    ]
    allowed = session.get("allowed_tools") or []
    denied = session.get("denied_tools") or []
    if allowed:
        lines.append(f"  allowed_tools: {', '.join(allowed)}")
    if denied:
        lines.append(f"  denied_tools: {', '.join(denied)}")
    lines.append(
        "  Use stepproof_step_complete with concrete evidence to advance. "
        "Actions outside the allowed set will be blocked by the PreToolUse gate."
    )
    return "\n".join(lines)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        session_id = event.get("session_id") or "unknown"
        session = _load_session(session_id)
        if not session.get("run_id"):
            # No active run — nothing to inject.
            sys.exit(0)

        context = _format_context(session)
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context,
                    }
                }
            )
        )
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()

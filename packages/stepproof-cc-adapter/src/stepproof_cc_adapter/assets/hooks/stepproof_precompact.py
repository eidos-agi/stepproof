#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""StepProof PreCompact hook.

Prevents the "forgot which step I was on" failure mode. Before Claude Code
compacts the transcript (manual or automatic), inject the active runbook state
via additionalContext so it survives compaction.

Same injection logic as SessionStart — different event, different lifecycle
point. Both guarantee the worker is oriented after the compaction boundary.

Exits 0 on any failure.
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


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        session_id = event.get("session_id") or "unknown"
        trigger = event.get("trigger", "auto")
        session = _load_session(session_id)
        if not session.get("run_id"):
            sys.exit(0)

        lines = [
            f"[StepProof] Compaction {trigger} — re-injecting runbook state.",
            f"  run_id: {session.get('run_id')}",
            f"  template: {session.get('template_id', 'unknown')}",
            f"  current_step: {session.get('current_step', 'unknown')}",
            "  Continue the declared plan. Use stepproof_run_status to refresh state.",
        ]
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreCompact",
                        "additionalContext": "\n".join(lines),
                    }
                }
            )
        )
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()

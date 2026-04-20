#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""StepProof PermissionRequest hook.

Per POSITIONING.md §Inline permission dialogs: StepProof avoids using the
PermissionRequest dialog as an inline approval gate (that's a terrible UX for
real agent loops). We log every permission request to the audit buffer for
traceability. If the daemon-side policy returned a transform decision recently,
we apply updatedInput here.

Exits 0 on any failure.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.getenv("STEPPROOF_STATE_DIR", ".stepproof"))
AUDIT_BUFFER_MAX_BYTES = int(os.getenv("STEPPROOF_AUDIT_BUFFER_MAX_BYTES", "1000000"))


def _buffer(event: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = STATE_DIR / "audit-buffer.jsonl"
        if p.exists() and p.stat().st_size > AUDIT_BUFFER_MAX_BYTES:
            return
        # Redact free-text tool_input fields that might carry secrets.
        ti = event.get("tool_input") or {}
        redacted = {k: ("<redacted>" if k in ("command", "content") else v) for k, v in ti.items()}
        record = {
            "kind": "permission_request",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "session_id": event.get("session_id"),
            "tool_name": event.get("tool_name"),
            "tool_use_id": event.get("tool_use_id"),
            "tool_input_keys": list(ti.keys()),
            "tool_input_redacted": redacted,
        }
        with p.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        _buffer(event)
        # We never allow/deny from this hook — that's PreToolUse's job.
        # Emit no decision body: Claude Code's default dialog behavior proceeds.
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()

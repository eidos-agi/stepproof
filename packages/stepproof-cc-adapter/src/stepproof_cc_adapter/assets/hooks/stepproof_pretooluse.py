#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6.0"]
# ///
"""StepProof PreToolUse adapter for Claude Code.

Exit-code contract (per docs/LESSONS_FROM_HOOKS_MASTERY.md):
  0 — continue / allow
  2 — block; stderr shown to Claude as denial reason
  any exception — caught and exits 0 (never break the session)

Logic:
  1. Load .stepproof/sessions/<session_id>.json for active run context
  2. Classify the tool call via action_classification.yaml
  3. Ring 0 → exit 0 (short-circuit, no daemon round-trip)
  4. Client-side deny (e.g., .env writes) → exit 2
  5. Ring 1+ → call /policy/evaluate on the daemon (500ms timeout)
  6. Daemon unreachable → log to audit buffer, fail-open (or fail-closed for configured rings)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path


def _glob_to_regex(pattern: str) -> re.Pattern:
    parts = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*" and i + 1 < len(pattern) and pattern[i + 1] == "*":
            parts.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == "/":
                i += 1
        elif c == "*":
            parts.append("[^/]*")
            i += 1
        elif c == "?":
            parts.append("[^/]")
            i += 1
        elif c in r".+^$(){}|\\":
            parts.append("\\" + c)
            i += 1
        else:
            parts.append(c)
            i += 1
    return re.compile("^" + "".join(parts) + "$")


def _glob_match(pattern: str, path: str) -> bool:
    return bool(_glob_to_regex(pattern).match(path))

DAEMON_URL = os.getenv("STEPPROOF_URL", "http://127.0.0.1:8787")
STATE_DIR = Path(os.getenv("STEPPROOF_STATE_DIR", ".stepproof"))
CLASSIFICATION_PATH = os.getenv(
    "STEPPROOF_CLASSIFICATION",
    str(Path(__file__).resolve().parents[1] / "action_classification.yaml"),
)
TIMEOUT_MS = int(os.getenv("STEPPROOF_TIMEOUT_MS", "500"))

# Fail-open is OPT-IN by default per code-review finding. When the daemon is
# unreachable, Ring 2+ actions are denied unless the operator sets
# STEPPROOF_FAIL_OPEN=1 — rejecting the earlier default that silently nullified
# enforcement during outages.
FAIL_OPEN = os.getenv("STEPPROOF_FAIL_OPEN", "0") == "1"
FAIL_CLOSED_RINGS = {
    int(r) for r in os.getenv("STEPPROOF_FAIL_CLOSED_RINGS", "").split(",") if r.strip()
}
# Audit buffer growth cap (bytes). Prevents local DoS from an always-down daemon.
AUDIT_BUFFER_MAX_BYTES = int(os.getenv("STEPPROOF_AUDIT_BUFFER_MAX_BYTES", "1000000"))


def _load_classification() -> tuple[dict, bool]:
    """Load the classification YAML. Returns (cls, loaded_ok).

    Per code-review finding: a silent classification-load failure previously
    returned {}, which combined with fail-open became a total bypass. Now we
    signal the failure to the caller so it can enforce a conservative posture.
    """
    try:
        import yaml

        with open(CLASSIFICATION_PATH, "r", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}), True
    except Exception:
        return {}, False


def _load_session(session_id: str) -> dict:
    p = STATE_DIR / "sessions" / f"{session_id}.json"
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        exp = data.get("heartbeat_expires_at")
        if exp:
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            if exp < now:
                return {}
        return data
    except Exception:
        return {}


# --- Inlined classifier (mirrors stepproof_cc_adapter.classifier) ---


def _apply_env_overrides(rule: dict, env: str | None) -> dict:
    ov = rule.get("env_overrides") or {}
    if env and env in ov:
        merged = dict(rule)
        merged.update(ov[env])
        return merged
    return rule


def _classify(tool_name: str, tool_input: dict, env: str | None, cls: dict) -> dict:
    # MCP tools first.
    if tool_name.startswith("mcp__"):
        for pat, rule in (cls.get("mcp_tools") or {}).items():
            try:
                if re.fullmatch(pat, tool_name):
                    return {
                        "action_type": rule.get("action_type", f"mcp.{tool_name}"),
                        "ring": int(rule.get("ring", 3)),
                    }
            except re.error:
                continue

    if tool_name == "Bash":
        cmd = (tool_input.get("command") or "").lstrip()
        for rule in cls.get("bash_patterns") or []:
            pat = rule.get("match", "")
            if pat and re.search(pat, cmd):
                applied = _apply_env_overrides(rule, env)
                return {
                    "action_type": applied.get("action_type", "shell.exec"),
                    "ring": int(applied.get("ring", 3)),
                    "deny": bool(applied.get("deny", False)),
                    "deny_reason": applied.get("deny_reason", ""),
                }

    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        if path:
            for rule in cls.get("path_classifications") or []:
                glob = rule.get("glob", "")
                if not glob:
                    continue
                if _glob_match(glob, path):
                    excl = rule.get("when_not_glob") or []
                    if any(_glob_match(e, path) for e in excl):
                        continue
                    return {
                        "action_type": rule.get("action_type", "filesystem.write"),
                        "ring": int(rule.get("ring", 1)),
                        "deny": bool(rule.get("deny", False)),
                        "deny_reason": rule.get("deny_reason", ""),
                    }

    entry = (cls.get("tools") or {}).get(tool_name)
    if entry is not None:
        return {
            "action_type": entry.get("action_type", f"tool.{tool_name.lower()}"),
            "ring": int(entry.get("ring", 3)),
        }

    return {"action_type": f"tool.{tool_name.lower()}", "ring": 3}


def _buffer_audit(payload: dict, reason: str) -> None:
    """Append an audit record. Caps file size and redacts free-text `message`
    to avoid capturing secrets per code-review finding."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = STATE_DIR / "audit-buffer.jsonl"
        if p.exists() and p.stat().st_size > AUDIT_BUFFER_MAX_BYTES:
            return  # Cap growth; a separate flush process will rotate.
        # Redact free-text message to prevent accidental secret capture.
        safe_payload = {k: v for k, v in payload.items() if k != "message"}
        if "message" in payload:
            safe_payload["message_len"] = len(payload.get("message") or "")
        with p.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "payload": safe_payload,
                        "reason": reason,
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def _call_daemon(payload: dict) -> dict | None:
    try:
        import httpx

        r = httpx.post(
            f"{DAEMON_URL.rstrip('/')}/policy/evaluate",
            json=payload,
            timeout=TIMEOUT_MS / 1000,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    try:
        tool_name = event.get("tool_name") or ""
        tool_input = event.get("tool_input") or {}
        session_id = event.get("session_id") or "unknown"

        session = _load_session(session_id)
        env = session.get("environment") or os.getenv("STEPPROOF_ENV", "staging")

        cls, cls_loaded = _load_classification()
        # Per code-review finding: when classification fails to load, do NOT
        # silently proceed with empty rules. Switch to a conservative posture:
        # Ring 3 for Bash/Write/Edit/Multi, Ring 0 only for well-known reads.
        if not cls_loaded:
            _buffer_audit(
                {"tool": tool_name, "actor_id": session_id},
                "classification-load-failed",
            )
            if tool_name in ("Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite"):
                sys.exit(0)
            if not FAIL_OPEN:
                print(
                    "[stepproof] classification unavailable; action blocked. "
                    "Set STEPPROOF_FAIL_OPEN=1 to override.",
                    file=sys.stderr,
                )
                sys.exit(2)
            sys.exit(0)

        result = _classify(tool_name, tool_input, env, cls)
        ring = result["ring"]

        # Client-side deny.
        if result.get("deny"):
            msg = f"[stepproof] {result.get('deny_reason') or 'client-side policy deny'}"
            print(msg, file=sys.stderr)
            sys.exit(2)

        # Ring 0 — never bother the daemon.
        if ring == 0:
            sys.exit(0)

        # Ring 1+ — consult daemon.
        payload = {
            "tool": tool_name,
            "action_type": result["action_type"],
            "ring": ring,
            "target_env": env,
            "run_id": session.get("run_id"),
            "step_id": session.get("current_step"),
            "actor_id": session_id,
            "human_owner_id": os.getenv("STEPPROOF_HUMAN_OWNER", "unknown"),
            "message": (tool_input.get("command") or "")[:500],
        }
        decision = _call_daemon(payload)

        if decision is None:
            _buffer_audit(payload, "daemon-unreachable")
            # Per code-review + Rhea ruling: fail-closed is the default. Ring 2+
            # blocks unless operator explicitly opts into fail-open. Ring 1
            # follows the same rule — structural denial is the correct behavior
            # when the policy engine cannot speak.
            if ring in FAIL_CLOSED_RINGS or not FAIL_OPEN:
                print(
                    f"[stepproof] runtime unreachable; Ring {ring} blocked. "
                    "Set STEPPROOF_FAIL_OPEN=1 to allow (not recommended for Ring 2+).",
                    file=sys.stderr,
                )
                sys.exit(2)
            sys.exit(0)  # explicit opt-in fail-open

        dec = decision.get("decision", "allow")
        if dec == "deny":
            msg = f"[stepproof {decision.get('policy_id', '')}] {decision.get('reason', 'blocked')}"
            if decision.get("suggested_tool"):
                msg += f" → try: {decision['suggested_tool']}"
            print(msg, file=sys.stderr)
            sys.exit(2)
        if dec == "transform":
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "decision": {
                        "behavior": "allow",
                        "updatedInput": decision.get("transformed_payload") or {},
                    },
                }
            }))
            sys.exit(0)
        if dec == "require_approval":
            print(
                f"[stepproof] approval required: {decision.get('approval_id', '')}",
                file=sys.stderr,
            )
            sys.exit(2)
        sys.exit(0)

    except Exception:
        # Never break the session.
        sys.exit(0)


if __name__ == "__main__":
    main()

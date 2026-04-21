# The Adapter Bridge — Hooks ↔ StepProof

The `PreToolUse` hook is the only hard enforcement Claude Code gives us. Everything StepProof promises — ring-based denial, runbook-step gating, policy decisions — has to flow through a ~20-line `uv` script fired by the Claude Code harness on every tool call. This doc is the load-bearing design for that bridge.

## The Five Hard Constraints

1. **Latency budget is tight.** The hook runs on every tool call. At 100ms added latency per call × 50 calls per session, that's an extra 5 seconds of session time purely from StepProof overhead. Target: sub-10ms for Ring 0 short-circuit, sub-50ms for decisions requiring a daemon round-trip.
2. **Hook has no memory.** Every invocation is a fresh Python process. No in-memory cache carries between calls. State lives on disk or in the daemon.
3. **Daemon may not be running.** StepProof graceful-degradation rule (GUARD-003): the hook must exit 0 if the daemon is unreachable. Enforcement degrades; the session doesn't die.
4. **Framework knowledge lives in the adapter, not the runtime.** Different agent frameworks (Claude Code, Cursor, LangChain, OpenAI Agents SDK) have different tool shapes. Classifying "is this a `database.write`?" depends on the framework. The runtime receives already-classified `PolicyInput`; the adapter does the classification.
5. **Hook output must conform to Claude Code's contract.** Exit 2 blocks, stderr carries the message, stdout JSON can transform. Nothing more.

## Architecture of the Bridge

```
┌─────────────────┐        stdin JSON         ┌─────────────────────┐
│   Claude Code   │ ─────────────────────────▶│  hook.py (uv)       │
│   (harness)     │                           │                     │
│                 │ ◀──── stderr + exit 2 ────│  1. read state      │
└─────────────────┘       (deny)              │  2. classify        │
        │                                     │  3. short-circuit   │
        │                                     │     Ring 0          │
        │ ◀──── stdout JSON + exit 0 ─────────│  4. call daemon     │
        │       (allow/transform)             │  5. fallback buffer │
                                              └──────────┬──────────┘
                                                         │ HTTP localhost
                                                         │ (500ms timeout)
                                                         ▼
                                              ┌──────────────────────┐
                                              │  stepproof-runtime   │
                                              │  (FastAPI + SQLite)  │
                                              └──────────────────────┘
                                                         ▲
                                                         │ state writes
                                                         │
   ┌──────────────────────┐                  ┌──────────────────────┐
   │ stepproof-mcp        │ ─── tool calls ──▶ .stepproof/sessions/ │
   │ (FastMCP stdio)      │                  │   <session_id>.json  │
   └──────────────────────┘                  └──────────────────────┘
                                                         ▲
                                                         │ read (per-hook)
                                                         │
                                                    hook.py
```

The hook and the MCP server are **two bridges that share state via a local file**. The MCP server writes session state on tool calls (`stepproof_run_start` → updates `.stepproof/sessions/<session_id>.json`). The hook reads it.

## The Four Sub-Systems

### A. Transport

HTTP over localhost TCP. Boring, correct, portable.

- Default port: `STEPPROOF_PORT=8787`.
- Timeout: 500ms. If exceeded → fallback (see D).
- Keep-alive not worth it at this scale; hook processes are one-shot.
- Future: Unix domain socket for ~2× speed on Unix; behind a flag. Not MVP.

Rejected alternatives:
- **In-process subprocess**: Python cold start is ~100ms. Unusable for per-call enforcement.
- **Direct SQLite query from the hook**: fast, but creates schema coupling — any runtime change breaks the hook. Only acceptable for offline audit-buffer flush.

### B. Shared Session State

File: `.stepproof/sessions/<session_id>.json`.

Written by: the MCP server, on tool calls that change run state. Never written by the hook.

```json
{
  "session_id": "claude-code-session-abc123",
  "run_id": "uuid",
  "template_id": "rb-db-migration-and-deploy",
  "current_step": "s3",
  "allowed_tools": ["cerebro_migrate_staging"],
  "denied_tools": ["psql", "pg_dump", "pg_restore"],
  "heartbeat_expires_at": "2026-04-20T16:30:00Z",
  "updated_at": "2026-04-20T16:25:10Z"
}
```

Read by: the hook on every invocation. If the file is missing, or `heartbeat_expires_at` has passed, the hook treats the session as having no active run.

The hook caches nothing across invocations — each run reads fresh. At <10 KB the read is sub-millisecond.

### C. Client-Side Classification

The adapter ships an `action_classification.yaml` that maps Claude Code tools to `action_type` + `ring`.

The concrete demand: the adapter needs enough context to classify "set Railway `DATABASE_URL`" as a production-cross-wiring action (Ring 3, deny without topology check), classify "run `psql` against prod" as a migration-bypass action (Ring 3, deny with sanctioned-tool suggestion), and classify "run an ad-hoc Python script that imports psycopg" as an unsanctioned-write (Ring 3, deny). A table of tool names alone is insufficient; the classification needs topology awareness.

```yaml
tools:
  Read:        { action_type: tool.read,       ring: 0 }
  Glob:        { action_type: tool.glob,       ring: 0 }
  Grep:        { action_type: tool.grep,       ring: 0 }
  Write:       { action_type: filesystem.write, ring: 1 }
  Edit:        { action_type: filesystem.write, ring: 1 }
  NotebookEdit:{ action_type: filesystem.write, ring: 1 }
  Bash:        { action_type: shell.exec,      ring: 3 }  # conservative default

bash_patterns:
  # When tool is Bash, match the command and promote/demote the classification.
  - match: "^psql\\b|^pg_dump\\b|^pg_restore\\b"
    action_type: database.write
    ring: 2
    env_overrides:
      production: { ring: 3 }
  - match: "^cerebro-migrate\\b"
    action_type: database.write
    ring: 2
    # Sanctioned tool — explicitly allowed at Ring 2 for the right step.
  - match: "^railway\\s+deploy\\b"
    action_type: deploy.production
    ring: 3
  - match: "^(ls|pwd|cat|head|tail|git\\s+(status|log|diff|show))\\b"
    ring: 0

mcp_tools:
  # MCP tools classified by their registered name.
  "mcp__cerebro__deploy_production": { action_type: deploy.production, ring: 3 }
  "mcp__stepproof__.*":              { action_type: stepproof.meta,    ring: 0 }

path_classifications:
  # When Write/Edit target-matches these globs, override ring.
  - glob: "migrations/**/*.sql"
    ring: 2
  - glob: "**/*.env*"
    ring: 3
    deny: true   # .env files are never a valid write target for agents
  - glob: "docs/**/*.md"
    ring: 1
```

The hook loads this once per invocation (it's small). Classification is a pure function of `(tool_name, tool_input, env)`. Deterministic, auditable, editable without touching the runtime.

### D. Graceful Degradation

If the daemon is unreachable, the hook:

1. Logs the attempted action to `.stepproof/audit-buffer.jsonl` (one event per line, append-only, no lock contention).
2. Emits a one-line stderr note: `[stepproof] runtime unreachable, allowing with audit buffer flag`.
3. Exits 0.

The daemon, on next startup, drains the buffer into the real audit log, flagging each event with `skipped=true`. Auditors see exactly which enforcement decisions were skipped and why.

Rationale: a StepProof outage in enforcement mode would brick every Claude Code session for every user. That's a worse incident than the risk of a few hours of unaudited activity. The buffer + flag model lets us recover the audit trail without stranding anyone.

**Exception**: for Ring 3 actions specifically, the hook can be configured (opt-in, per deployment) to **fail closed** — exit 2 with "StepProof unreachable; production-facing actions blocked until enforcement restored." Default is fail-open with audit; high-security deployments flip this.

### E. Runtime Discovery

The port `8787` is a last-resort fallback, not a load-bearing default. Every component participating in a session agrees on the runtime through `.stepproof/runtime.url`:

```json
{
  "url":        "http://127.0.0.1:54823",
  "pid":        41271,
  "started_at": "2026-04-20T16:24:01Z"
}
```

**Writer.** Whichever component owns the runtime — the MCP server's embedded runtime or a standalone `stepproof runtime` daemon — publishes the file atomically (tmp + fsync + rename) once its port is bound. It also registers an `atexit` hook and SIGTERM/SIGINT handlers so the file disappears on clean shutdown. The MCP server implementation lives in `packages/stepproof-mcp/src/stepproof_mcp/server.py`; the primitives it uses are in `packages/stepproof-state/`.

**Reader.** The hook resolves the daemon URL on each invocation:

1. Respect `STEPPROOF_URL` if the operator set one explicitly.
2. Otherwise read `.stepproof/runtime.url` and check that the writer's PID is still alive (`os.kill(pid, 0)`).
3. If the PID is dead, reap the stale file and fall back to `http://127.0.0.1:8787`. An unreachable runtime trips the usual graceful-degradation rules (D).

**Why PID-liveness, not URL ping.** The hook runs on every tool call; any extra HTTP round-trip dominates the latency budget. PID-liveness is a syscall. A live PID with a dead port is rare and will be caught by the actual policy-eval call a few milliseconds later; a dead PID with a stale URL file is common (`kill -9`, crashes) and must be reaped cheaply.

**Active-run binding.** When the agent declares a plan (`stepproof_keep_me_honest`) or starts a runbook (`stepproof_run_start`), the MCP server also writes `.stepproof/active-run.json`:

```json
{
  "run_id":        "uuid",
  "current_step":  "s2",
  "allowed_tools": ["Edit", "git"],
  "template_id":   "rb-declared-abc123"
}
```

The hook reads this alongside the session file. If `allowed_tools` is populated and the proposed tool is not in it, the hook exits 2 with a structural deny — no daemon round-trip needed. Per-step scoping runs before the Ring 0 short-circuit because keep-me-honest is a promise that the agent stays inside its declared toolset; a Read that wasn't declared is still a deviation worth surfacing.

See `docs/RUNTIME_HANDSHAKE.md` for the handshake protocol, failure modes, and test matrix.

## The Installation Surface

`stepproof install` is the single command that makes Claude Code aware of StepProof:

```
stepproof install
  → writes .claude/hooks/stepproof_pretooluse.py (uv single-file script)
  → writes .claude/hooks/stepproof_permissionrequest.py
  → writes .claude/hooks/stepproof_subagentstart.py
  → writes .claude/hooks/stepproof_sessionstart.py
  → writes .claude/hooks/stepproof_sessionend.py
  → writes .claude/hooks/stepproof_precompact.py
  → edits .claude/settings.json to register hooks with matchers
  → writes .claude/agents/stepproof/verifier-tier2.md (disallowedTools enforced)
  → writes .claude/commands/runbook-start.md (and 5 others)
  → edits .mcp.json to register stepproof MCP server
  → creates .stepproof/ with default config and action_classification.yaml
```

`stepproof uninstall` reverses all of the above (tracking via a manifest).

## The Hook Itself (Final Shape)

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""StepProof PreToolUse adapter."""
import json, os, sys, time
from pathlib import Path

DAEMON_URL = os.getenv("STEPPROOF_URL", "http://127.0.0.1:8787")
STATE_DIR = Path(os.getenv("STEPPROOF_STATE_DIR", ".stepproof"))
TIMEOUT_MS = 500
FAIL_CLOSED_RINGS = set(int(r) for r in os.getenv("STEPPROOF_FAIL_CLOSED_RINGS", "").split(",") if r)

def load_session(session_id: str) -> dict:
    p = STATE_DIR / "sessions" / f"{session_id}.json"
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text())
        exp = d.get("heartbeat_expires_at")
        if exp and exp < time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()):
            return {}
        return d
    except Exception:
        return {}

def classify(tool, tool_input, env) -> dict:
    # Loads action_classification.yaml, applies tool + bash + path rules.
    # Returns {action_type, ring, deny=False}
    ...

def buffer_audit(event: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with (STATE_DIR / "audit-buffer.jsonl").open("a") as f:
        f.write(json.dumps(event) + "\n")

def main():
    try:
        event = json.load(sys.stdin)
        tool, tool_input = event.get("tool_name"), event.get("tool_input", {})
        session_id = event.get("session_id", "unknown")

        session = load_session(session_id)
        cls = classify(tool, tool_input, os.getenv("STEPPROOF_ENV", "staging"))

        # Client-side deny (e.g., .env writes) — no need to bother the daemon.
        if cls.get("deny"):
            print(f"[stepproof] {cls.get('reason', 'client-side policy deny')}", file=sys.stderr)
            sys.exit(2)

        # Ring 0 short-circuit — never bother the daemon.
        if cls["ring"] == 0:
            sys.exit(0)

        # Call daemon.
        import httpx
        payload = {
            "tool": tool, "action_type": cls["action_type"], "ring": cls["ring"],
            "tool_input": tool_input, "run_id": session.get("run_id"),
            "step_id": session.get("current_step"), "actor_id": session_id,
        }
        try:
            r = httpx.post(f"{DAEMON_URL}/policy/evaluate", json=payload, timeout=TIMEOUT_MS / 1000)
            r.raise_for_status()
            d = r.json()
        except Exception:
            # Degrade.
            buffer_audit({"payload": payload, "reason": "daemon-unreachable"})
            if cls["ring"] in FAIL_CLOSED_RINGS:
                print(f"[stepproof] runtime unreachable; Ring {cls['ring']} blocked by fail-closed policy", file=sys.stderr)
                sys.exit(2)
            sys.exit(0)  # fail-open

        if d["decision"] == "deny":
            msg = f"[stepproof {d.get('policy_id','')}] {d.get('reason','blocked')}"
            if d.get("suggested_tool"): msg += f" → try: {d['suggested_tool']}"
            print(msg, file=sys.stderr)
            sys.exit(2)
        if d["decision"] == "transform":
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                "decision": {"behavior": "allow", "updatedInput": d["transformed_payload"]}}}))
            sys.exit(0)
        if d["decision"] == "require_approval":
            print(f"[stepproof] approval filed: {d.get('approval_id')}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    except Exception:
        sys.exit(0)  # Never break the session.

if __name__ == "__main__":
    main()
```

That's the entire bridge. ~80 lines. Classifies, short-circuits Ring 0, consults the daemon, enforces the decision, falls back gracefully.

## Why This Shape Works

- **Latency** — Ring 0 exits without network I/O. Ring 1+ is one localhost call with a 500ms ceiling. P95 should land under 30ms.
- **No memory** — every state read is a file read; the daemon is authoritative for anything durable.
- **Daemon outage tolerant** — buffer + exit 0 (or exit 2 for configured fail-closed rings).
- **Framework knowledge local** — `action_classification.yaml` is adapter-specific. Different adapters for Cursor, LangChain, etc. ship different classification files; the runtime is unchanged.
- **Auditable** — every decision (including fail-open skips) lands in the buffer or the daemon's audit log. No silent decisions.

## What's Next for the Bridge

Phase 2 actually builds it. The runtime and MCP already exist; Phase 2 is:

1. Ship `stepproof_cc_adapter` package: the 6 uv hook scripts, classification YAML, subagent definitions, slash commands, `install`/`uninstall` commands.
2. End-to-end test: a real Claude Code session, `stepproof install`, start a run, watch the hook block raw psql, watch the agent pick up the suggested tool.
3. Measure `denial_recovery_rate` over 10–20 real sessions. Tune the deny-message format based on what works.

Until that's done, StepProof is a runtime with no body. The bridge is the body.

#!/usr/bin/env python3
"""Tier 0 — scratch project, happy path.

Proves the MCP + verifier + audit-log chain works end-to-end
WITHOUT installing the PreToolUse hook. This is the Tier 0 shape
documented in docs/TIERS.md: evidence at step boundaries, verifier
gates advancement, audit log captures the run. No hook installed
means no session-wide gating and no catch-22 risk.

Flow:
  1. mktemp scratch project.
  2. git init + initial commit.
  3. Write .mcp.json pointing at stepproof binary.
  4. DO NOT run `stepproof install` — no hook.
  5. Spawn claude -p with rb-repo-simple template, ask agent to
     walk s1..s3 to COMPLETED.
  6. Assert:
       a. run status == completed
       b. all three step_completes submitted
       c. no off-scope tool denials appear (because there's no
          hook to deny anything — the point of Tier 0)
       d. audit log in runtime.db contains the causal chain
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STEPPROOF_BIN = REPO_ROOT / ".venv" / "bin" / "stepproof"
RUNBOOKS_DIR = REPO_ROOT / "examples"


class Err(RuntimeError):
    pass


def _ok(m: str) -> None:
    print(f"   ok  {m}")


def _fail(m: str) -> None:
    print(f"   FAIL  {m}")
    raise Err(m)


def _step(m: str) -> None:
    print(f"\n── {m}")


def scaffold(project: Path) -> None:
    (project / "tests").mkdir(parents=True)
    (project / "pyproject.toml").write_text(textwrap.dedent("""
        [project]
        name = "demo"
        version = "0.0.1"
        requires-python = ">=3.11"
        [tool.pytest.ini_options]
        testpaths = ["tests"]
    """).lstrip())
    (project / "tests" / "test_truth.py").write_text("def test_truth(): assert True\n")

    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Tier0", "GIT_AUTHOR_EMAIL": "tier0@example.com",
        "GIT_COMMITTER_NAME": "Tier0", "GIT_COMMITTER_EMAIL": "tier0@example.com",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=project, env=env, check=True)
    subprocess.run(["git", "add", "-A"], cwd=project, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=project, env=env, check=True)


def build_mcp_config(project: Path) -> Path:
    cfg = {
        "mcpServers": {
            "stepproof": {
                "type": "stdio",
                "command": str(STEPPROOF_BIN),
                "args": ["mcp"],
                "env": {
                    "STEPPROOF_STATE_DIR": str(project / ".stepproof"),
                    "STEPPROOF_RUNBOOKS_DIR": str(RUNBOOKS_DIR),
                },
            }
        }
    }
    p = project / ".mcp.json"
    p.write_text(json.dumps(cfg, indent=2))
    return p


PROMPT = textwrap.dedent("""
Walk the `rb-repo-simple` ceremony to completion. Tier 0 — no hook
is installed; the MCP + verifiers enforce at step boundaries.

1. Start run: mcp__stepproof__stepproof_run_start(
     template_id="rb-repo-simple",
     owner_id="tier0-happy",
     environment="staging")

2. For each step in order (s1, s2, s3):
   - s1 (write file): use Write to create HELLO.md with ≥1 line.
     Evidence: path="HELLO.md", min_lines=1
   - s2 (tests green): run
       pytest tests/ 2>&1 | tee /tmp/tier0-pytest.out
     Evidence: pytest_output_path="/tmp/tier0-pytest.out", min_passed=1
   - s3 (commit): run
       git add HELLO.md && git commit -m "feat: tier0 HELLO"
       git rev-parse HEAD
     Evidence: commit_sha=<the SHA>

3. When status=completed, report briefly and stop.

Work inside each step freely — no hook will intercept your tool
calls. Advancement is gated by the verifier reading real state, not
by tool scope.
""")


def parse_stream(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        s = line.strip()
        if s:
            try:
                events.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    return events


def summarize(events: list[dict]) -> dict:
    s = {"tool_uses": [], "tool_inputs": [], "hook_events": [], "assistant_text": []}
    for e in events:
        if e.get("type") == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    s["tool_uses"].append(b.get("name", ""))
                    s["tool_inputs"].append((b.get("name", ""), b.get("input", {})))
                elif b.get("type") == "text":
                    s["assistant_text"].append(b.get("text", ""))
        elif e.get("type") == "system" and "hook" in str(e.get("subtype", "")).lower():
            s["hook_events"].append(e)
    return s


def run_claude(project: Path, cfg: Path, timeout_s: int):
    cmd = [
        "claude", "-p", "--dangerously-skip-permissions",
        "--mcp-config", str(cfg),
        "--output-format", "stream-json",
        "--include-hook-events", "--verbose",
        PROMPT,
    ]
    env = os.environ.copy()
    env.pop("STEPPROOF_STATE_DIR", None)
    env["PATH"] = f"{REPO_ROOT}/.venv/bin:" + env.get("PATH", "")
    try:
        p = subprocess.run(
            cmd, cwd=str(project), env=env,
            capture_output=True, text=True, timeout=timeout_s,
        )
        return p.returncode, parse_stream(p.stdout)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return 124, parse_stream(out)


def query_audit_log(state_dir: Path) -> list[tuple[str, str]]:
    import sqlite3
    db = state_dir / "runtime.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT action_type, policy_id FROM audit_log ORDER BY timestamp"
    ).fetchall()
    conn.close()
    return rows


def run(project: Path, timeout_s: int) -> dict:
    scaffold(project)
    cfg = build_mcp_config(project)
    state = project / ".stepproof"

    rc, events = run_claude(project, cfg, timeout_s)
    summary = summarize(events)

    step_completes = [
        (inp or {}).get("step_id")
        for (name, inp) in summary["tool_inputs"]
        if name == "mcp__stepproof__stepproof_step_complete"
    ]

    ar = state / "active-run.json"
    sp_status = "cleared" if not ar.exists() else (
        f"active(step={json.loads(ar.read_text()).get('current_step')})"
    )

    audit_rows = query_audit_log(state)

    stepproof_hooks_in_stream = [
        e for e in summary["hook_events"]
        if "stepproof" in json.dumps(e).lower()
    ]

    return {
        "rc": rc,
        "stepproof_run_status": sp_status,
        "step_ids_completed": step_completes,
        "audit_log_row_count": len(audit_rows),
        "audit_log_action_types": sorted({a for a, _ in audit_rows}),
        "stepproof_hook_events_seen": len(stepproof_hooks_in_stream),
        "tool_uses_total": len(summary["tool_uses"]),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    project = Path(tempfile.mkdtemp(prefix="sp-tier0-happy-"))
    print(f"scratch: {project}")
    try:
        r = run(project, args.timeout)
        print(json.dumps(r, indent=2))

        _step("ASSERTIONS")

        if r["stepproof_run_status"] != "cleared":
            _fail(f"run not completed: {r['stepproof_run_status']}")
        _ok("run COMPLETED")

        completed = [s for s in r["step_ids_completed"] if s]
        if not set(completed) >= {"s1", "s2", "s3"}:
            _fail(f"missing steps: {completed}")
        _ok(f"all 3 steps verified (calls: {completed})")

        if r["audit_log_row_count"] < 4:
            _fail(f"audit log too short: {r['audit_log_row_count']} rows")
        _ok(f"audit log has {r['audit_log_row_count']} rows")

        if "step.complete" not in r["audit_log_action_types"]:
            _fail("no step.complete in audit log")
        _ok(f"audit contains: {r['audit_log_action_types']}")

        # Tier 0: hook should NOT have fired, because no hook is installed.
        if r["stepproof_hook_events_seen"] > 0:
            _fail(f"hook events seen in Tier 0 stream: {r['stepproof_hook_events_seen']}")
        _ok("no PreToolUse hook events (as expected for Tier 0)")

        print("\nTIER 0 HAPPY PATH PASSED — MCP + verifiers + audit log, no hook.")
    except Err as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(project, ignore_errors=True)
        else:
            print(f"\n(left at {project})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Simplest end-to-end proof that StepProof (MCP + hook + runbook)
gates a real Claude Code session.

Scratch repo, three-step ceremony (rb-repo-simple), claude -p run.
Task: write a trivial marker file, prove the pytest suite is still
green in the scratch repo's own tests, commit the change.

Passes iff the StepProof run reaches COMPLETED, each step verifier
passed, and there's a new real commit in the scratch repo.
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
PY = sys.executable
RUNBOOKS_DIR = REPO_ROOT / "examples"


class Err(RuntimeError):
    pass


def _ok(m): print(f"   ok  {m}")
def _fail(m): print(f"   FAIL  {m}"); raise Err(m)
def _step(m): print(f"\n── {m}")


def _run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=True)


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
        "GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com",
        "GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com",
    }
    _run(["git", "init", "-q", "-b", "main"], cwd=project, env=env)
    _run(["git", "add", "-A"], cwd=project, env=env)
    _run(["git", "commit", "-q", "-m", "initial"], cwd=project, env=env)


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
Your task: walk this repo's 3-step StepProof ceremony to COMPLETED.

1. Start a run: mcp__stepproof__stepproof_run_start(
     template_id="rb-repo-simple", owner_id="demo", environment="staging"
   ) — remember the run_id.

2. For each step returned as current_step, do the work then submit
   evidence via mcp__stepproof__stepproof_step_complete.

   - s1 (write file): use Write to create "HELLO.md" with at least
     one non-empty line. Evidence:
         path="HELLO.md", min_lines=1
   - s2 (tests green): run
         pytest tests/ 2>&1 | tee /tmp/sp-simple-pytest.out
     Evidence:
         pytest_output_path="/tmp/sp-simple-pytest.out", min_passed=1
   - s3 (commit): run
         git add HELLO.md && git commit -m "feat: add HELLO marker"
     Capture the SHA via:
         git rev-parse HEAD
     Evidence:
         commit_sha=<the SHA>

3. When status=completed, report one sentence and stop.

Stay strictly within each step's allowed_tools. Don't try to route around
the hook if it blocks you.
""")


def parse_stream(raw: str) -> list[dict]:
    out = []
    for line in raw.splitlines():
        s = line.strip()
        if s:
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    return out


def summarize(events: list[dict]) -> dict:
    s = {"tool_uses": [], "tool_inputs": [], "tool_results": [], "assistant_text": []}
    for e in events:
        if e.get("type") == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    s["tool_uses"].append(b.get("name", ""))
                    s["tool_inputs"].append((b.get("name", ""), b.get("input", {})))
                elif b.get("type") == "text":
                    s["assistant_text"].append(b.get("text", ""))
        elif e.get("type") == "user":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "tool_result":
                    s["tool_results"].append(
                        {"is_error": b.get("is_error", False),
                         "content": str(b.get("content", ""))[:400]}
                    )
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
    env.pop("STEPPROOF_CLASSIFICATION", None)
    env.pop("STEPPROOF_URL", None)
    env.pop("STEPPROOF_STATE_DIR", None)
    env["STEPPROOF_HUMAN_OWNER"] = "demo"
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


def run(project: Path, timeout_s: int) -> dict:
    from stepproof_cc_adapter import installer

    scaffold(project)
    installer.install(scope="project", project_dir=project)
    cfg = build_mcp_config(project)
    state = project / ".stepproof"

    rc, events = run_claude(project, cfg, timeout_s)
    summary = summarize(events)

    step_completes = [
        inp for (name, inp) in summary["tool_inputs"]
        if name == "mcp__stepproof__stepproof_step_complete"
    ]
    step_ids = [(inp or {}).get("step_id") for inp in step_completes]

    ar = state / "active-run.json"
    sp_status = "cleared" if not ar.exists() else (
        f"active(step={json.loads(ar.read_text()).get('current_step')})"
    )

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, capture_output=True, text=True
    ).stdout.strip()
    commits = subprocess.run(
        ["git", "log", "--oneline"], cwd=project, capture_output=True, text=True
    ).stdout.strip().splitlines()

    hello = (project / "HELLO.md").exists()

    final_text = summary["assistant_text"][-1] if summary["assistant_text"] else ""

    return {
        "rc": rc,
        "stepproof_run_status": sp_status,
        "step_ids_completed": step_ids,
        "hello_file_exists": hello,
        "head_sha": head_sha[:12],
        "commits": commits,
        "tool_uses_total": len(summary["tool_uses"]),
        "final_text": final_text[:400],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    project = Path(tempfile.mkdtemp(prefix="sp-simple-"))
    print(f"scratch project: {project}")
    try:
        result = run(project, args.timeout)
        print(json.dumps(result, indent=2))

        _step("ASSERTIONS")
        if result["stepproof_run_status"] != "cleared":
            _fail(f"run not completed: {result['stepproof_run_status']}")
        _ok("run COMPLETED")

        completed = [s for s in result["step_ids_completed"] if s]
        if not (set(completed) == {"s1", "s2", "s3"}):
            _fail(f"step coverage wrong: {completed}")
        _ok(f"all three steps completed (attempts: {completed})")

        if not result["hello_file_exists"]:
            _fail("HELLO.md was not created")
        _ok("HELLO.md exists on disk")

        if len(result["commits"]) < 2:
            _fail(f"no new commit: {result['commits']}")
        _ok(f"new commit made: {result['commits'][0]}")

        print("\nSIMPLE CEREMONY PASSED — MCP + hook + 3-step runbook worked end-to-end.")
    except Err as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(project, ignore_errors=True)
        else:
            print(f"\n(leaving scratch at {project})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

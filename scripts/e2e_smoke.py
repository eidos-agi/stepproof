#!/usr/bin/env python3
"""End-to-end smoke test for the runtime handshake (increment 1).

Unlike ``tests/integration/test_runtime_handshake.py`` — which drives the
*source-tree* hook directly — this script runs the full user-visible flow
against the *installed* copy produced by ``stepproof install``:

1.  Create a throwaway project dir under ``/tmp``.
2.  ``stepproof install --scope project --project-dir <tmp>`` → writes
    ``.claude/hooks/stepproof_pretooluse.py`` + classification YAML +
    ``settings.json`` registration + ``.stepproof/adapter-manifest.json``.
3.  Spawn the MCP server (subprocess, STEPPROOF_STATE_DIR=tmp/.stepproof).
4.  Confirm ``.stepproof/runtime.url`` is published with the MCP's PID.
5.  Ping the runtime's ``/health`` endpoint.
6.  Write a synthetic ``active-run.json`` (standing in for what
    ``keep_me_honest`` would write) and fire the INSTALLED hook with a tool
    event. Assert the hook:
        - allows a tool that is in ``allowed_tools``;
        - denies a tool that isn't, citing the step_id.
7.  SIGTERM the MCP. Confirm ``runtime.url`` is reaped.
8.  ``stepproof uninstall`` and assert ``.claude/`` is clean.

Prints pass/fail per step; exits non-zero on any failure. Intended to be
run between code changes — "did I break the user-visible contract?" —
and before cutting a release.

Usage:
    uv run python scripts/e2e_smoke.py
    uv run python scripts/e2e_smoke.py --keep    # leave the tmp project
                                                 # for inspection
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "integration" / "_mcp_driver.py"


class SmokeError(RuntimeError):
    pass


def _step(msg: str) -> None:
    print(f"\n── {msg}")


def _ok(msg: str) -> None:
    print(f"   ok  {msg}")


def _fail(msg: str) -> None:
    print(f"   FAIL  {msg}")
    raise SmokeError(msg)


def _spawn_driver(state_dir: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_dir)
    env.pop("STEPPROOF_URL", None)
    proc = subprocess.Popen(
        [sys.executable, str(DRIVER)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert proc.stdout is not None
    # Wait for the first stdout line — the base URL.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = (proc.stderr.read() if proc.stderr else "") or ""
            _fail(f"driver exited early: rc={proc.returncode}\n{stderr}")
        line = proc.stdout.readline()
        if line:
            return proc
    proc.kill()
    _fail("driver did not announce its URL in time")
    raise SmokeError("unreachable")


def _run_installed_hook(
    hook_path: Path,
    state_dir: Path,
    classification_yaml: Path,
    event: dict,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_dir)
    env["STEPPROOF_CLASSIFICATION"] = str(classification_yaml)
    env["STEPPROOF_HUMAN_OWNER"] = "e2e-smoke"
    env["STEPPROOF_FAIL_OPEN"] = "0"
    env.pop("STEPPROOF_URL", None)
    return subprocess.run(
        [sys.executable, str(hook_path)],
        input=json.dumps(event),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def run(keep: bool) -> None:
    from stepproof_cc_adapter import installer
    from stepproof_state import read_runtime_record

    project = Path(tempfile.mkdtemp(prefix="stepproof-smoke-"))
    print(f"tmp project: {project}")
    state_dir = project / ".stepproof"
    claude_dir = project / ".claude"
    hook_path = claude_dir / "hooks" / "stepproof_pretooluse.py"
    classification_yaml = claude_dir / "stepproof" / "action_classification.yaml"

    driver: subprocess.Popen[str] | None = None

    try:
        # -----------------------------------------------------------------
        _step("1. stepproof install --scope project")
        manifest = installer.install(scope="project", project_dir=project)
        if not hook_path.exists():
            _fail(f"hook not installed at {hook_path}")
        if not classification_yaml.exists():
            _fail(f"classification YAML not installed at {classification_yaml}")
        if not (project / ".stepproof" / "adapter-manifest.json").exists():
            _fail("adapter-manifest.json not written")
        _ok(f"installed {len(manifest.files_written)} files under {claude_dir}")

        # -----------------------------------------------------------------
        _step("2. spawn MCP driver")
        driver = _spawn_driver(state_dir)
        record = read_runtime_record(base=state_dir)
        if record is None:
            _fail("runtime.url not published")
        if record.pid != driver.pid:
            _fail(f"runtime.url PID mismatch: expected {driver.pid}, got {record.pid}")
        _ok(f"runtime.url = {record.url} (pid {record.pid})")

        # -----------------------------------------------------------------
        _step("3. ping /health")
        r = httpx.get(f"{record.url}/health", timeout=3.0)
        if r.status_code != 200:
            _fail(f"/health returned {r.status_code}")
        _ok(f"/health → {r.json()}")

        # -----------------------------------------------------------------
        _step("4. POST /plans/declare (the real keep_me_honest flow)")
        plan = {
            "intent": "e2e smoke — declared plan with one Write step",
            "environment": "staging",
            "owner_id": "e2e-smoke",
            "agent_id": "claude-code-worker",
            "risk_level": "low",
            "steps": [
                {
                    "step_id": "s-write-only",
                    "description": "Write a smoke file",
                    "required_evidence": ["file_path", "line_count"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Write"],
                }
            ],
        }
        pr = httpx.post(f"{record.url}/plans/declare", json=plan, timeout=5.0)
        if pr.status_code != 200:
            _fail(f"/plans/declare returned {pr.status_code}: {pr.text}")
        pdata = pr.json()
        run = pdata.get("run") or {}
        real_run_id = run.get("run_id")
        real_step = run.get("current_step")
        if not real_run_id or not real_step:
            _fail(f"declared plan missing run fields: {pdata}")
        _ok(f"run_id={real_run_id}  step={real_step}")

        active_run_path = state_dir / "active-run.json"
        active_run_path.write_text(
            json.dumps(
                {
                    "run_id": real_run_id,
                    "current_step": real_step,
                    "allowed_tools": ["Write"],
                    "template_id": pdata.get("template_id"),
                }
            )
        )
        _ok(f"wrote {active_run_path.name}")

        # -----------------------------------------------------------------
        _step("5a. installed hook allows Write (in allowed_tools)")
        event_allow = {
            "session_id": "smoke-session",
            "tool_name": "Write",
            "tool_input": {"file_path": str(project / "doc.md"), "content": "x"},
        }
        out = _run_installed_hook(hook_path, state_dir, classification_yaml, event_allow)
        if out.returncode != 0:
            _fail(f"Write was blocked unexpectedly: rc={out.returncode}\n{out.stderr}")
        _ok("Write allowed")

        _step("5b. installed hook denies Bash (not in allowed_tools)")
        event_deny = {
            "session_id": "smoke-session",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
        }
        out = _run_installed_hook(hook_path, state_dir, classification_yaml, event_deny)
        if out.returncode != 2:
            _fail(
                f"Bash was allowed but should have been denied: rc={out.returncode}\n"
                f"stderr={out.stderr!r}"
            )
        if "s-write-only" not in out.stderr:
            _fail(f"deny reason missing step_id: {out.stderr!r}")
        _ok(f"Bash denied: {out.stderr.strip()}")

        # -----------------------------------------------------------------
        _step("5c. installed hook denies .env write (client-side rule)")
        event_dotenv = {
            "session_id": "smoke-session",
            "tool_name": "Write",
            "tool_input": {"file_path": str(project / ".env"), "content": "SECRET=1"},
        }
        out = _run_installed_hook(hook_path, state_dir, classification_yaml, event_dotenv)
        if out.returncode != 2:
            _fail(f".env write was not denied: rc={out.returncode}")
        _ok(f".env denied: {out.stderr.strip()}")

        # -----------------------------------------------------------------
        _step("6. SIGTERM driver → runtime.url reaped")
        driver.send_signal(signal.SIGTERM)
        try:
            driver.wait(timeout=5)
        except subprocess.TimeoutExpired:
            driver.kill()
            driver.wait(timeout=2)
        driver = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and (state_dir / "runtime.url").exists():
            time.sleep(0.05)
        if (state_dir / "runtime.url").exists():
            _fail("runtime.url was not removed on SIGTERM")
        _ok("runtime.url cleaned up")

        # -----------------------------------------------------------------
        _step("7. stepproof uninstall")
        summary = installer.uninstall(project_dir=project)
        if claude_dir.exists() and (claude_dir / "hooks").exists():
            leftover = list((claude_dir / "hooks").glob("stepproof_*.py"))
            if leftover:
                _fail(f"leftover hook files after uninstall: {leftover}")
        _ok(f"removed {summary.get('files_removed', 0)} files")

        print("\nALL CHECKS PASSED")
    finally:
        if driver is not None and driver.poll() is None:
            driver.kill()
            driver.wait(timeout=2)
        if not keep:
            shutil.rmtree(project, ignore_errors=True)
        else:
            print(f"\n(leaving tmp project at {project})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="do not delete the tmp project on exit",
    )
    args = parser.parse_args()
    try:
        run(keep=args.keep)
    except SmokeError as e:
        print(f"\nSMOKE FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

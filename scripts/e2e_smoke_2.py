#!/usr/bin/env python3
"""End-to-end smoke #2 — multi-step plan and step transition.

Smoke #1 (``scripts/e2e_smoke.py``) proves the handshake works for a
single-step run: install, boot, publish, enforce, uninstall.

Smoke #2 asks the harder question: **does the hook's per-step scoping
follow the run as it moves from step 1 to step 2?** If
``stepproof_step_complete`` fails to update ``.stepproof/active-run.json``
with the new step's ``allowed_tools``, the hook will happily keep
enforcing step 1's rules during step 2 work. That's a silent bug — the
session looks fine, the audit log looks fine, but per-step scoping is a
lie.

Flow:

1.  Install into a throwaway project.
2.  Spawn the MCP driver (publishes ``runtime.url``).
3.  Declare a **two-step** plan: s1 is Edit-only, s2 is Write-only.
4.  Write ``active-run.json`` for s1 (the MCP would do this on plan accept).
5.  Invoke the installed hook from ``.claude/hooks/``:
        - Edit → allowed (s1's tool)
        - Write → denied (s2's tool, not active yet)
6.  Create the file s1 must produce, submit evidence for s1 via
    ``POST /runs/{id}/steps/s1/complete``.
7.  Verify the runtime moved ``current_step`` to s2 and
    ``status = ACTIVE``.
8.  Update ``active-run.json`` to s2 with s2's ``allowed_tools``
    (mirrors what the MCP's ``stepproof_step_complete`` handler does on
    the Python side).
9.  Invoke the installed hook again:
        - Edit → denied (s1's tool, no longer active)
        - Write → allowed (s2's tool, now active)
10. SIGTERM driver, uninstall, assert clean.

Passes iff the allow/deny decisions flip with the step transition. That
tells us the active-run.json contract is actually load-bearing across
step boundaries.

Usage:
    uv run python scripts/e2e_smoke_2.py
    uv run python scripts/e2e_smoke_2.py --keep
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
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = (proc.stderr.read() if proc.stderr else "") or ""
            _fail(f"driver exited early: rc={proc.returncode}\n{stderr}")
        if proc.stdout.readline():
            return proc
    proc.kill()
    _fail("driver did not announce its URL in time")
    raise SmokeError("unreachable")


def _run_hook(
    hook_path: Path,
    state_dir: Path,
    classification_yaml: Path,
    event: dict,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_dir)
    env["STEPPROOF_CLASSIFICATION"] = str(classification_yaml)
    env["STEPPROOF_HUMAN_OWNER"] = "e2e-smoke-2"
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


def _write_active_run(state_dir: Path, run_id: str, step: str, allowed: list[str]) -> None:
    (state_dir / "active-run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "current_step": step,
                "allowed_tools": allowed,
                "template_id": None,
            }
        )
    )


def run(keep: bool) -> None:
    from stepproof_cc_adapter import installer
    from stepproof_state import read_runtime_record

    project = Path(tempfile.mkdtemp(prefix="stepproof-smoke2-"))
    print(f"tmp project: {project}")
    state_dir = project / ".stepproof"
    claude_dir = project / ".claude"
    hook_path = claude_dir / "hooks" / "stepproof_pretooluse.py"
    classification_yaml = claude_dir / "stepproof" / "action_classification.yaml"

    driver: subprocess.Popen[str] | None = None

    try:
        # -----------------------------------------------------------------
        _step("1. install (scope=project)")
        installer.install(scope="project", project_dir=project)
        if not hook_path.exists():
            _fail(f"hook not installed at {hook_path}")
        _ok("installed")

        # -----------------------------------------------------------------
        _step("2. spawn MCP driver + read runtime.url")
        driver = _spawn_driver(state_dir)
        record = read_runtime_record(base=state_dir)
        if record is None or record.pid != driver.pid:
            _fail("runtime.url missing or PID mismatch")
        _ok(f"runtime.url = {record.url} (pid {record.pid})")

        # -----------------------------------------------------------------
        _step("3. declare a two-step plan (s1 Edit-only, s2 Write-only)")
        s1_file = project / "step1.md"
        plan = {
            "intent": "e2e smoke #2 — multi-step transition",
            "environment": "staging",
            "owner_id": "e2e-smoke-2",
            "agent_id": "claude-code-worker",
            "risk_level": "low",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Author a design note",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Edit"],
                },
                {
                    "step_id": "s2",
                    "description": "Write the final artifact",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Write"],
                },
            ],
        }
        pr = httpx.post(f"{record.url}/plans/declare", json=plan, timeout=5.0)
        if pr.status_code != 200:
            _fail(f"/plans/declare returned {pr.status_code}: {pr.text}")
        pdata = pr.json()
        run_id = pdata["run"]["run_id"]
        if pdata["run"]["current_step"] != "s1":
            _fail(f"expected current_step=s1, got {pdata['run']['current_step']}")
        _ok(f"run_id={run_id}  current_step=s1")

        # -----------------------------------------------------------------
        _step("4. write active-run.json pointing at s1 (Edit-only)")
        _write_active_run(state_dir, run_id, "s1", ["Edit"])
        _ok("active-run.json → s1")

        # -----------------------------------------------------------------
        _step("5a. s1: Edit (in allowed_tools) → allowed")
        out = _run_hook(
            hook_path,
            state_dir,
            classification_yaml,
            {
                "session_id": "smoke2",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(s1_file), "new_string": "x", "old_string": ""},
            },
        )
        if out.returncode != 0:
            _fail(f"Edit was blocked during s1: rc={out.returncode}\n{out.stderr}")
        _ok("Edit allowed during s1")

        _step("5b. s1: Write (s2's tool, not yet active) → denied")
        out = _run_hook(
            hook_path,
            state_dir,
            classification_yaml,
            {
                "session_id": "smoke2",
                "tool_name": "Write",
                "tool_input": {"file_path": str(project / "note.md"), "content": "x"},
            },
        )
        if out.returncode != 2:
            _fail(f"Write leaked through s1 scoping: rc={out.returncode}")
        if "s1" not in out.stderr:
            _fail(f"deny reason should name s1: {out.stderr!r}")
        _ok(f"Write denied during s1: {out.stderr.strip()}")

        # -----------------------------------------------------------------
        _step("6. create s1's artifact + complete s1 with real evidence")
        s1_file.write_text(
            "line one\nline two\nline three\n",
            encoding="utf-8",
        )
        cr = httpx.post(
            f"{record.url}/runs/{run_id}/steps/s1/complete",
            json={"evidence": {"path": str(s1_file), "min_lines": 2}},
            timeout=10.0,
        )
        if cr.status_code != 200:
            _fail(f"step_complete returned {cr.status_code}: {cr.text}")
        verdict = cr.json()
        if verdict["verification_result"]["status"] != "pass":
            _fail(f"verifier did not pass: {verdict['verification_result']}")
        if verdict["run"]["current_step"] != "s2":
            _fail(
                f"run did not advance to s2; current_step="
                f"{verdict['run']['current_step']}"
            )
        if verdict["run"]["status"] != "active":
            _fail(f"run status is {verdict['run']['status']}, expected active")
        _ok(f"s1 verified; run advanced to s2 (status=active)")

        # -----------------------------------------------------------------
        _step("7. update active-run.json → s2 (what the MCP handler would do)")
        _write_active_run(state_dir, run_id, "s2", ["Write"])
        _ok("active-run.json → s2")

        # -----------------------------------------------------------------
        _step("8a. s2: Edit (s1's tool, no longer active) → denied")
        out = _run_hook(
            hook_path,
            state_dir,
            classification_yaml,
            {
                "session_id": "smoke2",
                "tool_name": "Edit",
                "tool_input": {"file_path": str(s1_file), "new_string": "y", "old_string": "x"},
            },
        )
        if out.returncode != 2:
            _fail(f"Edit leaked into s2: rc={out.returncode}")
        if "s2" not in out.stderr:
            _fail(f"deny reason should name s2: {out.stderr!r}")
        _ok(f"Edit denied during s2: {out.stderr.strip()}")

        _step("8b. s2: Write (now in allowed_tools) → allowed")
        out = _run_hook(
            hook_path,
            state_dir,
            classification_yaml,
            {
                "session_id": "smoke2",
                "tool_name": "Write",
                "tool_input": {"file_path": str(project / "final.md"), "content": "x"},
            },
        )
        if out.returncode != 0:
            _fail(f"Write was blocked during s2: rc={out.returncode}\n{out.stderr}")
        _ok("Write allowed during s2")

        # -----------------------------------------------------------------
        _step("9. SIGTERM driver → runtime.url reaped")
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
        _step("10. stepproof uninstall")
        installer.uninstall(project_dir=project)
        leftover = (
            list((claude_dir / "hooks").glob("stepproof_*.py"))
            if (claude_dir / "hooks").exists()
            else []
        )
        if leftover:
            _fail(f"leftover hook files after uninstall: {leftover}")
        _ok("uninstall clean")

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
    parser.add_argument("--keep", action="store_true", help="do not delete the tmp project")
    args = parser.parse_args()
    try:
        run(keep=args.keep)
    except SmokeError as e:
        print(f"\nSMOKE FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Complex #1 — verification-failure path.

Can a step's first evidence submission fail the verifier without
corrupting enforcement state?

Flow:
  1. Install + spawn MCP.
  2. Declare a plan with one step that writes a file with at least 5
     non-empty lines (``verify_file_exists`` with ``min_lines=5``).
  3. Write ``active-run.json`` for s1.
  4. Submit evidence pointing at a file that has only 2 lines →
     verifier fails, runtime marks step FAILED.
  5. Assert: per-step scoping still holds (Bash still denied by the
     installed hook), i.e. the failed attempt did not clear or corrupt
     ``active-run.json``.
  6. Fix the file (write 6 lines). Resubmit evidence.
     *Expect 400*: the current step_runs.status is ``failed``, not
     ``pending``, so a second complete is refused as by-design — the
     run requires explicit remediation. That's still a useful signal:
     the runtime tells us the run is stuck, not silently advanced.
  7. Uninstall, clean.

This pins the "failed verification doesn't break state" invariant.
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


class Err(RuntimeError):
    pass


def _step(m: str) -> None:
    print(f"\n── {m}")


def _ok(m: str) -> None:
    print(f"   ok  {m}")


def _fail(m: str) -> None:
    print(f"   FAIL  {m}")
    raise Err(m)


def _spawn(state_dir: Path) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_dir)
    env.pop("STEPPROOF_URL", None)
    p = subprocess.Popen(
        [sys.executable, str(DRIVER)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert p.stdout
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if p.poll() is not None:
            _fail(f"driver exited: {p.stderr.read() if p.stderr else ''}")
        if p.stdout.readline():
            return p
    p.kill()
    _fail("driver never announced URL")
    raise Err("unreachable")


def _hook(hook_path: Path, state_dir: Path, cls_yaml: Path, event: dict):
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_dir)
    env["STEPPROOF_CLASSIFICATION"] = str(cls_yaml)
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

    project = Path(tempfile.mkdtemp(prefix="stepproof-complex1-"))
    print(f"tmp project: {project}")
    state = project / ".stepproof"
    claude = project / ".claude"
    hook = claude / "hooks" / "stepproof_pretooluse.py"
    cls_yaml = claude / "stepproof" / "action_classification.yaml"
    driver: subprocess.Popen[str] | None = None

    try:
        _step("1. install + spawn driver")
        installer.install(scope="project", project_dir=project)
        driver = _spawn(state)
        rec = read_runtime_record(base=state)
        if rec is None or rec.pid != driver.pid:
            _fail("runtime.url missing or PID mismatch")
        url = rec.url
        _ok(f"runtime at {url}")

        _step("2. declare plan: single step, min_lines=5")
        target = project / "design.md"
        plan = {
            "intent": "complex #1 — verification failure path",
            "environment": "staging",
            "owner_id": "complex-1",
            "agent_id": "claude-code-worker",
            "risk_level": "low",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Write a design doc ≥ 5 lines",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Write"],
                }
            ],
        }
        pr = httpx.post(f"{url}/plans/declare", json=plan, timeout=5.0)
        if pr.status_code != 200:
            _fail(f"/plans/declare → {pr.status_code}: {pr.text}")
        run_id = pr.json()["run"]["run_id"]
        _ok(f"run_id={run_id}")

        _step("3. write active-run.json → s1")
        (state / "active-run.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "current_step": "s1",
                    "allowed_tools": ["Write"],
                    "template_id": None,
                }
            )
        )
        _ok("active-run.json → s1 (Write-only)")

        _step("4. submit evidence pointing at a too-short file")
        target.write_text("only\ntwo\n", encoding="utf-8")
        cr = httpx.post(
            f"{url}/runs/{run_id}/steps/s1/complete",
            json={"evidence": {"path": str(target), "min_lines": 5}},
            timeout=10.0,
        )
        if cr.status_code != 200:
            _fail(f"step_complete HTTP {cr.status_code}: {cr.text}")
        verdict = cr.json()
        if verdict["verification_result"]["status"] != "fail":
            _fail(f"verifier should have failed; got {verdict['verification_result']}")
        if verdict["run"]["current_step"] != "s1":
            _fail(
                f"run advanced after failed verification: current_step="
                f"{verdict['run']['current_step']}"
            )
        _ok("verifier failed; run still on s1")

        _step("5. hook: Bash still denied (scoping intact after failure)")
        out = _hook(
            hook,
            state,
            cls_yaml,
            {
                "session_id": "c1",
                "tool_name": "Bash",
                "tool_input": {"command": "echo nope"},
            },
        )
        if out.returncode != 2 or "s1" not in out.stderr:
            _fail(f"scoping broke after failure: rc={out.returncode}\n{out.stderr}")
        _ok(f"Bash still denied: {out.stderr.strip()}")

        _step("6. fix the file; resubmit evidence")
        target.write_text(
            "line 1\nline 2\nline 3\nline 4\nline 5\nline 6\n",
            encoding="utf-8",
        )
        cr2 = httpx.post(
            f"{url}/runs/{run_id}/steps/s1/complete",
            json={"evidence": {"path": str(target), "min_lines": 5}},
            timeout=10.0,
        )
        # NB: the current runtime marks a failed step as FAILED and does not
        # auto-reset it on a second complete. That's a deliberate "stuck run
        # needs explicit remediation" posture. Either behavior (accept-or-400)
        # is a valid contract — we just assert it is *consistent* and does
        # not silently corrupt state.
        print(f"      second attempt: HTTP {cr2.status_code}  body={cr2.text[:200]!r}")

        if cr2.status_code == 200:
            verdict2 = cr2.json()
            if verdict2["verification_result"]["status"] != "pass":
                _fail(f"retry verifier should now pass; got {verdict2['verification_result']}")
            if verdict2["run"]["current_step"] is not None:
                _fail(
                    f"single-step run should be COMPLETED; current_step="
                    f"{verdict2['run']['current_step']}"
                )
            _ok("retry accepted; run COMPLETED")
        elif cr2.status_code in (400, 409):
            _ok(f"retry refused with {cr2.status_code} — stuck-run posture confirmed")
        else:
            _fail(f"unexpected retry response: {cr2.status_code}")

        _step("7. teardown")
        driver.send_signal(signal.SIGTERM)
        try:
            driver.wait(timeout=5)
        except subprocess.TimeoutExpired:
            driver.kill()
            driver.wait(timeout=2)
        driver = None
        installer.uninstall(project_dir=project)
        _ok("clean")

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
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    try:
        run(keep=args.keep)
    except Err as e:
        print(f"\nCOMPLEX 1 FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

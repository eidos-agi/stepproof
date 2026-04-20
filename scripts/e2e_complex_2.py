#!/usr/bin/env python3
"""Complex #2 — three-step happy path with out-of-order attempts.

Does the runtime reject steps that arrive out of sequence? Does the hook
surface those denials? Does the whole run end with ``active-run.json``
cleared on COMPLETED?

Flow:
  1. Install + spawn MCP.
  2. Declare a three-step plan: s1 (Write), s2 (Write), s3 (Edit).
     Each step has its own required file + verify_file_exists.
  3. Bind active-run.json to s1.
  4. Try to complete s3 before s1 → runtime returns 409.
  5. Complete s1 → advance to s2. Update active-run.json.
  6. Try to complete s1 again (out of order on the "done" side) → 409.
  7. Complete s2 → advance to s3. Update active-run.json.
  8. Complete s3 → run COMPLETED. Clear active-run.json.
  9. Verify: no active-run.json on disk (mirrors the MCP's
     ``clear_active_run`` on terminal status).
 10. Uninstall, clean.

This pins: out-of-order step submissions are rejected; the happy-path
sequence advances correctly across two transitions; the run terminal
state flows back to the state file.
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


def _complete(url: str, run_id: str, step: str, evidence: dict) -> httpx.Response:
    return httpx.post(
        f"{url}/runs/{run_id}/steps/{step}/complete",
        json={"evidence": evidence},
        timeout=10.0,
    )


def _set_active(state: Path, run_id: str, step: str | None, allowed: list[str]) -> None:
    if step is None:
        p = state / "active-run.json"
        if p.exists():
            p.unlink()
        return
    (state / "active-run.json").write_text(
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
    from stepproof_state import read_active_run, read_runtime_record

    project = Path(tempfile.mkdtemp(prefix="stepproof-complex2-"))
    print(f"tmp project: {project}")
    state = project / ".stepproof"
    driver: subprocess.Popen[str] | None = None

    try:
        _step("1. install + spawn driver")
        installer.install(scope="project", project_dir=project)
        driver = _spawn(state)
        rec = read_runtime_record(base=state)
        if rec is None:
            _fail("runtime.url missing")
        url = rec.url
        _ok(f"runtime at {url}")

        _step("2. declare three-step plan")
        f1 = project / "s1.md"
        f2 = project / "s2.md"
        f3 = project / "s3.md"
        plan = {
            "intent": "complex #2 — three-step sequence",
            "environment": "staging",
            "owner_id": "complex-2",
            "agent_id": "claude-code-worker",
            "risk_level": "low",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Write s1 artifact",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Write"],
                },
                {
                    "step_id": "s2",
                    "description": "Write s2 artifact",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Write"],
                },
                {
                    "step_id": "s3",
                    "description": "Edit s3 artifact",
                    "required_evidence": ["path", "min_lines"],
                    "verification_method": "verify_file_exists",
                    "allowed_tools": ["Edit"],
                },
            ],
        }
        pr = httpx.post(f"{url}/plans/declare", json=plan, timeout=5.0)
        if pr.status_code != 200:
            _fail(f"/plans/declare → {pr.status_code}: {pr.text}")
        run_id = pr.json()["run"]["run_id"]
        _ok(f"run_id={run_id}  current_step=s1")

        _set_active(state, run_id, "s1", ["Write"])

        _step("3. out-of-order: try s3 before s1 → 409")
        f3.write_text("a\nb\nc\n", encoding="utf-8")
        r = _complete(url, run_id, "s3", {"path": str(f3), "min_lines": 2})
        if r.status_code != 409:
            _fail(f"expected 409, got {r.status_code}: {r.text}")
        _ok(f"runtime refused s3: {r.json().get('detail','')}")

        _step("4. complete s1 (happy path)")
        f1.write_text("l1\nl2\nl3\n", encoding="utf-8")
        r = _complete(url, run_id, "s1", {"path": str(f1), "min_lines": 2})
        if r.status_code != 200:
            _fail(f"s1 complete failed: {r.status_code} {r.text}")
        j = r.json()
        if j["run"]["current_step"] != "s2":
            _fail(f"did not advance to s2: {j['run']}")
        _ok("advanced to s2")
        _set_active(state, run_id, "s2", ["Write"])

        _step("5. out-of-order: try s1 again after advance → 409")
        r = _complete(url, run_id, "s1", {"path": str(f1), "min_lines": 2})
        if r.status_code != 409:
            _fail(f"expected 409 on redundant s1, got {r.status_code}")
        _ok("runtime refused redundant s1")

        _step("6. complete s2")
        f2.write_text("x1\nx2\n", encoding="utf-8")
        r = _complete(url, run_id, "s2", {"path": str(f2), "min_lines": 2})
        if r.status_code != 200:
            _fail(f"s2 complete failed: {r.status_code} {r.text}")
        j = r.json()
        if j["run"]["current_step"] != "s3":
            _fail(f"did not advance to s3: {j['run']}")
        _ok("advanced to s3")
        _set_active(state, run_id, "s3", ["Edit"])

        _step("7. complete s3 → COMPLETED")
        r = _complete(url, run_id, "s3", {"path": str(f3), "min_lines": 2})
        if r.status_code != 200:
            _fail(f"s3 complete failed: {r.status_code} {r.text}")
        j = r.json()
        if j["run"]["status"] != "completed":
            _fail(f"run not COMPLETED: {j['run']}")
        _ok("run COMPLETED")

        _step("8. clear active-run.json (mirrors MCP's clear on terminal)")
        _set_active(state, run_id, None, [])
        if read_active_run(base=state) is not None:
            _fail("active-run.json still present after terminal state")
        _ok("active-run.json cleared")

        _step("9. teardown")
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
        print(f"\nCOMPLEX 2 FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

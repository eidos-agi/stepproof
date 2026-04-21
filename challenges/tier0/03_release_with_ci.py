#!/usr/bin/env python3
"""Tier 0 — this repo's release ceremony, with GitHub Actions
verification.

Extends test 02: after the local release ceremony completes, push a
temporary test branch to origin, wait for the `tests` workflow
(defined in .github/workflows/tests.yml) to run, verify its outcome
via the GitHub API, then clean up the branch.

This is the complete Tier-0 release loop against a real remote:

  1. Clone this repo into tmp.
  2. Run the rb-stepproof-release ceremony (same as test 02).
  3. Create a temp branch (stepproof-ci-test/<timestamp>).
  4. Push it to origin.
  5. Poll GitHub Actions API until the workflow run for that push
     reaches a terminal state (completed).
  6. Assert conclusion == "success" (the real verify_ci_green
     semantics, applied against a real workflow run).
  7. Delete the remote branch.

Requirements:
  - `gh` CLI installed and authenticated against github.com/eidos-agi/stepproof
  - Network access
  - The .github/workflows/tests.yml workflow committed to main

Cleanup is best-effort — on any failure path, the script attempts
to delete the remote branch to avoid pollution.
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
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STEPPROOF_BIN = REPO_ROOT / ".venv" / "bin" / "stepproof"
ORIGIN_URL = "https://github.com/eidos-agi/stepproof.git"
REPO_SLUG = "eidos-agi/stepproof"


class Err(RuntimeError):
    pass


def _ok(m: str) -> None:
    print(f"   ok  {m}")


def _fail(m: str) -> None:
    print(f"   FAIL  {m}")
    raise Err(m)


def _step(m: str) -> None:
    print(f"\n── {m}")


def _require_cli(name: str) -> None:
    if shutil.which(name) is None:
        _fail(f"{name} CLI required but not on PATH")


def copy_repo(dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--quiet", str(REPO_ROOT), str(dest)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.name", "Tier0 Release CI"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.email", "release-ci@example.com"],
        check=True,
    )
    # Point origin at the REAL remote for push, not at the local REPO_ROOT
    # that git clone auto-configured.
    subprocess.run(
        ["git", "-C", str(dest), "remote", "set-url", "origin", ORIGIN_URL],
        check=True,
    )


def install_workspace(copy_root: Path) -> None:
    subprocess.run(
        ["uv", "sync", "--all-packages"],
        cwd=copy_root, check=True, capture_output=True,
    )


def build_mcp_config(copy_root: Path) -> Path:
    cfg = {
        "mcpServers": {
            "stepproof": {
                "type": "stdio",
                "command": str(STEPPROOF_BIN),
                "args": ["mcp"],
                "env": {
                    "STEPPROOF_STATE_DIR": str(copy_root / ".stepproof"),
                    "STEPPROOF_RUNBOOKS_DIR": str(copy_root / "examples"),
                },
            }
        }
    }
    p = copy_root / ".mcp.json"
    p.write_text(json.dumps(cfg, indent=2))
    return p


PROMPT = textwrap.dedent("""
Walk the StepProof release ceremony end-to-end locally. Same flow
as test 02. After completion I'll push and verify CI.

1. Start: mcp__stepproof__stepproof_run_start(
     template_id="rb-stepproof-release",
     owner_id="tier0-release-ci",
     environment="staging")

2. Execute s1..s5 with these evidence shapes:
   - s1 bump versions in pyproject files. Evidence: path, min_lines.
   - s2 build: uv build --all-packages 2>&1 | tee /tmp/release-build.out.
     Evidence: pytest_output_path=<path>, min_lines=1  — wait, use
     the verify_file_exists evidence shape: path=/tmp/release-build.out,
     min_lines=1.
   - s3 pytest: uv run pytest tests/ 2>&1 | tee /tmp/release-pytest.out.
     Evidence: pytest_output_path, min_passed=100.
   - s4 commit + tag: git add; git commit -m "chore(release): bump";
     git tag -a vX.Y.Z -m "release". Evidence: commit_sha from
     `git rev-parse HEAD`.
   - s5 same commit_sha; verify_git_commit passes because it exists.

3. Report one line and stop. Do NOT push — the harness pushes after.
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
    s = {"tool_inputs": [], "assistant_text": []}
    for e in events:
        if e.get("type") == "assistant":
            for b in e.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    s["tool_inputs"].append((b.get("name", ""), b.get("input", {})))
                elif b.get("type") == "text":
                    s["assistant_text"].append(b.get("text", ""))
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


def push_test_branch(copy_root: Path, branch: str) -> str:
    """Create and push a temp branch; return the head SHA."""
    subprocess.run(
        ["git", "-C", str(copy_root), "checkout", "-b", branch],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(copy_root), "push", "-u", "origin", branch],
        check=True, capture_output=True,
    )
    sha = subprocess.run(
        ["git", "-C", str(copy_root), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    return sha


def delete_test_branch(branch: str) -> None:
    try:
        subprocess.run(
            ["git", "push", "origin", "--delete", branch],
            cwd=str(REPO_ROOT),
            check=False, capture_output=True,
        )
    except Exception:
        pass


def wait_for_workflow_run(head_sha: str, timeout_s: int) -> dict:
    """Poll GitHub Actions API via gh CLI until a workflow run for
    head_sha reaches a completed status. Returns the run record.
    """
    deadline = time.monotonic() + timeout_s
    run_id = None
    while time.monotonic() < deadline:
        listing = subprocess.run(
            ["gh", "run", "list", "--repo", REPO_SLUG,
             "--commit", head_sha, "--json",
             "databaseId,status,conclusion,workflowName,headSha",
             "--limit", "5"],
            capture_output=True, text=True,
        )
        if listing.returncode != 0:
            time.sleep(5)
            continue
        try:
            runs = json.loads(listing.stdout or "[]")
        except json.JSONDecodeError:
            runs = []
        for r in runs:
            if r.get("headSha") == head_sha and r.get("workflowName") == "tests":
                if r.get("status") == "completed":
                    return r
                run_id = r.get("databaseId")
        time.sleep(10)
    raise Err(f"workflow for {head_sha[:8]} did not complete within {timeout_s}s (last seen run_id={run_id})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--ceremony-timeout", type=int, default=900,
                    help="timeout for the local release ceremony")
    ap.add_argument("--ci-timeout", type=int, default=900,
                    help="timeout waiting for GitHub Actions to complete")
    args = ap.parse_args()

    _require_cli("git")
    _require_cli("gh")

    copy_root = Path(tempfile.mkdtemp(prefix="sp-tier0-ci-"))
    branch = f"stepproof-ci-test/{uuid.uuid4().hex[:12]}"
    print(f"copy root: {copy_root}")
    print(f"test branch: {branch}")

    try:
        _step("1. clone source repo into tmp + point origin at github")
        copy_repo(copy_root)
        _ok("cloned + origin set")

        _step("2. install workspace in clone")
        install_workspace(copy_root)
        _ok("uv sync complete")

        _step("3. register MCP (Tier 0)")
        cfg = build_mcp_config(copy_root)
        _ok(str(cfg.relative_to(copy_root)))

        _step(f"4. run release ceremony locally (timeout {args.ceremony_timeout}s)")
        rc, events = run_claude(copy_root, cfg, args.ceremony_timeout)
        summary = summarize(events)

        ar = copy_root / ".stepproof" / "active-run.json"
        sp_status = "cleared" if not ar.exists() else (
            f"active(step={json.loads(ar.read_text()).get('current_step')})"
        )

        step_completes = [
            (inp or {}).get("step_id")
            for (name, inp) in summary["tool_inputs"]
            if name == "mcp__stepproof__stepproof_step_complete"
        ]
        if sp_status != "cleared":
            _fail(f"ceremony did not complete: {sp_status}")
        _ok(f"ceremony completed; steps={step_completes}")

        _step(f"5. push test branch {branch} to origin")
        head_sha = push_test_branch(copy_root, branch)
        _ok(f"pushed head={head_sha[:8]}")

        _step(f"6. wait for GitHub Actions 'tests' workflow (timeout {args.ci_timeout}s)")
        run = wait_for_workflow_run(head_sha, args.ci_timeout)
        _ok(f"run_id={run['databaseId']} status={run['status']} conclusion={run['conclusion']}")

        _step("7. assert GitHub Actions succeeded")
        if run["conclusion"] != "success":
            _fail(f"CI conclusion={run['conclusion']}")
        _ok("CI conclusion == success")

        print("\nTIER 0 RELEASE + CI VERIFICATION PASSED.")
        return 0

    except Err as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        return 1
    finally:
        _step("cleanup: delete remote test branch")
        delete_test_branch(branch)
        if not args.keep:
            shutil.rmtree(copy_root, ignore_errors=True)
        else:
            print(f"(left at {copy_root})", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())

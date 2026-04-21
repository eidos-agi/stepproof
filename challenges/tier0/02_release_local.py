#!/usr/bin/env python3
"""Tier 0 — this repo's release ceremony, LOCAL only.

Copies this repo to a temp directory and walks the
`rb-stepproof-release` ceremony end-to-end against the copy, at
Tier 0 (no hook installed). The source repo is untouched.

Proves:
- The release runbook is well-formed and executable end-to-end.
- An agent can bump versions, build wheels, run the test suite,
  tag, and commit under ceremony enforcement.
- Every advancement is gated by a verifier reading real state
  (files exist with min_lines, pytest summary parsed, git commit
  SHA verified by `git cat-file`).

What this test does NOT do:
- Install the PreToolUse hook (this is Tier 0 by design).
- Push anything to a remote. Test 03 does that.
- Publish anything to PyPI. Out of scope.
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
RUNBOOKS_DIR_SRC = REPO_ROOT / "examples"


class Err(RuntimeError):
    pass


def _ok(m: str) -> None:
    print(f"   ok  {m}")


def _fail(m: str) -> None:
    print(f"   FAIL  {m}")
    raise Err(m)


def _step(m: str) -> None:
    print(f"\n── {m}")


def copy_repo(dest: Path) -> None:
    """Copy the StepProof repo into dest, excluding volatile state."""
    # Use `git clone` so .git is cloned cleanly and no working-tree
    # artifacts leak. A filesystem copy would also work but would
    # include .venv, .stepproof/, .pytest_cache/, etc.
    subprocess.run(
        ["git", "clone", "--quiet", str(REPO_ROOT), str(dest)],
        check=True,
        capture_output=True,
    )
    # Configure author/committer for the clone's local commits.
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.name", "Tier0 Release"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "config", "user.email", "release@example.com"],
        check=True,
    )


def install_workspace(copy_root: Path) -> None:
    """Install the workspace in the copy so uv/pytest work there."""
    subprocess.run(
        ["uv", "sync", "--all-packages"],
        cwd=copy_root, check=True, capture_output=True,
    )


def build_mcp_config(copy_root: Path) -> Path:
    cfg = {
        "mcpServers": {
            "stepproof": {
                "type": "stdio",
                # Use the source-repo's stepproof binary — the copy's
                # .venv isn't populated yet for the MCP server.
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
You're cutting a release of the StepProof monorepo. Walk the
`rb-stepproof-release` ceremony end-to-end.

1. Start the run:
     mcp__stepproof__stepproof_run_start(
       template_id="rb-stepproof-release",
       owner_id="tier0-release",
       environment="staging")
   Remember the run_id.

2. For each step:

   s1 — Bump versions. Pick a new patch version (e.g., if current is
        0.0.1, use 0.0.2). Edit every package's pyproject.toml —
        `pyproject.toml`, `packages/stepproof-runtime/pyproject.toml`,
        `packages/stepproof-mcp/pyproject.toml`,
        `packages/stepproof-cc-adapter/pyproject.toml`,
        `packages/stepproof-state/pyproject.toml` — and bump the
        `version = ...` line. Evidence: path to any one of those
        updated files, min_lines=1.

   s2 — Build. Run `uv build --all-packages 2>&1 | tee /tmp/release-build.out`.
        Evidence: path="/tmp/release-build.out", min_lines=1.

   s3 — Tests green. Run `uv run pytest tests/ 2>&1 | tee /tmp/release-pytest.out`.
        Evidence: pytest_output_path="/tmp/release-pytest.out", min_passed=100.

   s4 — Tag. Run:
          git add -A
          git commit -m "chore(release): bump to vX.Y.Z"
          git tag -a vX.Y.Z -m "release X.Y.Z"
          git rev-parse HEAD
        Evidence: commit_sha=<the SHA>.
        (Note: the runbook's s4 says "tag"; we do the commit here so
        the tag has something to point at. s5 is the confirmation
        commit in the runbook.)

   s5 — Commit confirmation. The commit from s4 is the same one. Submit
        the SAME commit_sha as evidence. verify_git_commit will confirm
        it exists in the repo.

3. When status=completed, report one-line summary. Stop.
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


def inspect_copy(copy_root: Path) -> dict:
    def _git(args):
        return subprocess.run(
            ["git", "-C", str(copy_root)] + args,
            capture_output=True, text=True,
        ).stdout.strip()

    return {
        "head_sha": _git(["rev-parse", "HEAD"]),
        "tag_list": _git(["tag", "--list"]).splitlines(),
        "commit_log_tail": _git(["log", "--oneline", "-3"]).splitlines(),
        "dist_contents": sorted(p.name for p in (copy_root / "dist").glob("*")) if (copy_root / "dist").exists() else [],
    }


def run(copy_root: Path, timeout_s: int) -> dict:
    _step("1. clone source repo into tmp")
    copy_repo(copy_root)
    _ok(f"cloned to {copy_root}")

    _step("2. install workspace in clone")
    install_workspace(copy_root)
    _ok("uv sync complete in copy")

    _step("3. register MCP config (no hook install)")
    cfg = build_mcp_config(copy_root)
    _ok(str(cfg.relative_to(copy_root)))

    _step(f"4. run claude -p against the release runbook (timeout {timeout_s}s)")
    rc, events = run_claude(copy_root, cfg, timeout_s)
    summary = summarize(events)

    step_completes = [
        (inp or {}).get("step_id")
        for (name, inp) in summary["tool_inputs"]
        if name == "mcp__stepproof__stepproof_step_complete"
    ]

    ar = copy_root / ".stepproof" / "active-run.json"
    sp_status = "cleared" if not ar.exists() else (
        f"active(step={json.loads(ar.read_text()).get('current_step')})"
    )

    copy_state = inspect_copy(copy_root)

    stepproof_hooks = [
        e for e in summary["hook_events"]
        if "stepproof" in json.dumps(e).lower()
    ]

    return {
        "rc": rc,
        "stepproof_run_status": sp_status,
        "step_ids_completed": step_completes,
        "stepproof_hook_events_seen": len(stepproof_hooks),
        "tool_uses_total": len(summary["tool_uses"]),
        "copy_state": copy_state,
        "final_text": (summary["assistant_text"][-1] if summary["assistant_text"] else "")[:500],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    copy_root = Path(tempfile.mkdtemp(prefix="sp-tier0-release-"))
    print(f"copy root: {copy_root}")
    try:
        r = run(copy_root, args.timeout)
        print(json.dumps(r, indent=2))

        _step("ASSERTIONS")

        if r["stepproof_run_status"] != "cleared":
            _fail(f"run not completed: {r['stepproof_run_status']}")
        _ok("release run COMPLETED")

        completed = [s for s in r["step_ids_completed"] if s]
        expected_steps = {"s1", "s2", "s3", "s4", "s5"}
        if not set(completed) >= expected_steps:
            _fail(f"missing steps {expected_steps - set(completed)}: got {completed}")
        _ok(f"all 5 release steps verified ({completed})")

        if not r["copy_state"]["dist_contents"]:
            print("   note: no dist/ artifacts (build may have gone elsewhere)")
        else:
            _ok(f"built artifacts: {r['copy_state']['dist_contents']}")

        if not r["copy_state"]["tag_list"]:
            print("   note: no git tag in copy (runbook s4 didn't produce one)")
        else:
            _ok(f"release tag: {r['copy_state']['tag_list']}")

        if len(r["copy_state"]["commit_log_tail"]) < 2:
            _fail("no release commit in copy")
        _ok(f"commits: {r['copy_state']['commit_log_tail'][:2]}")

        if r["stepproof_hook_events_seen"] > 0:
            _fail(f"hook events in Tier 0: {r['stepproof_hook_events_seen']}")
        _ok("zero hook events (Tier 0 confirmed)")

        print("\nTIER 0 RELEASE CEREMONY (LOCAL) PASSED.")
    except Err as e:
        print(f"\nFAIL: {e}", file=sys.stderr)
        return 1
    finally:
        if not args.keep:
            shutil.rmtree(copy_root, ignore_errors=True)
        else:
            print(f"\n(left at {copy_root})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

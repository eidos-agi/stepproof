"""End-to-end tests for the uv PreToolUse hook script.

Runs the hook as a subprocess with fake stdin JSON, verifies exit codes
and stderr messages match the classification rules.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

HOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "stepproof-cc-adapter"
    / "src"
    / "stepproof_cc_adapter"
    / "assets"
    / "hooks"
    / "stepproof_pretooluse.py"
)


def _run_hook(event: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    """Invoke the uv hook with a JSON event on stdin."""
    import os

    env_vars = dict(os.environ)
    # Point the daemon at an unreachable port so Ring 1+ actions hit the
    # graceful-degradation path (fail-open + audit buffer) rather than
    # making network calls during unit tests.
    env_vars["STEPPROOF_URL"] = "http://127.0.0.1:1"  # reserved, always refused
    env_vars["STEPPROOF_TIMEOUT_MS"] = "200"
    if env:
        env_vars.update(env)

    return subprocess.run(
        ["uv", "run", "--script", str(HOOK_PATH)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env_vars,
        timeout=30,
    )


def test_hook_exits_0_on_read_ring_0():
    r = _run_hook({"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "session_id": "t"})
    assert r.returncode == 0, r.stderr


def test_hook_exits_2_on_env_write():
    r = _run_hook({"tool_name": "Write", "tool_input": {"file_path": ".env"}, "session_id": "t"})
    assert r.returncode == 2
    assert ".env" in r.stderr


def test_hook_exits_0_on_git_status():
    r = _run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}, "session_id": "t"})
    assert r.returncode == 0


def test_hook_fails_closed_by_default_ring_2():
    """Per GPT-5.2 review + Rhea ruling: fail-closed is the default. Ring 2
    with daemon down → deny (exit 2). Operator must opt in to fail-open."""
    r = _run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "psql -c 'SELECT 1'"},
        "session_id": "t"
    })
    assert r.returncode == 2, (
        f"Expected fail-closed (exit 2) with default policy; got {r.returncode}. "
        f"stderr={r.stderr}"
    )
    assert "runtime unreachable" in r.stderr


def test_hook_opt_in_fail_open():
    """STEPPROOF_FAIL_OPEN=1 → Ring 2 with daemon down → allow (exit 0)."""
    r = _run_hook(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "psql -c 'SELECT 1'"},
            "session_id": "t",
        },
        env={"STEPPROOF_FAIL_OPEN": "1"},
    )
    assert r.returncode == 0, (
        f"Expected exit 0 with STEPPROOF_FAIL_OPEN=1; got {r.returncode}. stderr={r.stderr}"
    )


def test_hook_fails_closed_even_with_opt_in_for_configured_rings():
    """STEPPROOF_FAIL_CLOSED_RINGS=3 overrides STEPPROOF_FAIL_OPEN=1 for Ring 3."""
    r = _run_hook(
        {
            "tool_name": "Bash",
            "tool_input": {"command": "railway deploy --env prod"},
            "session_id": "t",
        },
        env={"STEPPROOF_FAIL_CLOSED_RINGS": "3", "STEPPROOF_FAIL_OPEN": "1"},
    )
    assert r.returncode == 2
    assert "Ring 3" in r.stderr


def test_hook_survives_malformed_stdin():
    """Per LESSONS_FROM_HOOKS_MASTERY: hook must never break the session on bad input."""
    r = subprocess.run(
        ["uv", "run", "--script", str(HOOK_PATH)],
        input="not json at all",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert r.returncode == 0


def test_hook_survives_missing_tool_name_and_denies_fail_closed():
    """Missing tool_name → empty string → unknown tool → Ring 3 → daemon
    unreachable → fail-closed default → deny. The hook does not crash."""
    r = _run_hook({"session_id": "t"})
    assert r.returncode == 2
    assert "unreachable" in r.stderr


def test_hook_classification_load_failure_blocks_fail_closed():
    """If classification YAML is missing, hook must not silently proceed."""
    r = _run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "whatever"}, "session_id": "t"},
        env={"STEPPROOF_CLASSIFICATION": "/nonexistent/path/classification.yaml"},
    )
    assert r.returncode == 2
    assert "classification unavailable" in r.stderr


def test_hook_classification_load_failure_opt_in_fail_open():
    """With STEPPROOF_FAIL_OPEN=1, missing classification falls through."""
    r = _run_hook(
        {"tool_name": "Bash", "tool_input": {"command": "whatever"}, "session_id": "t"},
        env={
            "STEPPROOF_CLASSIFICATION": "/nonexistent/path/classification.yaml",
            "STEPPROOF_FAIL_OPEN": "1",
        },
    )
    assert r.returncode == 0


def test_hook_classification_load_failure_allows_reads():
    """Even with missing classification, well-known read-only tools proceed."""
    r = _run_hook(
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/x"}, "session_id": "t"},
        env={"STEPPROOF_CLASSIFICATION": "/nonexistent/path/classification.yaml"},
    )
    assert r.returncode == 0

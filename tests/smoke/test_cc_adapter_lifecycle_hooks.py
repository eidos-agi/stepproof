"""Tests for the 5 lifecycle hooks.

Each hook is a uv single-file script invoked with fake stdin JSON. The tests
verify exit codes, optional stdout JSON (additionalContext injection), and
that every hook exits 0 on malformed input (never break the session).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

ASSETS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "stepproof-cc-adapter"
    / "src"
    / "stepproof_cc_adapter"
    / "assets"
    / "hooks"
)

SESSIONSTART = ASSETS / "stepproof_sessionstart.py"
SESSIONEND = ASSETS / "stepproof_sessionend.py"
PRECOMPACT = ASSETS / "stepproof_precompact.py"
USERPROMPTSUBMIT = ASSETS / "stepproof_userpromptsubmit.py"
PERMISSIONREQUEST = ASSETS / "stepproof_permissionrequest.py"


def _run(script: Path, event: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    env_vars = dict(os.environ)
    # Isolated state dir per test.
    if env:
        env_vars.update(env)
    return subprocess.run(
        ["uv", "run", "--script", str(script)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        env=env_vars,
        timeout=30,
    )


@pytest.fixture
def iso_state(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        yield d


def _write_session(iso_state: Path, session_id: str, payload: dict) -> Path:
    sessions = iso_state / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    p = sessions / f"{session_id}.json"
    p.write_text(json.dumps(payload))
    return p


# ---------------------------------------------------------------------------
# SessionStart
# ---------------------------------------------------------------------------


def test_sessionstart_no_active_session_exits_silent(iso_state: Path):
    r = _run(
        SESSIONSTART,
        {"session_id": "nope", "source": "startup"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_sessionstart_injects_runbook_state_when_active(iso_state: Path):
    _write_session(iso_state, "sid-1", {
        "run_id": "abc",
        "template_id": "rb-declared-xyz",
        "current_step": "s3",
        "allowed_tools": ["Edit", "git"],
    })
    r = _run(
        SESSIONSTART,
        {"session_id": "sid-1", "source": "startup"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout)
    assert body["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "abc" in ctx
    assert "s3" in ctx
    assert "rb-declared-xyz" in ctx


def test_sessionstart_ignores_expired_heartbeat(iso_state: Path):
    _write_session(iso_state, "sid-2", {
        "run_id": "abc",
        "heartbeat_expires_at": "1970-01-01T00:00:00Z",  # clearly expired
    })
    r = _run(
        SESSIONSTART,
        {"session_id": "sid-2", "source": "resume"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_sessionstart_survives_malformed_stdin():
    r = subprocess.run(
        ["uv", "run", "--script", str(SESSIONSTART)],
        input="not json",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# SessionEnd
# ---------------------------------------------------------------------------


def test_sessionend_no_active_session_is_noop(iso_state: Path):
    r = _run(
        SESSIONEND,
        {"session_id": "nope", "reason": "exit"},
        env={
            "STEPPROOF_STATE_DIR": str(iso_state),
            "STEPPROOF_URL": "http://127.0.0.1:1",  # unreachable; noop
        },
    )
    assert r.returncode == 0


def test_sessionend_cleans_up_session_file(iso_state: Path):
    session_file = _write_session(iso_state, "sid-end", {"run_id": "abc"})
    assert session_file.exists()
    r = _run(
        SESSIONEND,
        {"session_id": "sid-end", "reason": "exit"},
        env={
            "STEPPROOF_STATE_DIR": str(iso_state),
            "STEPPROOF_URL": "http://127.0.0.1:1",
            "STEPPROOF_TIMEOUT_MS": "200",
        },
    )
    assert r.returncode == 0
    assert not session_file.exists(), "SessionEnd should remove the session file"


def test_sessionend_survives_malformed_stdin():
    r = subprocess.run(
        ["uv", "run", "--script", str(SESSIONEND)],
        input="not json",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# PreCompact
# ---------------------------------------------------------------------------


def test_precompact_injects_state_on_active_run(iso_state: Path):
    _write_session(iso_state, "sid-c", {
        "run_id": "r1",
        "template_id": "rb-declared-abc",
        "current_step": "s4",
    })
    r = _run(
        PRECOMPACT,
        {"session_id": "sid-c", "trigger": "auto"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    body = json.loads(r.stdout)
    assert body["hookSpecificOutput"]["hookEventName"] == "PreCompact"
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "r1" in ctx
    assert "s4" in ctx
    assert "auto" in ctx


def test_precompact_silent_when_no_active_run(iso_state: Path):
    r = _run(
        PRECOMPACT,
        {"session_id": "no-sid", "trigger": "manual"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    assert r.stdout.strip() == ""


# ---------------------------------------------------------------------------
# UserPromptSubmit
# ---------------------------------------------------------------------------


def test_userpromptsubmit_nudges_on_psql_mention():
    r = _run(USERPROMPTSUBMIT, {"session_id": "x", "prompt": "let me just psql real quick"})
    assert r.returncode == 0, r.stderr
    body = json.loads(r.stdout)
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "database.write" in ctx
    assert "Ring 2" in ctx or "Ring 3" in ctx


def test_userpromptsubmit_nudges_on_rm_rf_mention():
    r = _run(USERPROMPTSUBMIT, {"session_id": "x", "prompt": "just rm -rf / the whole thing"})
    assert r.returncode == 0
    body = json.loads(r.stdout)
    ctx = body["hookSpecificOutput"]["additionalContext"]
    assert "DENY" in ctx


def test_userpromptsubmit_silent_on_benign_prompt():
    r = _run(USERPROMPTSUBMIT, {"session_id": "x", "prompt": "add a unit test for the parser"})
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_userpromptsubmit_survives_empty_prompt():
    r = _run(USERPROMPTSUBMIT, {"session_id": "x", "prompt": ""})
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# PermissionRequest
# ---------------------------------------------------------------------------


def test_permissionrequest_logs_to_audit_buffer(iso_state: Path):
    r = _run(
        PERMISSIONREQUEST,
        {
            "session_id": "sid",
            "tool_name": "Bash",
            "tool_input": {"command": "SECRET_VALUE=abc psql ..."},
            "tool_use_id": "tu-1",
        },
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    buf = iso_state / "audit-buffer.jsonl"
    assert buf.exists()
    line = buf.read_text().splitlines()[0]
    record = json.loads(line)
    assert record["kind"] == "permission_request"
    assert record["tool_name"] == "Bash"
    # `command` field must be redacted — this is the secrets-capture defense.
    assert record["tool_input_redacted"]["command"] == "<redacted>"


def test_permissionrequest_respects_buffer_size_cap(iso_state: Path):
    buf = iso_state / "audit-buffer.jsonl"
    buf.write_text("x" * 1_200_000)  # over the 1MB cap
    before = buf.stat().st_size
    r = _run(
        PERMISSIONREQUEST,
        {"session_id": "s", "tool_name": "Bash", "tool_input": {}, "tool_use_id": "x"},
        env={"STEPPROOF_STATE_DIR": str(iso_state)},
    )
    assert r.returncode == 0
    # Should not have grown.
    assert buf.stat().st_size == before


def test_permissionrequest_survives_malformed_stdin():
    r = subprocess.run(
        ["uv", "run", "--script", str(PERMISSIONREQUEST)],
        input="not json",
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert r.returncode == 0

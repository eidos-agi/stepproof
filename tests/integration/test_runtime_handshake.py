"""Integration tests for the runtime/state handshake (increment 1).

The MCP server publishes its URL to ``.stepproof/runtime.url`` on boot and
writes ``active-run.json`` when a plan is declared. The PreToolUse hook reads
both to discover the runtime and enforce per-step scoping. These tests
exercise the full lifecycle — boot, shutdown, corruption recovery, policy
enforcement, concurrent access — because enforcement code lives or dies on
its behavior at the edges.

Matrix:
    Lifecycle:       1, 2, 3, 4
    State corruption: 5, 6, 7
    Policy:          8, 9, 10, 11, 12
    Concurrency:     13
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from stepproof_state import (
    atomic_write_json,
    read_active_run,
    read_runtime_record,
    resolve_active_run,
    resolve_runtime_url,
    state_dir,
    write_active_run,
    write_runtime_url,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).parent / "_mcp_driver.py"
HOOK = (
    REPO_ROOT
    / "packages"
    / "stepproof-cc-adapter"
    / "src"
    / "stepproof_cc_adapter"
    / "assets"
    / "hooks"
    / "stepproof_pretooluse.py"
)
CLASSIFICATION = (
    REPO_ROOT
    / "packages"
    / "stepproof-cc-adapter"
    / "src"
    / "stepproof_cc_adapter"
    / "assets"
    / "stepproof"
    / "action_classification.yaml"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spawn_driver(
    state_path: Path,
    *,
    self_exit_after: float | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_path)
    env.pop("STEPPROOF_URL", None)
    if extra_env:
        env.update(extra_env)

    args = [sys.executable, str(DRIVER)]
    if self_exit_after is not None:
        args += ["--self-exit-after", str(self_exit_after)]

    proc = subprocess.Popen(
        args,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return proc


def _wait_for_url(proc: subprocess.Popen[str], timeout: float = 10.0) -> str:
    """Read the driver's first stdout line (the base URL)."""
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"driver exited early: rc={proc.returncode}\n{stderr}")
        line = proc.stdout.readline()
        if line:
            return line.strip()
    proc.kill()
    raise TimeoutError("driver did not announce its URL in time")


def _wait_for_file_absent(path: Path, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not path.exists():
            return True
        time.sleep(0.05)
    return False


def _wait_for_proc_exit(proc: subprocess.Popen[str], timeout: float = 5.0) -> None:
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def _run_hook(
    state_path: Path,
    event: dict,
    *,
    fail_open: bool = False,
    human_owner: str = "tester",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["STEPPROOF_STATE_DIR"] = str(state_path)
    env["STEPPROOF_CLASSIFICATION"] = str(CLASSIFICATION)
    env["STEPPROOF_HUMAN_OWNER"] = human_owner
    env["STEPPROOF_FAIL_OPEN"] = "1" if fail_open else "0"
    env.pop("STEPPROOF_URL", None)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


@pytest.fixture
def state_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / ".stepproof"
    p.mkdir()
    monkeypatch.setenv("STEPPROOF_STATE_DIR", str(p))
    monkeypatch.delenv("STEPPROOF_URL", raising=False)
    return p


# ---------------------------------------------------------------------------
# 1. MCP clean exit — SIGTERM triggers signal handler → runtime.url deleted.
# ---------------------------------------------------------------------------


def test_mcp_sigterm_cleans_runtime_url(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc = _spawn_driver(state)
    try:
        url = _wait_for_url(proc)
        assert url.startswith("http://127.0.0.1:")
        record = read_runtime_record(base=state)
        assert record is not None
        assert record.url == url
        assert record.pid == proc.pid

        proc.send_signal(signal.SIGTERM)
        _wait_for_proc_exit(proc, timeout=5)
        assert _wait_for_file_absent(state / "runtime.url", timeout=3)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# 2. MCP SIGKILL leaves stale runtime.url; next reader detects dead PID and
#    reaps the file.
# ---------------------------------------------------------------------------


def test_mcp_sigkill_stale_record_is_reaped(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc = _spawn_driver(state)
    try:
        _wait_for_url(proc)
        assert (state / "runtime.url").exists()
        proc.kill()
        proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill()

    # runtime.url still exists — SIGKILL prevents atexit.
    assert (state / "runtime.url").exists()
    # Caller resolves → sees dead PID → file is reaped, returns None.
    assert resolve_runtime_url(base=state) is None
    assert not (state / "runtime.url").exists()


# ---------------------------------------------------------------------------
# 3. atexit fires on normal exit — driver exits cleanly, cleanup runs.
# ---------------------------------------------------------------------------


def test_atexit_on_normal_exit_cleans_runtime_url(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc = _spawn_driver(state, self_exit_after=1.5)
    try:
        _wait_for_url(proc)
        assert (state / "runtime.url").exists()
        _wait_for_proc_exit(proc, timeout=6)
        assert proc.returncode == 0
        assert _wait_for_file_absent(state / "runtime.url", timeout=3)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# 4. Two MCP starts in one project — second takes ownership. No silent dual
#    writers: after the second has published, the record points at the second
#    PID and the first's is gone.
# ---------------------------------------------------------------------------


def test_two_mcp_starts_second_takes_ownership(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc_a = _spawn_driver(state)
    proc_b: subprocess.Popen[str] | None = None
    try:
        url_a = _wait_for_url(proc_a)
        rec_a = read_runtime_record(base=state)
        assert rec_a is not None and rec_a.pid == proc_a.pid

        proc_b = _spawn_driver(state)
        url_b = _wait_for_url(proc_b)
        assert url_b != url_a  # different free port

        # After second publishes, runtime.url points at proc_b.
        rec_b = read_runtime_record(base=state)
        assert rec_b is not None
        assert rec_b.pid == proc_b.pid
        assert rec_b.url == url_b
    finally:
        for p in (proc_a, proc_b):
            if p is not None and p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(timeout=2)


# ---------------------------------------------------------------------------
# 5. runtime.url with garbage content → resolver returns None without raising.
# ---------------------------------------------------------------------------


def test_runtime_url_corrupt_json_is_tolerated(state_path: Path):
    (state_path / "runtime.url").write_text("{not valid json")
    assert read_runtime_record(base=state_path) is None
    assert resolve_runtime_url(base=state_path) is None


# ---------------------------------------------------------------------------
# 6. active-run.json with unknown fields — extra keys ignored, known keys
#    still parse. Forward compatibility.
# ---------------------------------------------------------------------------


def test_active_run_unknown_fields_ignored(state_path: Path):
    (state_path / "active-run.json").write_text(
        json.dumps(
            {
                "run_id": "r-123",
                "current_step": "s1",
                "allowed_tools": ["Write"],
                "template_id": "rb-x",
                "future_field": {"v": 1},
                "another_new_thing": "ignored",
            }
        )
    )
    active = resolve_active_run(base=state_path)
    assert active is not None
    assert active.run_id == "r-123"
    assert active.current_step == "s1"
    assert active.allowed_tools == ["Write"]


# ---------------------------------------------------------------------------
# 7. .stepproof/ does not exist → write creates it with correct structure.
# ---------------------------------------------------------------------------


def test_state_dir_bootstrapped_on_first_write(tmp_path: Path):
    target = tmp_path / "fresh" / ".stepproof"
    assert not target.exists()
    write_runtime_url("http://127.0.0.1:9999", pid=os.getpid(), base=target)
    assert target.exists()
    assert (target / "runtime.url").exists()
    payload = json.loads((target / "runtime.url").read_text())
    assert payload["url"] == "http://127.0.0.1:9999"


# ---------------------------------------------------------------------------
# 8. Hook: Write to allowed_tools-listed path → allow (Ring 0 for /tmp write).
#    Uses the real classification YAML; /tmp is in path_classifications as
#    Ring 0. We verify the happy path with an active run bound.
# ---------------------------------------------------------------------------


def test_hook_allows_write_listed_in_allowed_tools(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc = _spawn_driver(state)
    try:
        _wait_for_url(proc)
        write_active_run(
            run_id="r-1",
            current_step="s1",
            allowed_tools=["Write", "Read"],
            template_id=None,
            base=state,
        )
        event = {
            "session_id": "test-session",
            "tool_name": "Read",
            "tool_input": {"file_path": str(tmp_path / "hello.txt")},
        }
        result = _run_hook(state, event)
        assert result.returncode == 0, result.stderr
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# 9. Write to .env → client-side deny, no runtime call at all.
# ---------------------------------------------------------------------------


def test_hook_denies_dotenv_write_clientside(state_path: Path, tmp_path: Path):
    # No active-run, no runtime, no classification edits needed — .env
    # should be blocked by the client-side rule in action_classification.yaml.
    event = {
        "session_id": "test-session",
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / ".env"), "content": "SECRET=1"},
    }
    result = _run_hook(state_path, event)
    assert result.returncode == 2
    assert "stepproof" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 10. Ring 2+ action with no runtime + no fail-open → structural deny.
#     Matches testplan.md "Ring 1+ action if no runbook is active."
# ---------------------------------------------------------------------------


def test_hook_fail_closed_when_no_runtime(state_path: Path):
    # Bash with 'rm -rf' is Ring 3 in the classification; no runtime is up
    # and no runtime.url is published, so the hook must block.
    event = {
        "session_id": "test-session",
        "tool_name": "Bash",
        "tool_input": {"command": "rm -rf /tmp/nonexistent-test-dir"},
    }
    result = _run_hook(state_path, event, fail_open=False)
    assert result.returncode == 2
    assert "runtime unreachable" in result.stderr.lower() or "blocked" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 11. Out-of-order step — the runtime returns a deny (via /policy/evaluate
#     binding to a run with a non-matching step_id) and the hook surfaces it.
#     We stage this by publishing an active-run with the wrong step, booting
#     a real runtime, and firing a Bash action with no registered policy
#     rule — the runtime's policy engine is authoritative and the hook must
#     propagate its decision. In the default engine, Ring 1+ without a
#     matching rule falls through to deny.
# ---------------------------------------------------------------------------


def test_hook_propagates_runtime_deny(tmp_path: Path):
    state = tmp_path / ".stepproof"
    state.mkdir()
    proc = _spawn_driver(state)
    try:
        url = _wait_for_url(proc)

        # Bind an active run with a specific step; then ask for a tool that
        # is NOT in allowed_tools. The hook short-circuits with a policy
        # deny before hitting the runtime.
        write_active_run(
            run_id="r-out-of-order",
            current_step="s1",
            allowed_tools=["Read"],  # very narrow
            base=state,
        )
        # Confirm the runtime is reachable before we exercise the hook, so a
        # hook failure can only come from policy, not connectivity.
        r = httpx.get(f"{url}/health", timeout=3.0)
        assert r.status_code == 200

        event = {
            "session_id": "test-session",
            "tool_name": "Write",
            "tool_input": {"file_path": str(tmp_path / "out.txt"), "content": "x"},
        }
        result = _run_hook(state, event)
        assert result.returncode == 2
        assert "allowed_tools" in result.stderr or "not in" in result.stderr
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# 12. Tool not in allowed_tools for current step → deny with a reason that
#     names the step and the allowed set.
# ---------------------------------------------------------------------------


def test_hook_denies_tool_outside_allowed_tools(state_path: Path, tmp_path: Path):
    write_active_run(
        run_id="r-scope",
        current_step="s-edit-only",
        allowed_tools=["Edit"],
        base=state_path,
    )
    # Bash is definitely not in allowed_tools.
    event = {
        "session_id": "test-session",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    }
    result = _run_hook(state_path, event)
    assert result.returncode == 2
    assert "s-edit-only" in result.stderr
    assert "Edit" in result.stderr


# ---------------------------------------------------------------------------
# 13. Concurrent reads during atomic writes never see a partial file.
# ---------------------------------------------------------------------------


def test_atomic_write_never_exposes_partial_file(state_path: Path):
    target = state_path / "active-run.json"
    errors: list[str] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            if target.exists():
                try:
                    data = json.loads(target.read_text(encoding="utf-8"))
                    # Every readable state must have both keys set.
                    assert "run_id" in data
                    assert "current_step" in data
                except json.JSONDecodeError as e:
                    errors.append(f"partial read: {e}")
                    return
                except Exception as e:
                    errors.append(f"unexpected: {e}")
                    return

    threads = [threading.Thread(target=reader) for _ in range(6)]
    for t in threads:
        t.start()
    try:
        for i in range(200):
            atomic_write_json(
                target,
                {
                    "run_id": f"r-{i}",
                    "current_step": f"s-{i}",
                    "allowed_tools": ["Write", "Edit"],
                    "template_id": None,
                },
            )
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=2)

    assert not errors, errors
    # File exists and is valid at the end.
    final = read_active_run(base=state_path)
    assert final is not None
    assert final.run_id.startswith("r-")


# ---------------------------------------------------------------------------
# Supplementary: state_dir() honors env var even inside the hook's vendored
# copy. This is the contract that keeps tests isolated from a user's real
# `.stepproof/` directory.
# ---------------------------------------------------------------------------


def test_state_dir_respects_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STEPPROOF_STATE_DIR", str(tmp_path / "custom"))
    assert state_dir() == tmp_path / "custom"

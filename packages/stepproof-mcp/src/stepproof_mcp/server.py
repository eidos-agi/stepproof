"""StepProof MCP server.

Exposes StepProof governance tools over Model Context Protocol. Two modes:

- Embedded (default): if STEPPROOF_URL is unset, spawn an in-process runtime
  with SQLite. Zero-install, single-user, good for local dev.
- Hosted: STEPPROOF_URL=https://... makes this a thin HTTP client.

Whichever mode, the server publishes its base URL to ``.stepproof/runtime.url``
so the PreToolUse hook (and any other adapter) can find it without guessing at
ports. See ``docs/RUNTIME_HANDSHAKE.md``.
"""

from __future__ import annotations

import asyncio
import atexit
import os
import signal
import socket
from contextlib import closing
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from stepproof_state import (
    clear_active_run,
    clear_runtime_url,
    write_active_run,
    write_runtime_url,
)


def _pick_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_embedded_task: asyncio.Task | None = None
_embedded_url: str | None = None
_cleanup_installed = False


def _install_cleanup() -> None:
    """Register atexit + SIGTERM/SIGINT handlers once per process.

    The owning process of the embedded runtime must delete ``runtime.url`` on
    exit so later readers do not chase a dead PID. Signal handlers translate
    termination into ``SystemExit``, which lets ``atexit`` run.
    """
    global _cleanup_installed
    if _cleanup_installed:
        return
    _cleanup_installed = True

    def _on_exit() -> None:
        try:
            clear_runtime_url()
        except Exception:
            pass

    atexit.register(_on_exit)

    def _on_signal(signum: int, _frame: Any) -> None:
        try:
            clear_runtime_url()
        finally:
            raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            # Not in main thread (e.g. under some test harnesses) — skip.
            pass


async def _start_embedded_runtime() -> str:
    """Start the runtime in-process on a free port; return its base URL.

    Publishes ``.stepproof/runtime.url`` once uvicorn has bound its port, and
    installs cleanup so the file is removed on process exit.
    """
    global _embedded_task, _embedded_url
    if _embedded_url is not None:
        return _embedded_url

    import uvicorn

    from stepproof_runtime.api import app

    port = _pick_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    _embedded_task = asyncio.create_task(server.serve())
    # Wait for server readiness.
    for _ in range(100):
        await asyncio.sleep(0.05)
        if server.started:
            break
    _embedded_url = f"http://127.0.0.1:{port}"

    _install_cleanup()
    try:
        write_runtime_url(_embedded_url)
    except Exception:
        # Never crash boot on state-dir failure; the hook will fall back.
        pass

    return _embedded_url


async def _base_url() -> str:
    explicit = os.getenv("STEPPROOF_URL")
    if explicit:
        # Even in hosted mode, publish the URL so hooks have a single
        # discovery mechanism. PID is this process — not the runtime's, but
        # "the owner of this binding."
        try:
            write_runtime_url(explicit.rstrip("/"))
            _install_cleanup()
        except Exception:
            pass
        return explicit.rstrip("/")
    return await _start_embedded_runtime()


async def _client() -> httpx.AsyncClient:
    base = await _base_url()
    return httpx.AsyncClient(base_url=base, timeout=30.0)


def _extract_allowed_tools(steps: list[dict[str, Any]], step_id: str | None) -> list[str]:
    if not step_id:
        return []
    for s in steps:
        if s.get("step_id") == step_id:
            return list(s.get("allowed_tools") or [])
    return []


async def _fetch_runbook_allowed_tools(
    c: httpx.AsyncClient, template_id: str, step_id: str | None
) -> list[str]:
    if not step_id:
        return []
    try:
        rr = await c.get(f"/runbooks/{template_id}")
        rr.raise_for_status()
        steps = (rr.json() or {}).get("steps") or []
        return _extract_allowed_tools(steps, step_id)
    except Exception:
        return []


mcp = FastMCP("stepproof")


@mcp.tool()
async def stepproof_run_start(
    template_id: str,
    owner_id: str = "unknown",
    agent_id: str = "claude-code-worker",
    environment: str = "staging",
) -> dict[str, Any]:
    """Start a StepProof runbook. Returns run_id and current_step."""
    async with (await _client()) as c:
        r = await c.post(
            "/runs",
            json={
                "template_id": template_id,
                "owner_id": owner_id,
                "agent_id": agent_id,
                "environment": environment,
            },
        )
        r.raise_for_status()
        data = r.json()
        try:
            run_id = str(data.get("run_id"))
            current_step = data.get("current_step")
            allowed = await _fetch_runbook_allowed_tools(c, template_id, current_step)
            if run_id:
                write_active_run(
                    run_id=run_id,
                    current_step=current_step,
                    allowed_tools=allowed,
                    template_id=template_id,
                )
        except Exception:
            pass
        return data


@mcp.tool()
async def stepproof_run_status(run_id: str) -> dict[str, Any]:
    """Get the full state of an active runbook run, including all step states."""
    async with (await _client()) as c:
        r = await c.get(f"/runs/{run_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def stepproof_step_complete(
    run_id: str, step_id: str, evidence: dict[str, Any]
) -> dict[str, Any]:
    """Submit evidence for the current step. The runtime dispatches a verifier and
    returns pass/fail plus the next step (or COMPLETED if finished)."""
    async with (await _client()) as c:
        r = await c.post(
            f"/runs/{run_id}/steps/{step_id}/complete",
            json={"evidence": evidence},
        )
        r.raise_for_status()
        data = r.json()
        try:
            status = (data.get("run") or {}).get("status") or data.get("status")
            next_step = (data.get("run") or {}).get("current_step") or data.get("next_step")
            if status and str(status).upper() in ("COMPLETED", "FAILED", "ABANDONED"):
                clear_active_run()
            elif next_step:
                template_id = (data.get("run") or {}).get("template_id")
                allowed = await _fetch_runbook_allowed_tools(c, template_id, next_step) if template_id else []
                write_active_run(
                    run_id=run_id,
                    current_step=next_step,
                    allowed_tools=allowed,
                    template_id=template_id,
                )
        except Exception:
            pass
        return data


@mcp.tool()
async def stepproof_policy_evaluate(
    tool: str,
    action_type: str,
    message: str = "",
    target_env: str = "staging",
    run_id: str | None = None,
    step_id: str | None = None,
    actor_id: str = "claude-code-worker",
    human_owner_id: str = "unknown",
) -> dict[str, Any]:
    """Evaluate whether a proposed action is allowed. Returns allow/deny/transform/
    require_approval/audit with reason and suggested alternative."""
    async with (await _client()) as c:
        r = await c.post(
            "/policy/evaluate",
            json={
                "tool": tool,
                "action_type": action_type,
                "message": message,
                "target_env": target_env,
                "run_id": run_id,
                "step_id": step_id,
                "actor_id": actor_id,
                "human_owner_id": human_owner_id,
            },
        )
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def stepproof_runbook_list() -> dict[str, Any]:
    """List all runbook templates available to start."""
    async with (await _client()) as c:
        r = await c.get("/runbooks")
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def stepproof_runbook_get(template_id: str) -> dict[str, Any]:
    """Fetch the full template for a runbook — its steps, required evidence, and verification methods."""
    async with (await _client()) as c:
        r = await c.get(f"/runbooks/{template_id}")
        r.raise_for_status()
        return r.json()


@mcp.tool()
async def stepproof_keep_me_honest(
    intent: str,
    steps: list[dict[str, Any]],
    environment: str = "staging",
    owner_id: str = "unknown",
    agent_id: str = "claude-code-worker",
    risk_level: str = "medium",
) -> dict[str, Any]:
    """Declare a plan inline and bind yourself to it.

    This is the primary StepProof mode. You submit a list of steps you intend to
    execute. Each step must declare:
      - step_id (stable identifier within this plan)
      - description (what this step does)
      - required_evidence (list of keys you'll submit at completion — concrete
        IDs/hashes, NOT free-text "done")
      - verification_method (must reference a registered Tier 1 verifier)
      - allowed_tools (tools permitted during this step)

    StepProof validates the plan structurally at submission. If it passes, the
    plan becomes your contract for this session — you cannot deviate without
    explicit amendment. Raw Bash, unsanctioned writes, and out-of-sequence
    steps will be denied at the enforcement gate.

    Example steps argument:
      [
        {"step_id": "s1", "description": "Open PR",
         "required_evidence": ["branch_name", "pr_url"],
         "verification_method": "verify_pr_opened",
         "allowed_tools": ["Edit", "git"]},
        {"step_id": "s2", "description": "Tests green",
         "required_evidence": ["ci_run_id"],
         "verification_method": "verify_ci_green",
         "allowed_tools": ["ci_cli"]},
      ]

    Call stepproof_runbook_list + stepproof_runbook_get to see registered
    verification methods and example plan shapes.
    """
    async with (await _client()) as c:
        r = await c.post(
            "/plans/declare",
            json={
                "intent": intent,
                "steps": steps,
                "environment": environment,
                "owner_id": owner_id,
                "agent_id": agent_id,
                "risk_level": risk_level,
            },
        )
        if r.status_code == 422:
            # Return the structured validation errors so the agent can fix them.
            return {"status": "rejected", **r.json().get("detail", {})}
        r.raise_for_status()
        data = r.json()
        try:
            run = data.get("run") or {}
            run_id = str(run.get("run_id"))
            current_step = run.get("current_step")
            template_id = data.get("template_id") or run.get("template_id")
            allowed = _extract_allowed_tools(steps, current_step)
            if run_id:
                write_active_run(
                    run_id=run_id,
                    current_step=current_step,
                    allowed_tools=allowed,
                    template_id=template_id,
                )
        except Exception:
            pass
        return {"status": "accepted", **data}


@mcp.tool()
async def stepproof_heartbeat(run_id: str, ttl_seconds: int = 300) -> dict[str, Any]:
    """Register or refresh liveness for an active run. Without heartbeat the run
    will transition to suspended and then expired per ADR-0003."""
    async with (await _client()) as c:
        r = await c.post(
            f"/runs/{run_id}/heartbeat",
            json={"ttl_seconds": ttl_seconds},
        )
        r.raise_for_status()
        return r.json()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

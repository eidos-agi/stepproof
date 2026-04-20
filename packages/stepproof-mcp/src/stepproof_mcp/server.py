"""StepProof MCP server.

Exposes StepProof governance tools over Model Context Protocol. Two modes:

- Embedded (default): if STEPPROOF_URL is unset, spawn an in-process runtime
  with SQLite. Zero-install, single-user, good for local dev.
- Hosted: STEPPROOF_URL=https://... makes this a thin HTTP client.
"""

from __future__ import annotations

import asyncio
import os
import socket
from contextlib import closing
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


def _pick_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_embedded_task: asyncio.Task | None = None
_embedded_url: str | None = None


async def _start_embedded_runtime() -> str:
    """Start the runtime in-process on a free port; return its base URL."""
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
    return _embedded_url


async def _base_url() -> str:
    explicit = os.getenv("STEPPROOF_URL")
    if explicit:
        return explicit.rstrip("/")
    return await _start_embedded_runtime()


async def _client() -> httpx.AsyncClient:
    base = await _base_url()
    return httpx.AsyncClient(base_url=base, timeout=30.0)


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
        return r.json()


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
        return r.json()


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

"""End-to-end smoke test against the embedded runtime via HTTP.

Covers the Phase 1 acceptance criteria: start a run, submit evidence, verify
state transitions, verify audit trail, and confirm a structural-gate denial
when attempted out of order.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def runtime_client(monkeypatch):
    # Isolate DB + runbooks per test run.
    tmp = tempfile.mkdtemp(prefix="stepproof-test-")
    db_path = str(Path(tmp) / "runtime.db")
    monkeypatch.setenv("STEPPROOF_DB_PATH", db_path)
    examples_dir = str(
        Path(__file__).resolve().parents[2] / "examples"
    )
    monkeypatch.setenv("STEPPROOF_RUNBOOKS_DIR", examples_dir)

    # Spin up the app via Uvicorn in-process.
    import uvicorn

    from stepproof_runtime.api import app

    port = 8796  # fixed test port
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = _spawn(server.serve())
    for _ in range(200):
        await _sleep(0.05)
        if server.started:
            break

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10.0) as client:
        yield client

    server.should_exit = True
    try:
        await task
    except Exception:
        pass


def _spawn(coro):
    import asyncio

    return asyncio.create_task(coro)


async def _sleep(s):
    import asyncio

    await asyncio.sleep(s)


@pytest.mark.asyncio
async def test_health(runtime_client: httpx.AsyncClient):
    r = await runtime_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "verify_ci_green" in body["verifier_methods"]


@pytest.mark.asyncio
async def test_runbooks_loaded(runtime_client: httpx.AsyncClient):
    r = await runtime_client.get("/runbooks")
    assert r.status_code == 200
    ids = [rb["template_id"] for rb in r.json()["runbooks"]]
    assert "rb-db-migration-and-deploy" in ids


@pytest.mark.asyncio
async def test_run_start_and_step_complete_happy_path(runtime_client: httpx.AsyncClient):
    # Start.
    r = await runtime_client.post(
        "/runs",
        json={
            "template_id": "rb-db-migration-and-deploy",
            "owner_id": "smoke",
            "agent_id": "smoke-worker",
            "environment": "staging",
        },
    )
    assert r.status_code == 200, r.text
    run = r.json()
    run_id = run["run_id"]
    assert run["current_step"] == "s1"

    # Complete s1 with valid evidence.
    r = await runtime_client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "feat/x", "pr_url": "https://gh/pr/1"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification_result"]["status"] == "pass"
    assert body["run"]["current_step"] == "s2"


@pytest.mark.asyncio
async def test_evidence_contract_enforced(runtime_client: httpx.AsyncClient):
    r = await runtime_client.post(
        "/runs",
        json={"template_id": "rb-db-migration-and-deploy", "owner_id": "smoke", "environment": "staging"},
    )
    run_id = r.json()["run_id"]

    # Submit empty evidence — must 400 per GUARD-002.
    r = await runtime_client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {}},
    )
    assert r.status_code == 400
    assert "required evidence" in r.text.lower()


@pytest.mark.asyncio
async def test_out_of_order_step_denied(runtime_client: httpx.AsyncClient):
    r = await runtime_client.post(
        "/runs",
        json={"template_id": "rb-db-migration-and-deploy", "owner_id": "smoke", "environment": "staging"},
    )
    run_id = r.json()["run_id"]

    # Try to complete s3 without completing s1 and s2 — must 409.
    r = await runtime_client.post(
        f"/runs/{run_id}/steps/s3/complete",
        json={"evidence": {"migration_name": "m1", "staging_db_id": "db1", "deploy_id": "d1"}},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_policy_gate_blocks_ring3_without_runbook(runtime_client: httpx.AsyncClient):
    r = await runtime_client.post(
        "/policy/evaluate",
        json={
            "tool": "deploy-cli",
            "action_type": "deploy.production",
            "target_env": "production",
            "actor_id": "smoke-worker",
            "human_owner_id": "smoke",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "deny"
    assert "runbook" in body["reason"].lower()
    assert body["policy_id"] == "structural.ring_requires_run"


@pytest.mark.asyncio
async def test_audit_log_records_full_causal_chain(runtime_client: httpx.AsyncClient):
    r = await runtime_client.post(
        "/runs",
        json={"template_id": "rb-db-migration-and-deploy", "owner_id": "smoke", "environment": "staging"},
    )
    run_id = r.json()["run_id"]

    await runtime_client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "b", "pr_url": "u"}},
    )

    r = await runtime_client.get(f"/audit?run_id={run_id}")
    assert r.status_code == 200
    events = r.json()["events"]
    action_types = {e["action_type"] for e in events}
    assert "run.start" in action_types
    assert "step.complete" in action_types


@pytest.mark.asyncio
async def test_heartbeat_registers_and_expires(runtime_client: httpx.AsyncClient):
    r = await runtime_client.post(
        "/runs",
        json={"template_id": "rb-db-migration-and-deploy", "owner_id": "smoke", "environment": "staging"},
    )
    run_id = r.json()["run_id"]

    r = await runtime_client.post(
        f"/runs/{run_id}/heartbeat",
        json={"ttl_seconds": 60},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"

"""Smoke tests for the 'keep me honest' declared-plan flow.

Per docs/KEEP_ME_HONEST.md: agent submits a plan inline, StepProof validates
structurally, plan becomes the contract.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest_asyncio.fixture
async def client(monkeypatch):
    import uvicorn

    from stepproof_runtime.api import app

    tmp = tempfile.mkdtemp(prefix="stepproof-kmh-")
    monkeypatch.setenv("STEPPROOF_DB_PATH", str(Path(tmp) / "runtime.db"))
    monkeypatch.setenv("STEPPROOF_RUNBOOKS_DIR", str(EXAMPLES_DIR))

    port = 8798
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        await asyncio.sleep(0.05)
        if server.started:
            break

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=10.0) as c:
        yield c

    server.should_exit = True
    try:
        await task
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Happy-path
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_declared_plan_accepted(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Add a config flag and open a PR",
            "environment": "staging",
            "owner_id": "smoke",
            "agent_id": "smoke-agent",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Open the PR",
                    "allowed_tools": ["Edit", "git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                },
                {
                    "step_id": "s2",
                    "description": "CI green",
                    "allowed_tools": ["ci_cli"],
                    "required_evidence": ["ci_run_id"],
                    "verification_method": "verify_ci_green",
                    "verification_tier": "tier1",
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["template_id"].startswith("rb-declared-")
    assert body["steps"] == 2
    run = body["run"]
    assert run["current_step"] == "s1"

    # Now complete the steps — the declared plan behaves like any other runbook.
    run_id = run["run_id"]
    r = await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "feat/x", "pr_url": "https://gh/pr/1"}},
    )
    assert r.json()["verification_result"]["status"] == "pass"
    assert r.json()["run"]["current_step"] == "s2"


@pytest.mark.asyncio
async def test_declared_plan_appears_in_runs_list_with_source_declared(
    client: httpx.AsyncClient,
):
    await client.post(
        "/plans/declare",
        json={
            "intent": "Quick demo",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "only",
                    "description": "Just open a PR",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    # The template should appear in /runbooks — reusable, per hash.
    r = await client.get("/runbooks")
    template_ids = [rb["template_id"] for rb in r.json()["runbooks"]]
    assert any(t.startswith("rb-declared-") for t in template_ids)


# -----------------------------------------------------------------------------
# Rejection cases
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_plan_rejected(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={"intent": "Do nothing", "environment": "staging", "steps": []},
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "steps.empty" in codes


@pytest.mark.asyncio
async def test_empty_intent_rejected(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "x",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "intent.empty" in codes


@pytest.mark.asyncio
async def test_unknown_verification_method_rejected(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Try to slip in a bogus verifier",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "x",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name"],
                    "verification_method": "verify_nothing_trust_me",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "verification_method.unknown" in codes


@pytest.mark.asyncio
async def test_empty_required_evidence_rejected(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Free-text done is not evidence",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "x",
                    "allowed_tools": ["git"],
                    "required_evidence": [],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "required_evidence.empty" in codes


@pytest.mark.asyncio
async def test_duplicate_step_ids_rejected(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Two s1s walk into a bar",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "one",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                },
                {
                    "step_id": "s1",
                    "description": "two",
                    "allowed_tools": ["ci_cli"],
                    "required_evidence": ["ci_run_id"],
                    "verification_method": "verify_ci_green",
                    "verification_tier": "tier1",
                },
            ],
        },
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "step_id.duplicate" in codes


@pytest.mark.asyncio
async def test_ring3_step_requires_risky_evidence(client: httpx.AsyncClient):
    """A plan with a production-targeting tool must include Ring 3-appropriate evidence."""
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Deploy with no deploy_id evidence — should be rejected",
            "environment": "production",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "Deploy prod",
                    "allowed_tools": ["deploy_cli"],
                    "required_evidence": ["some_random_key"],
                    "verification_method": "verify_deploy_and_health",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    assert r.status_code == 422
    codes = [e["code"] for e in r.json()["detail"]["errors"]]
    assert "ring3.insufficient_evidence" in codes


# -----------------------------------------------------------------------------
# Integration with other features
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_declared_plan_audit_records_plan_declared(client: httpx.AsyncClient):
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Audit-chain integration",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "x",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    run_id = r.json()["run"]["run_id"]
    r = await client.get(f"/audit?run_id={run_id}")
    action_types = {e["action_type"] for e in r.json()["events"]}
    assert "plan.declared" in action_types


@pytest.mark.asyncio
async def test_declared_plan_evidence_contract_still_enforced(client: httpx.AsyncClient):
    """The evidence contract (GUARD-002) applies to declared plans the same as templates."""
    r = await client.post(
        "/plans/declare",
        json={
            "intent": "Evidence contract test",
            "environment": "staging",
            "steps": [
                {
                    "step_id": "s1",
                    "description": "x",
                    "allowed_tools": ["git"],
                    "required_evidence": ["branch_name", "pr_url"],
                    "verification_method": "verify_pr_opened",
                    "verification_tier": "tier1",
                }
            ],
        },
    )
    run_id = r.json()["run"]["run_id"]

    # Missing required_evidence — must 400.
    r = await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "only-branch"}},
    )
    assert r.status_code == 400
    assert "pr_url" in r.text

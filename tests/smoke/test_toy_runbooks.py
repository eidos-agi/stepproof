"""Smoke tests for the full library of toy runbooks under examples/.

Each runbook must:
1. Load without schema errors.
2. Reference only registered verifier methods.
3. Be startable against its declared environment.

Plus per-runbook happy-path evidence submission where it's non-trivial.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio
import tempfile

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest_asyncio.fixture
async def client(monkeypatch):
    import uvicorn

    from stepproof_runtime.api import app

    tmp = tempfile.mkdtemp(prefix="stepproof-toys-")
    monkeypatch.setenv("STEPPROOF_STATE_DIR", str(Path(tmp) / ".stepproof"))
    monkeypatch.setenv("STEPPROOF_RUNBOOKS_DIR", str(EXAMPLES_DIR))

    # Reset in-memory template registry so each test starts clean.
    from stepproof_runtime import runbooks
    runbooks.clear_registry()

    port = 8797
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    import asyncio

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


EXPECTED_TOYS = {
    "rb-db-migration-and-deploy",
    "rb-fleetio-connector-deploy",
    "rb-hotfix-prod",
    "rb-secret-rotation",
    "rb-pr-review-and-merge",
    "rb-data-backfill",
    "rb-dep-upgrade",
    "rb-rollback-prod",
}


@pytest.mark.asyncio
async def test_all_toys_loaded(client: httpx.AsyncClient):
    r = await client.get("/runbooks")
    assert r.status_code == 200
    template_ids = {rb["template_id"] for rb in r.json()["runbooks"]}
    missing = EXPECTED_TOYS - template_ids
    assert not missing, f"Runbooks failed to load: {missing}"


@pytest.mark.asyncio
async def test_all_toys_reference_registered_verifiers(client: httpx.AsyncClient):
    r = await client.get("/health")
    registered = set(r.json()["verifier_methods"])

    r = await client.get("/runbooks")
    templates = r.json()["runbooks"]
    for t in templates:
        d = await client.get(f"/runbooks/{t['template_id']}")
        for step in d.json()["steps"]:
            method = step["verification_method"]
            assert method in registered, (
                f"Runbook {t['template_id']} step {step['step_id']} references "
                f"unregistered verifier {method!r}"
            )


@pytest.mark.asyncio
async def test_fleetio_connector_happy_path_s1(client: httpx.AsyncClient):
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-fleetio-connector-deploy",
            "owner_id": "smoke",
            "environment": "staging",
        },
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    # Complete s1 (PR opened).
    r = await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "feat/fleetio", "pr_url": "https://gh/pr/42"}},
    )
    assert r.status_code == 200
    assert r.json()["verification_result"]["status"] == "pass"


@pytest.mark.asyncio
async def test_row_count_verifier_catches_silent_null_violation(client: httpx.AsyncClient):
    """Verifier must fail when rows_loaded != rows_extracted (silent null violation)."""
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-data-backfill",
            "owner_id": "smoke",
            "environment": "staging",
        },
    )
    run_id = r.json()["run_id"]

    # s1 happy path.
    await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"branch_name": "backfill-1", "pr_url": "https://gh/jobs/1",
                           "job_id": "job1", "vendor": "fleetio", "table": "vehicles"}},
    )

    # s2 with mismatched rows (silent null violation): extracted=75, loaded=0.
    r = await client.post(
        f"/runs/{run_id}/steps/s2/complete",
        json={"evidence": {"rows_extracted": 75, "rows_loaded": 0}},
    )
    assert r.status_code == 200
    result = r.json()["verification_result"]
    assert result["status"] == "fail"
    assert "mismatch" in result["reason"].lower()


@pytest.mark.asyncio
async def test_zombie_detector_catches_multi_active_deployment(client: httpx.AsyncClient):
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-hotfix-prod",
            "owner_id": "smoke",
            "environment": "production",
        },
    )
    run_id = r.json()["run_id"]

    # Burn through s1..s4 with stub evidence.
    for step, ev in [
        ("s1", {"branch_name": "hotfix-1", "pr_url": "https://gh/hotfix/1"}),
        ("s2", {"ci_run_id": "ci-42"}),
        ("s3", {"pr_url": "https://gh/hotfix/1", "approval_count": 1}),
        ("s4", {"deploy_id": "dep-5", "declared_env": "production", "database_url_env": "production"}),
    ]:
        r = await client.post(f"/runs/{run_id}/steps/{step}/complete", json={"evidence": ev})
        assert r.status_code == 200, f"{step} failed: {r.text}"

    # s5 — 2 active deployments (zombie present).
    r = await client.post(
        f"/runs/{run_id}/steps/s5/complete",
        json={"evidence": {"active_deployment_count": 2, "deploy_id": "dep-5"}},
    )
    assert r.json()["verification_result"]["status"] == "fail"

    # Recovery: resubmit with active_deployment_count=1. The step is now
    # failed so the runtime blocks re-submission. That's the right
    # behavior — the operator must intervene (on_fail=escalate_human).


@pytest.mark.asyncio
async def test_env_isolation_catches_env_cross_wiring(client: httpx.AsyncClient):
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-fleetio-connector-deploy",
            "owner_id": "smoke",
            "environment": "staging",
        },
    )
    run_id = r.json()["run_id"]

    # Burn through s1..s4.
    for step, ev in [
        ("s1", {"branch_name": "feat/fleetio", "pr_url": "https://gh/pr/42"}),
        ("s2", {"ci_run_id": "ci-1"}),
        ("s3", {"pr_url": "https://gh/pr/42", "approval_count": 1}),
        ("s4", {"migration_name": "20260420_fleetio", "staging_db_id": "stg-1", "deploy_id": "dep-1"}),
    ]:
        r = await client.post(f"/runs/{run_id}/steps/{step}/complete", json={"evidence": ev})
        assert r.status_code == 200, f"{step} failed: {r.text}"

    # s5 with CROSS-WIRED environment (declared staging, DATABASE_URL resolves to production).
    r = await client.post(
        f"/runs/{run_id}/steps/s5/complete",
        json={"evidence": {"deploy_id": "dep-2", "declared_env": "staging",
                           "database_url_env": "production"}},
    )
    result = r.json()["verification_result"]
    assert result["status"] == "fail"
    assert "cross-wiring" in result["reason"].lower()


@pytest.mark.asyncio
async def test_secret_rotation_requires_full_evidence(client: httpx.AsyncClient):
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-secret-rotation",
            "owner_id": "smoke",
            "environment": "production",
        },
    )
    run_id = r.json()["run_id"]

    # s1 — new version issued.
    r = await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"secret_id": "DB_PASS", "new_version": 7, "old_invalidated": False}},
    )
    # False means s1's verifier fails (since verify_secret_rotated wants all three true).
    # But s1 only requires [secret_id, new_version] — let me re-check: required_evidence = [secret_id, new_version].
    # old_invalidated is not required for s1. The verifier runs and checks. Without old_invalidated=True it fails.
    # This is intentional: secret rotation is an all-or-nothing trio.
    assert r.status_code == 200
    assert r.json()["verification_result"]["status"] == "fail"


@pytest.mark.asyncio
async def test_rollback_prod_happy_path(client: httpx.AsyncClient):
    r = await client.post(
        "/runs",
        json={
            "template_id": "rb-rollback-prod",
            "owner_id": "smoke",
            "environment": "production",
        },
    )
    run_id = r.json()["run_id"]

    # s1 approval.
    await client.post(
        f"/runs/{run_id}/steps/s1/complete",
        json={"evidence": {"pr_url": "https://gh/incident/99", "approval_count": 1}},
    )

    # s2 rollback succeeded.
    r = await client.post(
        f"/runs/{run_id}/steps/s2/complete",
        json={"evidence": {"rollback_deploy_id": "dep-rollback", "prior_deploy_id": "dep-99"}},
    )
    assert r.json()["verification_result"]["status"] == "pass"

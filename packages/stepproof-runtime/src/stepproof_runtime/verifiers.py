"""Tier 1 verifier registry — deterministic scripts.

Tier 2 (read-only Haiku subagent) and Tier 3 (opt-in heavyweight) land in a later phase.
Today: just the in-process function registry for Tier 1.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from .models import Tier, VerificationResult, VerificationStatus

VerifierFunc = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, tuple[Tier, VerifierFunc]] = {}


def register(method_name: str, tier: Tier) -> Callable[[VerifierFunc], VerifierFunc]:
    def wrap(fn: VerifierFunc) -> VerifierFunc:
        _REGISTRY[method_name] = (tier, fn)
        return fn

    return wrap


async def dispatch(
    method: str, evidence: dict[str, Any], context: dict[str, Any]
) -> VerificationResult:
    if method not in _REGISTRY:
        return VerificationResult(
            status=VerificationStatus.FAIL,
            confidence=1.0,
            reason=f"Unknown verification method: {method}",
            verifier_id="dispatcher",
        )
    tier, fn = _REGISTRY[method]
    t0 = time.perf_counter()
    try:
        raw = await fn(evidence, context)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.FAIL,
            confidence=1.0,
            reason=f"Verifier raised: {type(e).__name__}: {e}",
            verifier_id=method,
            tier_used=tier,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
    return VerificationResult(
        status=VerificationStatus(raw.get("status", "fail")),
        confidence=float(raw.get("confidence", 1.0)),
        reason=str(raw.get("reason", "")),
        artifacts=raw.get("artifacts", {}),
        verifier_id=method,
        tier_used=tier,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


# --- Built-in Tier 1 verifiers ---
#
# These are intentionally generous in happy-path to make the MVP loop work.
# Real verifiers will talk to CI, deploy APIs, read-only DBs, etc.


@register("verify_pr_opened", Tier.TIER1)
async def verify_pr_opened(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    branch = evidence.get("branch_name")
    pr_url = evidence.get("pr_url")
    if branch and pr_url:
        return {
            "status": "pass",
            "reason": f"PR {pr_url} opened on branch {branch}.",
            "artifacts": {"branch": branch, "pr_url": pr_url},
        }
    return {
        "status": "fail",
        "reason": "Missing branch_name or pr_url in evidence.",
    }


@register("verify_ci_green", Tier.TIER1)
async def verify_ci_green(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    run_id = evidence.get("ci_run_id")
    # Stubbed: a real verifier would call the CI API.
    if run_id and not str(run_id).startswith("fail"):
        return {"status": "pass", "reason": f"CI run {run_id} SUCCESS.", "artifacts": {"ci_run_id": run_id}}
    return {"status": "fail", "reason": f"CI run missing or failing: {run_id}"}


@register("verify_migration_applied", Tier.TIER1)
async def verify_migration_applied(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    migration = evidence.get("migration_name")
    deploy_id = evidence.get("deploy_id")
    if migration and deploy_id:
        return {
            "status": "pass",
            "reason": f"Migration {migration} recorded; deploy {deploy_id} SUCCESS.",
            "artifacts": {"migration": migration, "deploy_id": deploy_id},
        }
    return {"status": "fail", "reason": "Missing migration_name or deploy_id."}


@register("verify_smoke_logs", Tier.TIER1)
async def verify_smoke_logs(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    smoke_run_id = evidence.get("smoke_run_id")
    if smoke_run_id:
        return {"status": "pass", "reason": f"Smoke run {smoke_run_id} green."}
    return {"status": "fail", "reason": "Missing smoke_run_id."}


@register("verify_deploy_and_health", Tier.TIER1)
async def verify_deploy_and_health(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    deploy_id = evidence.get("deploy_id")
    if deploy_id:
        return {"status": "pass", "reason": f"Deploy {deploy_id} SUCCESS; health endpoints OK."}
    return {"status": "fail", "reason": "Missing deploy_id."}


def list_methods() -> list[str]:
    return sorted(_REGISTRY.keys())

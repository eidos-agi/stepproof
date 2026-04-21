"""FastAPI control plane — filesystem-backed (store.py), no database."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import runbooks, store, verifiers
from .models import (
    AuditEvent,
    Decision,
    Heartbeat,
    LivenessStatus,
    PlanDeclaration,
    PolicyDecision,
    PolicyInput,
    RunbookTemplate,
    RunStatus,
    StepRun,
    StepStatus,
    VerificationStatus,
    WorkflowRun,
    utcnow,
)
from .plan_validator import validate_plan
from .policy import PolicyEngine, classify_ring, structural_gate


# --- App lifecycle ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runbooks.sync_from_disk()
    yield


app = FastAPI(
    title="StepProof Runtime",
    version="0.0.1",
    description="Verification-aware governance control plane.",
    lifespan=lifespan,
)


# --- Helpers ---


def _sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, default=str, sort_keys=True).encode()).hexdigest()


def _record_audit(event: AuditEvent) -> None:
    """Append an audit event to both the per-run stream and the global stream."""
    store.append_event(event)


async def _prior_steps_verified(run: WorkflowRun) -> bool:
    template = await runbooks.get_template(run.template_id)
    if template is None or run.current_step is None:
        return False
    return store.prior_steps_verified(
        run.run_id,
        [s.step_id for s in template.steps],
        run.current_step,
    )


# --- Request/response bodies ---


class RunStartRequest(BaseModel):
    template_id: str
    owner_id: str = "unknown"
    agent_id: str = "unknown"
    environment: str = "staging"


class EvidencePayload(BaseModel):
    evidence: dict[str, Any]


class HeartbeatRequest(BaseModel):
    ttl_seconds: int = 300


class PlanRejected(BaseModel):
    """422 body when a declared plan fails validation."""

    errors: list[dict[str, Any]]
    message: str = "Plan rejected by StepProof structural validation."


# --- Endpoints ---


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": app.version, "verifier_methods": verifiers.list_methods()}


@app.post("/runs", response_model=WorkflowRun)
async def run_start(req: RunStartRequest) -> WorkflowRun:
    template = await runbooks.get_template(req.template_id)
    if template is None:
        raise HTTPException(404, f"Runbook template not found: {req.template_id}")
    if req.environment not in template.allowed_environments:
        raise HTTPException(
            400, f"Environment '{req.environment}' not in {template.allowed_environments}"
        )
    run = WorkflowRun(
        template_id=template.template_id,
        template_version=template.version,
        owner_id=req.owner_id,
        agent_id=req.agent_id,
        environment=req.environment,
        current_step=template.steps[0].step_id if template.steps else None,
    )
    store.create_run(run, [s.step_id for s in template.steps])
    _record_audit(
        AuditEvent(
            actor_type="system",
            actor_id="runtime",
            human_owner_id=req.owner_id,
            run_id=run.run_id,
            action_type="run.start",
            decision=Decision.ALLOW,
            policy_id="system.run_started",
            reason=f"Started runbook {template.template_id} v{template.version}",
            payload_hash=_sha256(req.model_dump()),
        )
    )
    return run


@app.post("/plans/declare")
async def plan_declare(plan: PlanDeclaration) -> dict[str, Any]:
    """Accept an agent-declared plan ("keep me honest"), validate
    structurally, register it as an in-memory runbook template, and
    create a WorkflowRun against it.
    """
    # 1. Validate.
    errors = validate_plan(plan)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Plan rejected by StepProof structural validation.",
                "errors": [e.model_dump(exclude_none=True) for e in errors],
            },
        )

    # 2. Derive a stable template_id for the declared plan.
    plan_payload = json.dumps(plan.model_dump(mode="json"), sort_keys=True)
    plan_hash = hashlib.sha256(plan_payload.encode()).hexdigest()[:12]
    template_id = f"rb-declared-{plan_hash}"

    # 3. Register as an in-memory runbook template.
    template = RunbookTemplate(
        template_id=template_id,
        version="1.0.0",
        name=f"Declared: {plan.intent[:60]}",
        description=plan.intent,
        risk_level=plan.risk_level,
        allowed_environments=[plan.environment],
        requires_human_signoff=False,
        shadow=False,
        source="declared",
        steps=plan.steps,
    )
    runbooks.register_template(template)

    # 4. Create the run.
    run = WorkflowRun(
        template_id=template_id,
        template_version="1.0.0",
        owner_id=plan.owner_id,
        agent_id=plan.agent_id,
        environment=plan.environment,
        current_step=plan.steps[0].step_id,
    )
    store.create_run(run, [s.step_id for s in plan.steps])
    _record_audit(
        AuditEvent(
            actor_type="worker_agent",
            actor_id=plan.agent_id,
            human_owner_id=plan.owner_id,
            run_id=run.run_id,
            action_type="plan.declared",
            decision=Decision.ALLOW,
            policy_id="system.plan_declared",
            reason=f"Declared plan: {plan.intent[:200]}",
            payload_hash=plan_hash,
        )
    )
    return {
        "run": run.model_dump(mode="json"),
        "template_id": template_id,
        "plan_hash": plan_hash,
        "steps": len(plan.steps),
    }


@app.post("/runs/{run_id}/abandon")
async def run_abandon(run_id: UUID, reason: str = "session_ended") -> dict[str, Any]:
    """Mark a run as abandoned. Idempotent — already-terminal runs are a no-op."""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    if run.status in (RunStatus.COMPLETED, RunStatus.ABANDONED, RunStatus.FAILED):
        return {"run_id": str(run_id), "status": run.status.value, "abandoned": False}
    run.status = RunStatus.ABANDONED
    run.ended_at = utcnow()
    store.update_run(run)
    _record_audit(
        AuditEvent(
            actor_type="system",
            actor_id="runtime",
            human_owner_id=run.owner_id,
            run_id=run_id,
            action_type="run.abandon",
            decision=Decision.ALLOW,
            policy_id="system.run_abandoned",
            reason=f"Run abandoned: {reason}",
            payload_hash=_sha256({"reason": reason}),
        )
    )
    return {"run_id": str(run_id), "status": "abandoned", "abandoned": True, "reason": reason}


@app.get("/runs/{run_id}")
async def run_status(run_id: UUID) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    steps = store.list_steps(run_id)
    return {"run": run.model_dump(mode="json"), "steps": [s.model_dump(mode="json") for s in steps]}


@app.get("/runs")
async def runs_list(limit: int = 50) -> dict[str, Any]:
    runs = store.list_runs(limit=limit)
    return {
        "runs": [
            {
                "run_id": str(r.run_id),
                "template_id": r.template_id,
                "environment": r.environment,
                "current_step": r.current_step,
                "status": r.status.value,
                "started_at": r.started_at.isoformat(),
            }
            for r in runs
        ]
    }


@app.post("/runs/{run_id}/steps/{step_id}/complete")
async def step_complete(
    run_id: UUID, step_id: str, payload: EvidencePayload
) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    if run.current_step != step_id:
        raise HTTPException(
            409, f"Run is on step {run.current_step}, not {step_id}"
        )

    template = await runbooks.get_template(run.template_id)
    if template is None:
        raise HTTPException(500, "Template disappeared")
    step_template = next((s for s in template.steps if s.step_id == step_id), None)
    if step_template is None:
        raise HTTPException(500, f"Step template not found: {step_id}")

    # Evidence contract (GUARD-002).
    missing = [k for k in step_template.required_evidence if k not in payload.evidence]
    if missing:
        raise HTTPException(400, f"Missing required evidence keys: {missing}")

    # Mark awaiting_verification and bump attempts.
    store.update_step(
        run_id, step_id,
        status=StepStatus.AWAITING_VERIFICATION,
        evidence=payload.evidence,
        bump_attempts=True,
        set_started_at=utcnow(),
    )

    # Dispatch verifier (Tier 1 is sync-ish, some are async).
    result = await verifiers.dispatch(
        method=step_template.verification_method,
        evidence=payload.evidence,
        context={
            "runbook_id": run.template_id,
            "environment": run.environment,
            "owner_id": run.owner_id,
            "step_id": step_id,
        },
    )

    if result.status == VerificationStatus.PASS:
        # Find next step in template order.
        step_ids = [s.step_id for s in template.steps]
        idx = step_ids.index(step_id)
        next_step = step_ids[idx + 1] if idx + 1 < len(step_ids) else None
        new_run_status = RunStatus.ACTIVE if next_step else RunStatus.COMPLETED
        store.update_step(
            run_id, step_id,
            status=StepStatus.VERIFIED,
            verification_result=result.model_dump(mode="json"),
            set_ended_at=utcnow(),
        )
        run.current_step = next_step
        run.status = new_run_status
        if new_run_status == RunStatus.COMPLETED:
            run.ended_at = utcnow()
        store.update_run(run)
        decision = Decision.ALLOW
        reason = f"Step {step_id} verified; advancing to {next_step or 'COMPLETED'}"
    else:
        store.update_step(
            run_id, step_id,
            status=StepStatus.FAILED,
            verification_result=result.model_dump(mode="json"),
            set_ended_at=utcnow(),
        )
        decision = Decision.DENY
        reason = f"Step {step_id} verification failed: {result.reason}"

    _record_audit(
        AuditEvent(
            actor_type="worker_agent",
            actor_id=run.agent_id,
            human_owner_id=run.owner_id,
            run_id=run_id,
            step_id=step_id,
            action_type="step.complete",
            decision=decision,
            policy_id=f"verifier.{step_template.verification_method}",
            reason=reason,
            payload_hash=_sha256(payload.evidence),
        )
    )

    refreshed = store.get_run(run_id)
    return {
        "verification_result": result.model_dump(mode="json"),
        "run": refreshed.model_dump(mode="json") if refreshed else None,
    }


@app.post("/policy/evaluate", response_model=PolicyDecision)
async def policy_evaluate(event: PolicyInput) -> PolicyDecision:
    # Resolve run state if one is bound.
    run_active = False
    prior_verified = True
    if event.run_id is not None:
        run = store.get_run(event.run_id)
        if run is not None and run.status == RunStatus.ACTIVE:
            run_active = True
            prior_verified = await _prior_steps_verified(run)

    event.ring = event.ring or classify_ring(event.action_type, event.target_env)

    gate = structural_gate(event, run_active=run_active, prior_verified=prior_verified)
    if gate is not None:
        _record_audit(
            AuditEvent(
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                human_owner_id=event.human_owner_id,
                run_id=event.run_id,
                step_id=event.step_id,
                action_type=event.action_type,
                tool=event.tool,
                decision=gate.decision,
                policy_id=gate.policy_id,
                reason=gate.reason,
                payload_hash=_sha256(event.model_dump(mode="json")),
            )
        )
        return gate

    # No rule set loaded in MVP — default allow with audit.
    engine = PolicyEngine()
    decision = engine.evaluate(event)
    _record_audit(
        AuditEvent(
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            human_owner_id=event.human_owner_id,
            run_id=event.run_id,
            step_id=event.step_id,
            action_type=event.action_type,
            tool=event.tool,
            decision=decision.decision,
            policy_id=decision.policy_id,
            reason=decision.reason,
            payload_hash=_sha256(event.model_dump(mode="json")),
        )
    )
    return decision


@app.post("/runs/{run_id}/heartbeat", response_model=Heartbeat)
async def heartbeat(run_id: UUID, req: HeartbeatRequest) -> Heartbeat:
    now = utcnow()
    expires_at = now + timedelta(seconds=req.ttl_seconds)
    hb = Heartbeat(
        run_id=run_id,
        ttl_seconds=req.ttl_seconds,
        registered_at=now,
        expires_at=expires_at,
        status=LivenessStatus.ACTIVE,
    )
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"Run not found: {run_id}")
    store.write_heartbeat(hb)
    return hb


@app.get("/runbooks")
async def runbooks_list() -> dict[str, Any]:
    templates = await runbooks.list_templates()
    return {
        "runbooks": [
            {
                "template_id": t.template_id,
                "name": t.name,
                "version": t.version,
                "risk_level": t.risk_level,
                "steps_count": len(t.steps),
                "requires_human_signoff": t.requires_human_signoff,
            }
            for t in templates
        ]
    }


@app.get("/runbooks/{template_id}")
async def runbook_get(template_id: str) -> dict[str, Any]:
    t = await runbooks.get_template(template_id)
    if t is None:
        raise HTTPException(404, f"Runbook not found: {template_id}")
    return t.model_dump(mode="json")


@app.get("/audit")
async def audit_list(run_id: UUID | None = None, limit: int = 100) -> dict[str, Any]:
    events = store.list_events(run_id=run_id, limit=limit)
    return {
        "events": [
            {
                "event_id": e.get("event_id"),
                "timestamp": e.get("timestamp"),
                "actor_type": e.get("actor_type"),
                "actor_id": e.get("actor_id"),
                "run_id": e.get("run_id"),
                "step_id": e.get("step_id"),
                "action_type": e.get("action_type"),
                "tool": e.get("tool"),
                "decision": e.get("decision"),
                "policy_id": e.get("policy_id"),
                "reason": e.get("reason"),
            }
            for e in events
        ]
    }

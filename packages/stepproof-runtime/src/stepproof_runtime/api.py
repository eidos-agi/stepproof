"""FastAPI control plane."""

from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import runbooks, verifiers
from .db import connect, init_db
from .models import (
    AuditEvent,
    Decision,
    Heartbeat,
    LivenessStatus,
    PlanDeclaration,
    PolicyDecision,
    PolicyInput,
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
    await init_db()
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


async def _record_audit(conn, event: AuditEvent) -> None:
    await conn.execute(
        """
        INSERT INTO audit_log
          (event_id, timestamp, actor_type, actor_id, human_owner_id,
           run_id, step_id, action_type, tool, decision, policy_id, reason,
           compliance_tags, payload_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(event.event_id),
            event.timestamp.isoformat(),
            event.actor_type,
            event.actor_id,
            event.human_owner_id,
            str(event.run_id) if event.run_id else None,
            event.step_id,
            event.action_type,
            event.tool,
            event.decision.value if event.decision else None,
            event.policy_id,
            event.reason,
            json.dumps(event.compliance_tags),
            event.payload_hash,
        ),
    )
    await conn.commit()


async def _run_state(conn, run_id: UUID) -> WorkflowRun | None:
    cursor = await conn.execute(
        "SELECT * FROM workflow_runs WHERE run_id = ?", (str(run_id),)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return WorkflowRun(
        run_id=UUID(row["run_id"]),
        template_id=row["template_id"],
        template_version=row["template_version"],
        owner_id=row["owner_id"],
        agent_id=row["agent_id"],
        environment=row["environment"],
        current_step=row["current_step"],
        status=RunStatus(row["status"]),
        started_at=datetime.fromisoformat(row["started_at"]),
        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
    )


async def _step_runs_for(conn, run_id: UUID) -> list[StepRun]:
    cursor = await conn.execute(
        "SELECT * FROM step_runs WHERE run_id = ? ORDER BY step_id", (str(run_id),)
    )
    rows = await cursor.fetchall()
    out: list[StepRun] = []
    for row in rows:
        vr = json.loads(row["verification_result"]) if row["verification_result"] else None
        out.append(
            StepRun(
                run_id=UUID(row["run_id"]),
                step_id=row["step_id"],
                status=StepStatus(row["status"]),
                evidence=json.loads(row["evidence"]),
                verification_result=vr,
                attempts=int(row["attempts"]),
                started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            )
        )
    return out


async def _prior_steps_verified(conn, run: WorkflowRun) -> bool:
    template = await runbooks.get_template(run.template_id)
    if template is None or run.current_step is None:
        return False
    required_step_ids = []
    for s in template.steps:
        if s.step_id == run.current_step:
            break
        required_step_ids.append(s.step_id)
    if not required_step_ids:
        return True
    placeholders = ",".join("?" for _ in required_step_ids)
    cursor = await conn.execute(
        f"SELECT status FROM step_runs WHERE run_id = ? AND step_id IN ({placeholders})",
        (str(run.run_id), *required_step_ids),
    )
    rows = await cursor.fetchall()
    if len(rows) < len(required_step_ids):
        return False
    return all(row["status"] == StepStatus.VERIFIED.value for row in rows)


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
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO workflow_runs
              (run_id, template_id, template_version, owner_id, agent_id,
               environment, current_step, status, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(run.run_id),
                run.template_id,
                run.template_version,
                run.owner_id,
                run.agent_id,
                run.environment,
                run.current_step,
                run.status.value,
                run.started_at.isoformat(),
                None,
            ),
        )
        for step in template.steps:
            await conn.execute(
                """
                INSERT INTO step_runs
                  (run_id, step_id, status, evidence, attempts)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(run.run_id), step.step_id, StepStatus.PENDING.value, "{}", 0),
            )
        await _record_audit(
            conn,
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
            ),
        )
        await conn.commit()
    return run


@app.post("/plans/declare")
async def plan_declare(plan: PlanDeclaration) -> dict[str, Any]:
    """Accept an agent-declared plan ("keep me honest"), validate structurally,
    register it as a runbook template, and create a WorkflowRun against it.
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

    # 3. Persist as a runbook_template with source='declared'.
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO runbook_templates
              (template_id, version, name, description, risk_level,
               allowed_environments, requires_human_signoff, shadow, source,
               steps, source_path, intent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(template_id) DO UPDATE SET
              intent = excluded.intent
            """,
            (
                template_id,
                "1.0.0",
                f"Declared: {plan.intent[:60]}",
                plan.intent,
                plan.risk_level,
                json.dumps([plan.environment]),
                0,
                0,
                "declared",
                json.dumps([s.model_dump(mode="json") for s in plan.steps]),
                None,
                plan.intent,
            ),
        )

        # 4. Create the run — same shape as /runs.
        run = WorkflowRun(
            template_id=template_id,
            template_version="1.0.0",
            owner_id=plan.owner_id,
            agent_id=plan.agent_id,
            environment=plan.environment,
            current_step=plan.steps[0].step_id,
        )
        await conn.execute(
            """
            INSERT INTO workflow_runs
              (run_id, template_id, template_version, owner_id, agent_id,
               environment, current_step, status, started_at, ended_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(run.run_id),
                run.template_id,
                run.template_version,
                run.owner_id,
                run.agent_id,
                run.environment,
                run.current_step,
                run.status.value,
                run.started_at.isoformat(),
                None,
            ),
        )
        for step in plan.steps:
            await conn.execute(
                """INSERT INTO step_runs (run_id, step_id, status, evidence, attempts)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(run.run_id), step.step_id, StepStatus.PENDING.value, "{}", 0),
            )
        await _record_audit(
            conn,
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
            ),
        )
        await conn.commit()

    return {
        "run": run.model_dump(mode="json"),
        "template_id": template_id,
        "plan_hash": plan_hash,
        "steps": len(plan.steps),
    }


@app.get("/runs/{run_id}")
async def run_status(run_id: UUID) -> dict[str, Any]:
    async with connect() as conn:
        run = await _run_state(conn, run_id)
        if run is None:
            raise HTTPException(404, f"Run not found: {run_id}")
        steps = await _step_runs_for(conn, run_id)
    return {"run": run.model_dump(mode="json"), "steps": [s.model_dump(mode="json") for s in steps]}


@app.get("/runs")
async def runs_list(limit: int = 50) -> dict[str, Any]:
    async with connect() as conn:
        cursor = await conn.execute(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?", (min(limit, 200),)
        )
        rows = await cursor.fetchall()
    return {
        "runs": [
            {
                "run_id": r["run_id"],
                "template_id": r["template_id"],
                "environment": r["environment"],
                "current_step": r["current_step"],
                "status": r["status"],
                "started_at": r["started_at"],
            }
            for r in rows
        ]
    }


@app.post("/runs/{run_id}/steps/{step_id}/complete")
async def step_complete(
    run_id: UUID, step_id: str, payload: EvidencePayload
) -> dict[str, Any]:
    async with connect() as conn:
        run = await _run_state(conn, run_id)
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
        await conn.execute(
            """UPDATE step_runs SET status = ?, evidence = ?, attempts = attempts + 1,
                                     started_at = COALESCE(started_at, ?)
               WHERE run_id = ? AND step_id = ?""",
            (
                StepStatus.AWAITING_VERIFICATION.value,
                json.dumps(payload.evidence),
                utcnow().isoformat(),
                str(run_id),
                step_id,
            ),
        )
        await conn.commit()

    # Dispatch verifier (outside connection; Tier 1 is sync-ish).
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

    async with connect() as conn:
        if result.status == VerificationStatus.PASS:
            # Find next step in template order.
            step_ids = [s.step_id for s in template.steps]
            idx = step_ids.index(step_id)
            next_step = step_ids[idx + 1] if idx + 1 < len(step_ids) else None
            new_run_status = RunStatus.ACTIVE if next_step else RunStatus.COMPLETED
            await conn.execute(
                """UPDATE step_runs SET status = ?, verification_result = ?, ended_at = ?
                   WHERE run_id = ? AND step_id = ?""",
                (
                    StepStatus.VERIFIED.value,
                    json.dumps(result.model_dump(mode="json")),
                    utcnow().isoformat(),
                    str(run_id),
                    step_id,
                ),
            )
            await conn.execute(
                """UPDATE workflow_runs SET current_step = ?, status = ?,
                                             ended_at = COALESCE(?, ended_at)
                   WHERE run_id = ?""",
                (
                    next_step,
                    new_run_status.value,
                    utcnow().isoformat() if new_run_status == RunStatus.COMPLETED else None,
                    str(run_id),
                ),
            )
            decision = Decision.ALLOW
            reason = f"Step {step_id} verified; advancing to {next_step or 'COMPLETED'}"
        else:
            await conn.execute(
                """UPDATE step_runs SET status = ?, verification_result = ?, ended_at = ?
                   WHERE run_id = ? AND step_id = ?""",
                (
                    StepStatus.FAILED.value,
                    json.dumps(result.model_dump(mode="json")),
                    utcnow().isoformat(),
                    str(run_id),
                    step_id,
                ),
            )
            decision = Decision.DENY
            reason = f"Step {step_id} verification failed: {result.reason}"

        await _record_audit(
            conn,
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
            ),
        )
        await conn.commit()

        refreshed = await _run_state(conn, run_id)
        return {
            "verification_result": result.model_dump(mode="json"),
            "run": refreshed.model_dump(mode="json") if refreshed else None,
        }


@app.post("/policy/evaluate", response_model=PolicyDecision)
async def policy_evaluate(event: PolicyInput) -> PolicyDecision:
    # Resolve run state if one is bound.
    run_active = False
    prior_verified = True
    async with connect() as conn:
        if event.run_id is not None:
            run = await _run_state(conn, event.run_id)
            if run is not None and run.status == RunStatus.ACTIVE:
                run_active = True
                prior_verified = await _prior_steps_verified(conn, run)

    event.ring = event.ring or classify_ring(event.action_type, event.target_env)

    gate = structural_gate(event, run_active=run_active, prior_verified=prior_verified)
    if gate is not None:
        async with connect() as conn:
            await _record_audit(
                conn,
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
                ),
            )
        return gate

    # No rule set loaded in MVP — default allow with audit.
    engine = PolicyEngine()
    decision = engine.evaluate(event)
    async with connect() as conn:
        await _record_audit(
            conn,
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
            ),
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
    async with connect() as conn:
        run = await _run_state(conn, run_id)
        if run is None:
            raise HTTPException(404, f"Run not found: {run_id}")
        await conn.execute(
            """
            INSERT INTO liveness_heartbeats
              (run_id, ttl_seconds, registered_at, expires_at, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              ttl_seconds = excluded.ttl_seconds,
              registered_at = excluded.registered_at,
              expires_at = excluded.expires_at,
              status = excluded.status
            """,
            (str(run_id), req.ttl_seconds, now.isoformat(), expires_at.isoformat(),
             LivenessStatus.ACTIVE.value),
        )
        await conn.commit()
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
    async with connect() as conn:
        if run_id is not None:
            cursor = await conn.execute(
                "SELECT * FROM audit_log WHERE run_id = ? ORDER BY timestamp DESC LIMIT ?",
                (str(run_id), min(limit, 500)),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (min(limit, 500),)
            )
        rows = await cursor.fetchall()
    return {
        "events": [
            {
                "event_id": r["event_id"],
                "timestamp": r["timestamp"],
                "actor_type": r["actor_type"],
                "actor_id": r["actor_id"],
                "run_id": r["run_id"],
                "step_id": r["step_id"],
                "action_type": r["action_type"],
                "tool": r["tool"],
                "decision": r["decision"],
                "policy_id": r["policy_id"],
                "reason": r["reason"],
            }
            for r in rows
        ]
    }

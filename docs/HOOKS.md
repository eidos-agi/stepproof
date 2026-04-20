# Hook Integration Pseudo-Code

Concrete shapes for the three enforcement points: `PreToolUse`, `complete_step`, and verifier dispatch. These are **pseudo-code**: enough to guide implementation, not tied to a specific language yet.

## 1. `PreToolUse` Adapter (Claude Code)

The Claude Code adapter is a thin hook that forwards candidate actions to the StepProof control plane. Business logic lives server-side.

```typescript
// .claude/hooks/stepproof-pretooluse.ts
import { normalizeAction, callStepProof, renderDeny } from "./stepproof-sdk";

export async function preToolUse(event: ToolUseEvent): Promise<HookResult> {
  const action = normalizeAction({
    actor_type: "worker_agent",
    actor_id: event.session_id,
    human_owner_id: event.user_id,
    tool: event.tool_name,
    action_type: classifyAction(event.tool_name, event.tool_input),
    target_env: inferEnvironment(event.tool_input),
    payload_summary: summarize(event.tool_input),
    run_id: activeRunId(),      // null if no runbook is active
    step_id: currentStepId(),   // null if no runbook is active
  });

  const decision = await callStepProof("/policy/evaluate", action);

  switch (decision.decision) {
    case "allow":
      return { allow: true };

    case "deny":
      return {
        allow: false,
        message: renderDeny(decision),
        // Renders: "Blocked by policy {policy_id}: {reason}. Try {suggested_tool}."
      };

    case "transform":
      return {
        allow: true,
        transform_tool_input: decision.transformed_payload,
      };

    case "require_approval":
      return {
        allow: false,
        message:
          `This action requires human approval. ` +
          `Request filed as ${decision.approval_id}. ` +
          `Check status: stepproof approval view ${decision.approval_id}`,
      };
  }
}
```

Notes:

- `classifyAction` maps tool name + input into normalized action classes (`database.write`, `deploy.production`, `secrets.rotate`, etc.). Start with a simple lookup table; evolve as needed.
- `activeRunId` / `currentStepId` are read from a local `.stepproof/run.json` maintained by the `stepproof run` CLI, or from the control plane keyed by session/PID.
- The hook **never** decides locally. It only adapts. All policy logic is server-side so it can be versioned, replayed, and audited.

## 2. `complete_step` Flow (Control Plane)

The worker signals step completion through the SDK or CLI:

```bash
stepproof step complete s3 \
  --evidence migration_name=20260420_add_connector \
  --evidence staging_db_id=stg-main \
  --evidence deploy_id=dep_456
```

Which POSTs to `/runs/:run_id/steps/:step_id/complete`:

```python
# control_plane/api/step_complete.py

@router.post("/runs/{run_id}/steps/{step_id}/complete")
async def complete_step(
    run_id: UUID,
    step_id: str,
    payload: EvidencePayload,
    actor: AuthedActor = Depends(require_worker),
) -> StepCompletionResult:
    run = await db.get_run(run_id)
    step_template = run.template.step(step_id)

    # 1. Precondition: worker must be on this step
    if run.current_step != step_id:
        raise HTTPException(409, f"Run is on {run.current_step}, not {step_id}")

    # 2. Evidence contract: all required keys must be present
    missing = [k for k in step_template.required_evidence if k not in payload.evidence]
    if missing:
        raise HTTPException(400, f"Missing evidence: {missing}")

    # 3. Record the claim
    step_run = await db.upsert_step_run(
        run_id=run_id,
        step_id=step_id,
        status="awaiting_verification",
        evidence=payload.evidence,
        attempts=lambda prior: (prior or 0) + 1,
    )

    # 4. Dispatch verifier (sync for Tier 1, async for Tier 2/3)
    result = await dispatch_verifier(
        run_id=run_id,
        step_id=step_id,
        method=step_template.verification_method,
        tier=step_template.verification_tier,
        evidence=payload.evidence,
        context={
            "runbook_id": run.template_id,
            "environment": run.environment,
            "owner_id": run.owner_id,
        },
        timeout_seconds=step_template.timeout_seconds,
    )

    # 5. Apply result
    if result.status == "pass":
        await db.update_step_run(run_id, step_id, status="verified",
                                 verification_result=result)
        await db.advance_run(run_id, next_step=step_template.next_id)
        await audit.record("step.verified", run_id, step_id, actor, result)
        return StepCompletionResult(status="verified", next_step=step_template.next_id)

    elif result.status == "fail":
        await db.update_step_run(run_id, step_id, status="failed",
                                 verification_result=result)
        await apply_on_fail(run, step_template, result)
        await audit.record("step.failed", run_id, step_id, actor, result)
        return StepCompletionResult(status="failed", reason=result.reason)

    else:  # inconclusive or timeout
        escalated = await escalate_tier(run, step_template, payload, result)
        return StepCompletionResult(status=escalated.status,
                                    reason=escalated.reason)
```

The key invariants:

- **Evidence contract is enforced at the API boundary.** The verifier never sees partial evidence.
- **The worker cannot mark itself verified.** `status="verified"` is only written after `dispatch_verifier` returns `pass`.
- **Every transition is audited.** `audit.record` is append-only and content-addressed.
- **`apply_on_fail`** implements the runbook's declared failure mode: `block`, `retry`, or `escalate_human`.

## 3. Verifier Dispatch

The verifier fabric is a registry of methods keyed by name, each with a declared tier.

```python
# verifiers/dispatch.py

VERIFIERS: dict[str, Verifier] = {
    "verify_ci_green": Tier1Verifier(verify_ci_green),
    "verify_migration_applied": Tier1Verifier(verify_migration_applied),
    "verify_deploy_succeeded": Tier1Verifier(verify_deploy_succeeded),
    "verify_smoke_logs": Tier2Verifier(prompt="verify_smoke_logs.md"),
    "verify_code_change": Tier2Verifier(prompt="verify_code_change.md"),
    "verify_guardrail_compliance": Tier3Verifier(prompt="verify_guardrail.md"),
}

async def dispatch_verifier(
    *, run_id, step_id, method, tier, evidence, context, timeout_seconds,
) -> VerificationResult:
    verifier = VERIFIERS.get(method)
    if verifier is None:
        return VerificationResult(
            status="fail",
            confidence=1.0,
            reason=f"Unknown verification method: {method}",
        )
    if verifier.tier != tier:
        return VerificationResult(
            status="fail",
            confidence=1.0,
            reason=f"Tier mismatch: runbook says {tier}, method is {verifier.tier}",
        )

    async with timeout(timeout_seconds):
        try:
            result = await verifier.run(evidence=evidence, context=context)
        except TimeoutError:
            return VerificationResult(status="timeout",
                                      reason=f"Verifier exceeded {timeout_seconds}s")

    return normalize_result(result, verifier_id=verifier.id, tier_used=verifier.tier)
```

### Tier 1 verifier (deterministic)

```python
# verifiers/tier1/verify_migration_applied.py

async def verify_migration_applied(evidence: dict, context: dict) -> dict:
    migration = evidence["migration_name"]
    db_id = evidence["staging_db_id"]  # or prod_db_id per step

    async with readonly_db(db_id) as conn:
        count = await conn.scalar(
            "SELECT COUNT(*) FROM schema_migrations WHERE name = $1",
            migration,
        )

    deploy = await deploy_api.get(evidence["deploy_id"])

    if count >= 1 and deploy.status == "SUCCESS":
        return {
            "status": "pass",
            "confidence": 1.0,
            "reason": f"Migration {migration} recorded; deploy {deploy.id} SUCCESS.",
            "artifacts": {"count": count, "deploy_status": deploy.status},
        }
    return {
        "status": "fail",
        "confidence": 1.0,
        "reason": f"count={count}, deploy_status={deploy.status}",
        "artifacts": {"count": count, "deploy_status": deploy.status},
    }
```

### Tier 2 verifier (small model)

The Tier 2 verifier is a separate Claude Agent SDK process with **read-only tools only**. It cannot collude because it has no write capability.

```python
# verifiers/tier2/runner.py

from claude_agent_sdk import Agent, ReadOnlyTools

async def run_tier2(prompt_template: str, evidence: dict, context: dict) -> dict:
    prompt = render_template(prompt_template, evidence=evidence, context=context)

    agent = Agent(
        model="claude-haiku-4-5-20251001",
        tools=ReadOnlyTools(
            git=True,
            ci=True,
            deploy_api=True,
            db_readonly=True,
            logs=True,
        ),
        system=VERIFIER_SYSTEM_PROMPT,
        max_turns=5,
    )

    raw = await agent.run(prompt)
    return parse_json_strict(raw, schema=VERIFICATION_RESULT_SCHEMA)
```

`VERIFIER_SYSTEM_PROMPT` explicitly states:

```
You are a StepProof verifier. You have no write tools. You cannot modify
any system. Your only job is to answer pass / fail / inconclusive on
whether the claimed step was actually completed, based on the evidence
the worker submitted and the real system state you can observe.

You return strict JSON matching this schema. If you cannot decide, return
"inconclusive" — do not guess.
```

## 4. Gate Hooks (PreCommit / PreMerge / PreDeploy)

These are thin shell wrappers that call the same `/policy/evaluate` endpoint with a different `action_type`:

```bash
# .git/hooks/pre-commit
#!/usr/bin/env bash
stepproof gate check \
  --action_type commit \
  --files "$(git diff --cached --name-only)" \
  --branch "$(git branch --show-current)" \
  || { echo "StepProof blocked this commit. Run 'stepproof run status' to see why."; exit 1; }
```

The control plane decides. The hook just enforces.

## Design Principles

1. **Hooks are thin adapters.** Business logic stays in the control plane so it is auditable, versionable, and replayable.
2. **Verify at step-completion boundaries, not mid-execution.** Mid-step blocks degrade worker reasoning; per-step gates preserve flow while preventing silent skips.
3. **Evidence is submitted once, explicitly.** The worker does not implicitly trigger verification by side effect.
4. **Verifiers have no write tools.** Ever. This is the cardinal rule.
5. **All decisions are audited.** Including `allow` decisions — they are the load-bearing record for "we ran this runbook correctly."

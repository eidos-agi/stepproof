# Hook Integration Pseudo-Code

Concrete shapes for the enforcement points. StepProof integrates with Claude Code through its native hook lifecycle; the pseudo-code below follows the idioms documented in [LESSONS_FROM_HOOKS_MASTERY.md](LESSONS_FROM_HOOKS_MASTERY.md) — `uv` single-file scripts, exit-code semantics, JSON over stdin, matchers in `settings.json`.

## 0. Claude Code Hook Contract

Every StepProof adapter is a `uv` single-file Python script invoked by Claude Code:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "python-dotenv"]
# ///
```

**Exit codes are the contract:**

| Exit code | Behavior |
|-----------|----------|
| `0` | Continue. Hook took no position. |
| `2` | Block the tool call. `stderr` is shown to Claude as the denial reason. |
| Any exception | Catch and exit `0`. A crashed hook must not break the session. |

**Registration** in `.claude/settings.json` uses matchers to limit blast radius:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Write|Edit|mcp__stepproof__.*|mcp__cerebro__deploy.*",
        "hooks": [
          {
            "type": "command",
            "command": "uv run $CLAUDE_PROJECT_DIR/.claude/hooks/stepproof_pretooluse.py"
          }
        ]
      }
    ]
  }
}
```

Other enforcement surfaces StepProof uses: `PermissionRequest` (second-chance gate with `updatedInput` transform support), `SubagentStart`/`SubagentStop` (verifier dispatch lifecycle), `PreCompact` (inject runbook state so the worker never forgets which step it's on), `SessionEnd` (mark abandoned runs).

---


## 1. `PreToolUse` Adapter

The Claude Code adapter is a thin `uv` script that forwards candidate actions to the StepProof control plane. Business logic lives server-side. File: `.claude/hooks/stepproof_pretooluse.py`.

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "python-dotenv"]
# ///
"""StepProof PreToolUse adapter. Forwards normalized actions to /policy/evaluate."""
import json, os, sys
from pathlib import Path

def load_active_run() -> dict | None:
    """Read .stepproof/run.json — the active runbook state for this session."""
    path = Path.cwd() / ".stepproof" / "run.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def classify_action(tool_name: str, tool_input: dict) -> str:
    """Map tool name + input to a normalized action class."""
    # Simple lookup to start; evolve as the action taxonomy grows.
    if tool_name == "Bash":
        cmd = tool_input.get("command", "").lstrip()
        if cmd.startswith(("psql", "pg_dump", "pg_restore")):
            return "database.write"
        if cmd.startswith(("cerebro-migrate", "railway deploy", "deploy ")):
            return "deploy.risky"
    if tool_name.startswith("mcp__cerebro__deploy"):
        return "deploy.production"
    if tool_name in ("Write", "Edit"):
        return "filesystem.write"
    return f"tool.{tool_name.lower()}"

def normalize(input_data: dict) -> dict:
    run = load_active_run() or {}
    return {
        "actor_type": "worker_agent",
        "actor_id": input_data.get("session_id"),
        "human_owner_id": os.getenv("STEPPROOF_HUMAN_OWNER", "unknown"),
        "tool": input_data.get("tool_name"),
        "tool_input": input_data.get("tool_input", {}),
        "action_type": classify_action(
            input_data.get("tool_name", ""),
            input_data.get("tool_input", {}),
        ),
        "run_id": run.get("run_id"),
        "step_id": run.get("current_step"),
        "target_env": run.get("environment"),
    }

def call_stepproof(action: dict) -> dict:
    """POST to /policy/evaluate. Degrade gracefully on any failure."""
    import httpx
    url = os.getenv("STEPPROOF_URL", "http://localhost:8787") + "/policy/evaluate"
    try:
        r = httpx.post(url, json=action, timeout=2.0)
        r.raise_for_status()
        return r.json()
    except Exception:
        # Degrade to allow; control-plane outage must not break the session.
        # The audit log records the skipped decision on reconnect.
        return {"decision": "allow", "reason": "stepproof-unreachable", "skipped": True}

def main():
    try:
        input_data = json.load(sys.stdin)
        action = normalize(input_data)
        decision = call_stepproof(action)

        match decision.get("decision"):
            case "allow":
                sys.exit(0)

            case "deny":
                msg = (
                    f"[StepProof {decision.get('policy_id', 'unknown')}] "
                    f"{decision.get('reason', 'blocked')}. "
                    f"Try: {decision.get('suggested_tool', 'see stepproof run status')}"
                )
                print(msg, file=sys.stderr)
                sys.exit(2)

            case "transform":
                # Emit JSON on stdout to rewrite the tool input.
                print(json.dumps({
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "decision": {
                            "behavior": "allow",
                            "updatedInput": decision["transformed_payload"],
                        },
                    }
                }))
                sys.exit(0)

            case "require_approval":
                print(
                    f"Approval required: {decision.get('approval_id')}. "
                    f"Check: stepproof approval view {decision.get('approval_id')}",
                    file=sys.stderr,
                )
                sys.exit(2)

            case _:
                sys.exit(0)

    except Exception:
        # Never break the session. Log locally, exit 0.
        sys.exit(0)

if __name__ == "__main__":
    main()
```

Design notes:

- **The hook never decides locally.** It normalizes the event, calls the control plane, and enforces the returned decision. All policy logic is server-side so it is versioned, replayable, and centrally auditable.
- **`classify_action` is a lookup table to start.** Grow the taxonomy as new action classes emerge. Don't over-engineer classification on day one.
- **Active run state lives at `.stepproof/run.json`** — maintained by `stepproof run start|step complete|run end`. The hook reads it; it doesn't own it.
- **Graceful degradation is mandatory.** If the control plane is down, the hook allows, flags the decision as `skipped`, and the audit buffer catches up on reconnect. A StepProof outage must never strand the worker.

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

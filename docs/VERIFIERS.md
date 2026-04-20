# Verifier Fabric

Verifiers confirm that a step was actually completed against real system state. They are the independent check that makes StepProof more than a checklist.

## Design Principles

1. **Read-only.** Verifiers have no write tools. They surface problems; they do not fix them. This eliminates collusion — a verifier that could quietly patch the problem is no verifier.
2. **Evidence-driven.** Verifiers consume structured evidence submitted by the worker (IDs, refs, hashes). They do not guess.
3. **Machine-decisive.** Verifier output is structured pass/fail with reason, not prose. The governor consumes it automatically.
4. **Tiered by cost.** Start cheap, escalate only when cheap isn't enough.

## Tiers

### Tier 1 — Deterministic Scripts

Default tier. Shell or Python functions that query concrete system state.

**Use for:**
- DB state checks (`SELECT COUNT(*) FROM schema_migrations WHERE name = :n`)
- API status checks (CI, deploy, health endpoints)
- Git queries (branch, commit, diff presence)
- File-system facts

**Cost:** effectively zero.
**Latency:** milliseconds.
**Coverage:** 80–90% of typical checks.

### Tier 2 — Small Verifier Model

Used when evidence is unstructured: logs, diffs, qualitative fit.

**Use for:**
- "Does this diff implement the requirement without unrelated changes?"
- "Do these logs indicate the new connector registered successfully?"
- "Does this PR description match the runbook intent?"

**Model class:** Haiku-tier. Fast, cheap, good enough.
**Cost:** ~$0.001 per check.
**Prompt contract:** model is told it is a read-only verifier, given evidence, and must return JSON `{status, confidence, reason, artifacts}`.

### Tier 3 — Heavy Model

Opt-in per step. Rare, high-stakes checks.

**Use for:**
- "Does this architectural change violate our data-handling guardrails?"
- "Is this runbook compatible with our SOC 2 controls?"

**Cost:** ~$0.02 per check.
**Policy:** runbooks must explicitly opt into Tier 3; default is Tier 1, escalate to Tier 2 when needed.

## Interface Contract

Every verifier — Tier 1, 2, or 3 — implements the same contract.

### Request

```json
{
  "run_id": "run_123",
  "step_id": "s3",
  "method": "verify_migration_applied",
  "tier": "tier1",
  "evidence": {
    "migration_name": "20260420_add_connector",
    "deploy_id": "dep_456",
    "database": "staging-main"
  },
  "context": {
    "runbook_id": "rb-add-connector-fleetio",
    "environment": "staging",
    "owner_id": "daniel"
  }
}
```

### Response

```json
{
  "status": "pass",
  "confidence": 0.99,
  "reason": "Migration row exists in schema_migrations; deploy status is SUCCESS.",
  "artifacts": {
    "query_result": { "count": 1 },
    "deploy_status": "SUCCESS",
    "deploy_url": "https://deploy.example.com/dep_456"
  },
  "verifier_id": "verifier-migration-staging-v1",
  "tier_used": "tier1",
  "latency_ms": 84
}
```

Status values: `pass`, `fail`, `inconclusive`, `timeout`.

`inconclusive` triggers automatic escalation to the next tier (unless the step opts out of escalation). `timeout` is treated as `fail` by default.

## Tier 1 Examples

### `verify_ci_green`

```python
def verify_ci_green(evidence, context):
    run = ci_api.get_run(evidence["ci_run_id"])
    if run.status == "SUCCESS":
        return {
            "status": "pass",
            "confidence": 1.0,
            "reason": f"CI run {run.id} succeeded",
            "artifacts": {"status": run.status, "url": run.url},
        }
    return {
        "status": "fail",
        "confidence": 1.0,
        "reason": f"CI run {run.id} status is {run.status}",
        "artifacts": {"status": run.status, "url": run.url},
    }
```

### `verify_migration_applied`

```python
def verify_migration_applied(evidence, context):
    with readonly_db(evidence["database"]) as conn:
        count = conn.query_scalar(
            "SELECT COUNT(*) FROM schema_migrations WHERE name = %s",
            [evidence["migration_name"]],
        )
    deploy = deploy_api.get(evidence["deploy_id"])

    if count >= 1 and deploy.status == "SUCCESS":
        return {"status": "pass", "confidence": 1.0, "reason": "Migration recorded; deploy succeeded."}
    return {
        "status": "fail",
        "confidence": 1.0,
        "reason": f"schema_migrations count={count}, deploy status={deploy.status}",
    }
```

## Tier 2 Prompt Template

```
System:
You are a StepProof verifier. You are read-only. You cannot modify any
system. Your only job is to determine whether the claimed step was
actually completed, based on evidence.

Return strict JSON:
{"status": "pass" | "fail" | "inconclusive",
 "confidence": 0.0-1.0,
 "reason": "<one sentence>"}

User:
Runbook: {runbook_id}
Step: {step_id} — {step_description}
Requirement: {step_requirement}

Evidence submitted by worker:
{evidence_block}

Relevant system output:
{unstructured_output_block}

Question:
Did the worker satisfy the requirement for this step, based on the
evidence and system output? Answer pass, fail, or inconclusive.
```

## Anti-Patterns

- **Giving verifiers write access.** This is the cardinal sin. A verifier that can act is not a verifier.
- **Accepting free-text evidence.** "I ran the migration" is not evidence. `migration_name` + `deploy_id` is.
- **Using Tier 3 as a default.** Heavy models are slow, expensive, and unnecessary for the vast majority of checks.
- **Blocking mid-step.** Verify at step-completion boundaries, not mid-execution. Mid-step blocks degrade worker reasoning.
- **Silent pass on missing evidence.** If required evidence is absent, the verifier must `fail`, not `inconclusive`. Missing evidence is a contract violation.

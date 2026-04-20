# StepProof Architecture

> Verification-aware runbooks with worker, verifier, and hook-level governance.

## 1. Problem

Agent-operated production systems have a recurring failure mode: the agent has the tools and the instructions to do things correctly, yet routinely bypasses its own process. Raw `psql` instead of sanctioned migrations. Ad-hoc scripts instead of the daemon. Guessed env vars instead of topology lookups. Debugging symptoms instead of reading the runbook.

All current controls — docs, instructions, `CLAUDE.md`, MCP server guidance, memory — are **advisory**. Hooks can block individual commands but have no concept of **process compliance**.

StepProof treats process compliance as a first-class runtime property, not a guideline. A worker cannot advance a workflow until an independent verifier confirms the current step against real system state.

This aligns with the 2026 consensus on agent governance: verifiable execution, adversarial verification, and gateway-level enforcement.

## 2. Roles

Three explicit roles, no trust between them.

### Worker Agent
- **Tools:** code editing, sanctioned migration tooling, deploy CLI, DB access through approved interfaces.
- **Responsibilities:** execute runbook steps, produce required evidence.
- **Limits:** cannot mark a step verified; cannot override governor decisions.

### Verifier Agent
- **Tools:** read-only git, CI status, deployment APIs, read-only DB, logs, topology.
- **Responsibilities:** given `(runbook_id, step_id, evidence)`, decide pass/fail.
- **Limits:** no write tools. It surfaces problems, it does not fix them.

### Governor (Hook / Policy Layer)
- Lives outside both agents.
- Integrates at `PreToolUse`, step completion, `PreCommit` / `PreMerge` / `PreDeploy`.
- Enforces that a runbook is active, the worker is on the expected step, and prior steps are verified.
- Emits append-only audit records for every decision.

## 3. Verification-Aware Runbooks

Runbooks are first-class objects. Each step declares both what "done" means and how it will be verified.

```jsonc
{
  "runbook_id": "rb-add-connector-fleetio",
  "name": "Add new connector to service X",
  "risk_level": "medium",
  "allowed_environments": ["staging", "production"],
  "steps": [
    {
      "step_id": "s1",
      "description": "Implement connector behind feature flag",
      "required_evidence": ["branch_name", "diff_ref"],
      "verification_method": "verify_code_change",
      "verification_tier": "tier2",
      "allowed_tools": ["editor", "git", "tests"]
    },
    {
      "step_id": "s2",
      "description": "CI tests green on PR",
      "required_evidence": ["ci_run_id"],
      "verification_method": "verify_ci_green",
      "verification_tier": "tier1",
      "allowed_tools": ["tests", "ci_cli"]
    },
    {
      "step_id": "s3",
      "description": "Apply DB migration to staging",
      "required_evidence": ["migration_name", "staging_db_id", "deploy_id"],
      "verification_method": "verify_migration_staging",
      "verification_tier": "tier1",
      "allowed_tools": ["cerebro_migrate_staging", "deploy_cli"]
    }
  ]
}
```

Full schema: [RUNBOOKS.md](RUNBOOKS.md).

## 4. Verification Tiers

| Tier | Mechanism | Cost | Example |
|------|-----------|------|---------|
| **1** | Deterministic script | ~$0 | `SELECT COUNT(*) FROM schema_migrations WHERE name = :n` |
| **2** | Small LLM (Haiku-class) | ~$0.001/check | "Did this diff implement the requirement without unrelated changes?" |
| **3** | Heavy LLM, opt-in only | ~$0.02/check | "Does this architectural change violate our data-handling guardrails?" |

Runbooks default to Tier 1. They escalate to Tier 2 when evidence is unstructured (logs, diffs). Tier 3 requires explicit opt-in per step.

Full details: [VERIFIERS.md](VERIFIERS.md).

## 5. Governance, Identity, and Audit

Every action is identity-scoped and audited.

```json
{
  "actor_type": "worker_agent",
  "actor_id": "claude-worker-17",
  "human_owner_id": "daniel",
  "run_id": "run_123",
  "step_id": "s3",
  "action_type": "database.write",
  "tool": "psql",
  "target_env": "staging",
  "payload_summary": "apply migration 20260420_add_connector"
}
```

Policy examples (see [POLICY.md](POLICY.md)):

- Deny `database.write` when a sanctioned wrapper exists (`cerebro-migrate`).
- Deny `deploy.production` unless prior steps are verified.
- If a verifier fails twice, block further risky tools and require human approval.
- Certain runbook types require human sign-off even after a verifier pass.

The audit log can answer, for any change: which runbook, which step, which worker, which verifier, what evidence, which policies, what decision.

## 6. Hook Integration

### `PreToolUse` (risky tools)
1. Resolve owner, agent, runbook, step.
2. If no runbook is active → deny with suggestion.
3. If tool is not allowed at current step → deny with explanation.
4. If prior required steps are not verified → deny until verification.

### Step completion
1. Worker calls `complete_step(run_id, step_id, evidence)`.
2. Governor spawns verifier with narrow prompt and evidence.
3. On pass: unlock next step's tool set.
4. On fail / timeout: block risky tools; attach verifier's explanation.

### `PreCommit` / `PreMerge` / `PreDeploy`
- Final gates. Confirm all required steps completed and verified.
- Optional human sign-off for high-risk runbooks.

## 7. End-to-End Example

"Add new connector + migration + prod deploy":

1. Human starts `rb-add-connector-fleetio`.
2. **s1** — worker writes code, opens PR. Verifier (T2) checks diff matches requirement.
3. **s2** — tests run. Verifier (T1) checks CI status == SUCCESS.
4. **s3** — worker attempts raw `psql`. `PreToolUse` denies: "Use `cerebro-migrate-staging` at this step." Worker uses sanctioned tool; records migration + deploy IDs. Verifier (T1) queries `schema_migrations` and deploy status.
5. **s4** — prod deploy. Gate ensures s1–s3 verified. Verifier (T2) checks post-deploy logs for expected connector registry entry.
6. `PreMerge` confirms all verified, optionally routes to human.
7. Audit log retains the entire causal chain.

## 8. Why This Generalizes

The architecture is domain-neutral. It works anywhere you have:

- A workflow with discrete steps.
- Steps whose completion is verifiable against concrete system state.
- Risky actions that benefit from policy gating.
- A need for auditable attribution.

See [ROADMAP.md](ROADMAP.md) for the MVP sequence and expansion plan.

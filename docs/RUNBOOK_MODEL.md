# Runbook Model

Runbooks are first-class, verification-aware objects. Every step declares what "done" means and how it will be checked.

## Core Objects

### `RunbookTemplate`

The blueprint. Versioned, immutable once published.

| Field | Type | Description |
|-------|------|-------------|
| `template_id` | string | Stable identifier, e.g. `rb-add-connector-fleetio` |
| `version` | semver | Template version |
| `name` | string | Human-readable name |
| `description` | string | Why this runbook exists |
| `risk_level` | enum | `low` \| `medium` \| `high` \| `critical` |
| `allowed_environments` | string[] | Which envs this runbook can target |
| `requires_human_signoff` | bool | Gate final merge/deploy on human approval |
| `steps` | `StepTemplate[]` | Ordered sequence |

### `StepTemplate`

| Field | Type | Description |
|-------|------|-------------|
| `step_id` | string | Stable within template (e.g. `s3`) |
| `description` | string | What the worker is doing |
| `allowed_tools` | string[] | Tool names permitted while on this step |
| `denied_tools` | string[] | Explicit deny list (overrides allow) |
| `required_evidence` | string[] | Keys the worker must submit at completion |
| `verification_method` | string | Verifier function/template name |
| `verification_tier` | enum | `tier1` \| `tier2` \| `tier3` |
| `timeout_seconds` | int | Max time before step auto-fails |
| `on_fail` | enum | `block` \| `retry` \| `escalate_human` |
| `on_fail_max_retries` | int | Retry budget before escalation |

### `WorkflowRun`

A live instance of a template.

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | uuid | Instance identifier |
| `template_id` | string | Source template |
| `template_version` | semver | Pinned at start |
| `owner_id` | string | Human sponsor |
| `agent_id` | string | Worker agent instance |
| `environment` | string | Target env |
| `current_step` | string | Active step ID |
| `status` | enum | `active` \| `blocked` \| `completed` \| `failed` \| `abandoned` |
| `started_at` | timestamp | |
| `ended_at` | timestamp \| null | |

### `StepRun`

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | uuid | Parent workflow |
| `step_id` | string | Template step |
| `status` | enum | `pending` \| `in_progress` \| `awaiting_verification` \| `verified` \| `failed` \| `blocked` |
| `evidence` | map | Key/value payload submitted by worker |
| `verification_result` | `VerificationResult` \| null | |
| `attempts` | int | Retry counter |

## Example: DB Migration + Deploy

```yaml
template_id: rb-db-migration-and-deploy
version: 1.0.0
name: Apply DB migration and deploy service
risk_level: high
allowed_environments: [staging, production]
requires_human_signoff: true

steps:
  - step_id: s1
    description: Author migration file and open PR
    allowed_tools: [editor, git]
    required_evidence: [branch_name, pr_url]
    verification_method: verify_pr_opened
    verification_tier: tier1
    timeout_seconds: 3600
    on_fail: retry
    on_fail_max_retries: 2

  - step_id: s2
    description: CI tests pass on PR
    allowed_tools: [ci_cli]
    required_evidence: [ci_run_id]
    verification_method: verify_ci_green
    verification_tier: tier1
    timeout_seconds: 1800
    on_fail: block

  - step_id: s3
    description: Apply migration to staging
    allowed_tools: [cerebro_migrate_staging]
    denied_tools: [psql, pg_dump, pg_restore]
    required_evidence: [migration_name, staging_db_id, deploy_id]
    verification_method: verify_migration_applied
    verification_tier: tier1
    timeout_seconds: 600
    on_fail: escalate_human

  - step_id: s4
    description: Smoke-test staging
    allowed_tools: [http_probe, log_reader]
    required_evidence: [smoke_run_id]
    verification_method: verify_smoke_logs
    verification_tier: tier2
    timeout_seconds: 900
    on_fail: block

  - step_id: s5
    description: Apply migration to production
    allowed_tools: [cerebro_migrate_production]
    denied_tools: [psql, pg_dump, pg_restore]
    required_evidence: [migration_name, prod_db_id, deploy_id]
    verification_method: verify_migration_applied
    verification_tier: tier1
    timeout_seconds: 600
    on_fail: escalate_human

  - step_id: s6
    description: Deploy service to production
    allowed_tools: [deploy_cli]
    required_evidence: [deploy_id]
    verification_method: verify_deploy_and_health
    verification_tier: tier2
    timeout_seconds: 900
    on_fail: escalate_human
```

## Authoring Guidelines

1. **Every step must be independently verifiable.** If you can't write a verifier for it, split the step or reconsider whether it belongs in an enforced runbook.
2. **Prefer Tier 1 verification.** Escalate to Tier 2 only when evidence is unstructured. Tier 3 is opt-in per step.
3. **Deny sanctioned-bypass tools explicitly.** If `cerebro-migrate` exists, deny raw `psql` at migration steps.
4. **Require concrete evidence.** `migration_name` + `deploy_id` beats a free-text "done". Evidence is what the verifier consumes.
5. **Set realistic timeouts.** A step that blocks for hours is a hole in the governance layer.
6. **Mark high-risk runbooks `requires_human_signoff: true`.** Verifiers are a guard, not a replacement for human accountability on destructive or regulated operations.

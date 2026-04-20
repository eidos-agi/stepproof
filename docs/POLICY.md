# Policy Engine

StepProof's governor intercepts every risky action and makes a deterministic decision: **allow, deny, transform, or require approval.**

This follows the 2026 pattern for agent governance: a stateless policy engine sitting in front of execution, with sub-millisecond overhead for common cases.

## Decision Model

Every candidate action is normalized into a policy event:

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
  "payload_summary": "apply migration 20260420_add_connector",
  "timestamp": "2026-04-20T15:30:00Z"
}
```

The engine returns:

```json
{
  "decision": "deny",
  "reason": "Tool psql is denied at step s3. Use cerebro-migrate-staging instead.",
  "policy_id": "pol-prefer-sanctioned-migration-tool",
  "suggested_tool": "cerebro-migrate-staging",
  "requires_human_approval": false
}
```

Possible decisions:

| Decision | Meaning |
|----------|---------|
| `allow` | Execute as-is |
| `deny` | Block; surface reason and suggested alternative |
| `transform` | Rewrite the action (e.g., enforce dry-run flag) |
| `require_approval` | Pause; route to human; resume on approval |
| `audit` | Log and continue. Pure observability — no enforcement. Used for shadow-mode rules and rules that are too new to enforce. |

### Shadow mode

Policies and runbooks may be marked `shadow: true`. Shadow rules evaluate normally and write full decision records to the audit log, but the `decision` field returned to the adapter is always `allow` regardless of what the rule concluded. This lets operators:

- Author new rules and measure their impact before turning them on.
- Tune noisy rules into quiet ones by reviewing would-have-blocked events.
- Promote rules from `shadow: true` to `shadow: false` once they've proven themselves.

Shadow mode is the safe on-ramp for new policy. See [ADR 0001](adr/0001-deterministic-policy-evaluation.md) for why open-text LLM review of shadow-mode findings happens outside the enforcement path.

### Execution rings

Before any rule evaluates, the governor classifies the action into one of four execution rings (Ring 0 sandbox through Ring 3 production-facing). Ring 0 actions skip policy entirely. Rings 1–3 require an active runbook; Ring 3 additionally consults trust state and approval requirements. See [ADR 0002](adr/0002-four-execution-rings.md) for the full ring model.

## Rule Language

Rules are expressed as policy-as-code. StepProof supports two backends out of the box:

- **OPA / Rego** — industry standard for workflow and agent governance.
- **Cedar** — AWS-originated, strong typing, good for authorization-style rules.

Either is optional. The MVP ships a simple YAML rule set evaluated by a built-in engine, with OPA/Cedar as drop-in replacements.

### Example Rules (YAML MVP)

```yaml
rules:
  - id: pol-runbook-required-for-risky-actions
    when:
      action_type_in: [database.write, deploy.production, secrets.rotate]
      run_id_missing: true
    decision: deny
    reason: "Risky action requires an active runbook. Start one with `stepproof run start <template>`."

  - id: pol-tool-allowed-for-step
    when:
      run_id_present: true
      tool_not_in_allowed_tools: true
    decision: deny
    reason: "Tool {{tool}} is not allowed at step {{step_id}}. Allowed: {{allowed_tools}}."

  - id: pol-prior-steps-verified
    when:
      run_id_present: true
      prior_required_steps_unverified: true
    decision: deny
    reason: "Prior required steps are not verified. Unverified: {{unverified_steps}}."

  - id: pol-prefer-sanctioned-migration-tool
    when:
      tool_in: [psql, pg_dump, pg_restore]
      target_env_in: [staging, production]
      step_has_sanctioned_alternative: true
    decision: deny
    reason: "Use sanctioned migration tool {{sanctioned_tool}} instead of raw {{tool}}."

  - id: pol-prod-deploy-requires-human-signoff
    when:
      action_type: deploy.production
      runbook_requires_human_signoff: true
    decision: require_approval
    reason: "Production deploy on high-risk runbook requires human approval."

  - id: pol-repeated-verifier-failure-escalates
    when:
      current_step_verification_failures_gte: 2
    decision: require_approval
    reason: "Step has failed verification twice. Escalating to human."
```

## Hook Integration Points

The policy engine is invoked from multiple hook types. Each is a thin integration; policy logic lives in one place.

### `PreToolUse` (Claude Code)
- Invoked before every tool call.
- Governor decides allow/deny/transform.
- Denied calls return a message to the agent explaining why and what to try instead.

### `PreCommit` / `PreMerge` (Git hooks, CI gates)
- Invoked before commits or merges affecting tracked paths.
- Confirms all required runbook steps are verified.
- Optionally routes to human approval.

### `PreDeploy` (CI/CD, deploy CLI wrappers)
- Invoked before production deploys.
- Confirms topology match, prior-step verification, and human sign-off if required.

### `PostStepCompletion` (explicit worker signal)
- Worker submits evidence.
- Governor dispatches verifier, records result, and unlocks subsequent steps on pass.

## Audit Log

Every decision — allow, deny, transform, approve — is appended to a tamper-evident log. Schema:

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | uuid | Append-only identifier |
| `timestamp` | timestamp | |
| `actor_type` | string | `worker_agent` \| `verifier_agent` \| `human` \| `system` |
| `actor_id` | string | Specific identity |
| `human_owner_id` | string | Sponsor |
| `run_id` | uuid \| null | |
| `step_id` | string \| null | |
| `action_type` | string | Normalized action class |
| `tool` | string \| null | |
| `decision` | enum | |
| `policy_id` | string | Which rule fired |
| `reason` | string | Human-readable |
| `payload_hash` | sha256 | Content-addressed payload reference |

The log is append-only, hashed, and queryable. For any change in the system, you can trace back to runbook, step, agents, evidence, policies, and decisions.

## Policy Authoring Guidelines

1. **Deny by default on new action classes.** Add explicit allow rules rather than leaving holes.
2. **Every deny rule must include a suggested path forward.** Workers need to know what to do instead.
3. **Prefer deterministic conditions over model-based ones.** The policy engine is a gate, not an oracle. See [ADR 0001](adr/0001-deterministic-policy-evaluation.md).
4. **Escalate, don't just block, on repeated failure.** A worker retrying the same denied action is a signal the runbook is wrong — involve a human.
5. **Version your policies.** Record which rule set was active at decision time for audit replay.
6. **New rules ship `shadow: true` first.** Only promote to enforcement after audit-log review confirms the rule fires when expected and stays quiet otherwise.
7. **Classify actions by ring, not just name.** Every new action class gets a ring assignment per [ADR 0002](adr/0002-four-execution-rings.md). Unclassified actions default to Ring 3 — conservative by design, surfaces gaps quickly.
8. **Do not conflate identity, authority, and liveness.** The enforcement gate checks all three independently per [ADR 0003](adr/0003-three-property-trust.md); policies consume the booleans, not a merged score.

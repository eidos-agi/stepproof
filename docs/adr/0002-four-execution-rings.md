# ADR 0002: Four execution rings for runtime privilege

- **Status:** accepted
- **Date:** 2026-04-20

## Context

The initial StepProof design used `allowed_tools` and `denied_tools` per step as the primary privilege mechanism. This works but has limits:

- It requires every runbook to re-declare what's allowed, even for routine patterns (read-only ops, reversible writes, etc.).
- It doesn't encode **blast radius** — the expected reversibility and scope of impact of an action.
- It couples runbook authorship tightly to action-taxonomy knowledge. Authors have to know every tool name that should be allowed or denied.
- It makes defaults brittle. A new tool is unlisted → unknown → either over-permissive (default allow) or breaks flows (default deny).

A coarser-grained layer *beneath* the per-step allow/deny gives us sensible defaults, safer unknowns, and a natural place for trust-based escalation.

## Decision

Every action class maps to one of **four execution rings**, describing its blast radius:

| Ring | Name | Blast Radius | Default Policy |
|------|------|--------------|----------------|
| **0** | Sandbox / Read-only | No side effects observable outside the session. | Always allowed. No runbook required. |
| **1** | Reversible writes, non-prod | Creates or modifies local/dev state. Easily undone. | Runbook required. No verifier gate between steps. |
| **2** | Non-reversible writes, non-prod | Staging/test systems, external services in non-prod mode. | Runbook required. Verifier gate between steps. |
| **3** | Production-facing | Production data, production deploys, production secrets, external systems at full scope. | Runbook + verifier + trust threshold + optional human approval. |

**Ring is an attribute of the action class**, not the runbook. Every action-class definition declares its ring. The policy engine checks ring first, then step-level `allowed_tools`:

1. **Ring 0** — no active runbook required; no policy check needed beyond rate limits and audit.
2. **Rings 1–3** — require an active runbook. Ring 3 additionally checks trust thresholds and (per runbook) approval requirements.
3. Step-level `allowed_tools` and `denied_tools` provide finer-grained overrides within the ring.

**Rings are enforced, not advisory.** The policy engine denies Ring 3 actions without an active runbook regardless of what step `allowed_tools` says — because a Ring 3 action *needs* a runbook by definition.

RBAC still exists for human-facing administration (who can author runbooks, who can approve, who can tune policies). Rings are the runtime mechanism for *what the agent can do right now*.

## Consequences

**Benefits:**

- Sensible defaults for unknown tools. A new MCP tool with no explicit classification lands in Ring 2 or Ring 3 by default (conservative), surfacing as a denied action and forcing explicit classification.
- Runbook authors don't have to enumerate every read-only tool. Ring 0 is always allowed.
- Graduated escalation becomes explicit: Ring 3 + low trust score → require approval; Ring 3 + unverified prior step → deny regardless of trust.
- Policy explanations become simpler: "This is Ring 3, you're at trust score 400, threshold is 600, so approval is required."
- Breach detection becomes easier: unexpected Ring 3 activity is a louder signal than per-tool anomalies.

**Tradeoffs:**

- Rings are coarser than full role modeling. Fine-grained authorization still requires step-level `allowed_tools` / `denied_tools` and, for some cases, capability scopes layered on top.
- Classifying every action into a ring is upfront work. The default is conservative (unclassified → Ring 3), which surfaces gaps quickly but may slow initial rollout.

## Follow-up Work

- A public `RING_TAXONOMY.md` documenting every built-in action class and its ring assignment.
- Per-organization ring overrides (some orgs may classify actions more strictly).
- Ring-based rate limits: Ring 3 capped at N/hour per worker, etc.

## Reference Implementations

- [microsoft/agent-governance-toolkit ADR 0002](https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/adr/0002-use-four-execution-rings-for-runtime-privilege.md) — same model, validated in production at Microsoft.

# ADR 0003: Three-property agent trust (identity / authority / liveness)

- **Status:** accepted
- **Date:** 2026-04-20

## Context

The initial POLICY.md sketched a continuous trust score (0–1000) with behavioral decay — inspired by the Microsoft toolkit's trust model. On deeper reading of their ADR 0005, a cleaner decomposition emerges that avoids a significant failure mode.

A single trust score conflates things that change on completely different timelines:

- **Who the agent is** (cryptographic identity) changes approximately never.
- **What the agent may do** (delegation / runbook scope) changes per workflow, per session.
- **Whether the agent is alive right now** changes per minute.

When you collapse all three into one score, you create a **ghost-agent failure mode**: a worker with a high base trust score can crash, be replaced by an impostor, or silently drop its session — and a score-with-decay model takes time to catch up. Meanwhile, any action taken during that window is authorized by the stale score.

## Decision

Decompose agent trust into three independent properties, each with its own lifecycle:

| Property | What it proves | Typical decay | Recovery path |
|----------|---------------|---------------|---------------|
| **Identity** | Who the agent is (e.g., DID + Ed25519, or session cryptographic attestation in MVP) | Very slow — compromise only | Re-registration with new credentials |
| **Authority** | What the agent may do (active runbook, step, scope) | Medium — runbook ends, approval expires | Open a new runbook; re-request approval |
| **Liveness** | Whether the agent is operationally alive right now | Rapid — seconds to minutes | Heartbeat resumption |

**All three must hold** for a risky action to proceed:

```
can_execute = identity_valid AND authority_valid AND liveness_active
```

Liveness is a **gate, not a score modifier.** A highly-trusted agent that has stopped heartbeating cannot exercise authority just because its base reputation is high. This eliminates the ghost-agent failure mode.

### Behavioral trust signals

Separately from the three hard properties, StepProof tracks **behavioral signals** as an input to policy (not a replacement for the hard gates):

- Verifier pass rate over recent steps.
- Denied-action attempts (signal of trying to bypass).
- Self-correction on denial (did the worker heed the suggested tool and move on?).

These feed into policies like "require human approval for Ring 3 if recent denial rate > threshold." They do **not** unlock gates that identity/authority/liveness have closed.

### Heartbeat protocol (MVP shape)

- Worker registers liveness with a TTL (default: 300 seconds) on runbook start.
- Worker refreshes at `TTL / 2` (150s default). Piggyback on existing control-plane calls where possible to avoid extra round-trips.
- Heartbeat payload includes a hash of the current `(run_id, step_id)` binding — so a worker claiming liveness for a runbook it was never assigned is rejected.
- **Active** (within TTL): full authority.
- **Suspended** (past TTL, within 2×TTL): authority frozen, not revoked. Reversible.
- **Expired** (past 2×TTL): runbook marked `abandoned`, authority dormant, delegation requires re-issue.

### Backward compatibility

Workers that do not register a heartbeat are treated as `liveness_unknown`:

- **Enforcement mode** (default for production runbooks): `liveness_unknown` blocks Ring 2/3 actions.
- **Legacy mode** (opt-in per runbook): `liveness_unknown` permitted. Used during migration.

## Consequences

**Benefits:**

- Ghost agents cannot exercise authority during downtime, regardless of accumulated trust. Hard gate.
- Operators have independent knobs for identity, authority, liveness — each tunable per context.
- Suspension semantics support rapid recovery from transient failures (restarts, network partitions) without principal re-delegation.
- The policy engine gets cleaner inputs: three booleans + behavioral signals, not one fuzzy score.

**Tradeoffs:**

- Stricter defaults require operators to opt into `legacy_mode` during migration. This is intentional — the ghost-agent gap is a security issue.
- Adds per-worker heartbeat state to the control plane. For deployments with many concurrent workers, this needs a real storage backend (Postgres row or Redis, not in-memory).
- Workers behind NAT or hostile firewalls that cannot reach the control plane for heartbeats will show as `liveness_unknown`. Solutions: legacy mode, or heartbeat relay.

## Follow-up Work

- Cross-organization trust propagation for federated StepProof deployments.
- Orphan detection: workers that are both `unreachable` (no liveness) and `unowned` (sponsor revoked / left) should auto-decommission.
- Consider Ed25519 key-based identity as opt-in for high-assurance deployments (matches Microsoft toolkit and IATP).

## Reference Implementations

- [microsoft/agent-governance-toolkit ADR 0005](https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/adr/0005-add-liveness-attestation-to-trust-handshake.md) — three-property decomposition with liveness as a gate.
- [AgentNexus ADR-014](https://github.com/kevinkaylie/AgentNexus/blob/main/docs/adr/014-governance-trust-network.md) — three-dimensional trust scoring with independent decay timelines (referenced by Microsoft's ADR).
- SIP REGISTER — TTL-based heartbeat pattern, production-proven at telecom scale.

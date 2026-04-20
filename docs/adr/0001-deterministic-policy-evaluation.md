# ADR 0001: Deterministic policy evaluation, no LLM in the enforcement loop

- **Status:** accepted
- **Date:** 2026-04-20

## Context

StepProof intercepts every risky action before execution. If the enforcement decision itself depends on an LLM call, three problems follow:

1. **Latency.** LLM inference adds tens to hundreds of milliseconds per decision. Applied to every tool call, this is prohibitive.
2. **Non-determinism.** The same input can produce different outputs depending on model version, temperature, prompt phrasing. Audit replay becomes impossible.
3. **Availability coupling.** An LLM outage — provider rate limit, model deprecation, network blip — becomes a StepProof outage. The graceful-degradation rule from [LESSONS_FROM_HOOKS_MASTERY.md](../LESSONS_FROM_HOOKS_MASTERY.md) already commits us to never breaking the session; that guarantee is much harder to uphold if the enforcement path is LLM-bound.

The three-tier verifier model (Tier 1 scripts / Tier 2 small model / Tier 3 heavy model) exists to manage cost and judgment-calls at **step-completion boundaries**, not at the per-action enforcement gate.

## Decision

Policy evaluation at the enforcement layer — the `PreToolUse` gate — is **deterministic**. It uses declarative rules (YAML by default, OPA Rego or Cedar as drop-in backends) evaluated by a stateless engine with sub-millisecond target latency.

**LLM reasoning lives outside the enforcement path:**

- Inside the **worker** — where Opus/Sonnet do their normal job.
- Inside **Tier 2/3 verifiers** — which run at *step-completion* boundaries, not per-tool, and consume structured evidence.
- Inside **runbook authoring** — a `runbook-author` meta-agent helps humans draft new runbooks and policies.
- Inside **shadow-mode review** — humans or LLMs audit shadow-mode logs to tune rules before promoting them to enforcement.

LLM output never directly produces an `allow` or `deny` decision at runtime.

## Consequences

**Benefits:**

- Decisions are reproducible. Given the same `(input, data_bundle)`, evaluation is deterministic — audit replay works, tests are stable.
- Sub-millisecond decisions are achievable, making per-tool-call enforcement viable.
- Provider outages (Anthropic, OpenAI, local inference) do not disable enforcement.
- Policies are readable artifacts that security reviewers and compliance auditors can inspect without running a model.

**Tradeoffs:**

- Nuanced judgment (e.g., "is this diff the correct implementation of the feature?") happens at step-completion via Tier 2/3 verifiers, not at per-tool enforcement. This is a feature, not a limitation — blocking mid-step degrades worker reasoning quality.
- Rule authors must translate intent into declarative form. The `runbook-author` subagent (outside the enforcement loop) helps with this.
- Novel failure modes that don't match any declarative rule pass through. Shadow-mode analysis and behavioral telemetry surface these for rule updates.

## Reference Implementations

- [microsoft/agent-governance-toolkit ADR 0004](https://github.com/microsoft/agent-governance-toolkit/blob/main/docs/adr/0004-keep-policy-evaluation-deterministic.md) — same argument, same conclusion.
- [OPA philosophy](https://www.openpolicyagent.org/docs/latest/philosophy/) — "specify declaratively, update at any time without recompiling or redeploying, and enforce automatically."

# Prior Art

StepProof stands on a growing body of 2026 work in agent governance, verifiable execution, and policy-as-code. This document catalogs what exists, what StepProof reuses, and where StepProof is genuinely new.

## What Already Exists

### Hook + validator patterns for coding agents

- **[claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery)** — documents two-agent pairing where a validator increases trust that work was delivered correctly. Shares the worker/verifier split with StepProof.
- **Builder-validator pattern** — recognized Claude Code pattern where a validator has read access but no write access, so it cannot "collude" by quietly patching the problem away. StepProof codifies this rule as **verifiers have no write tools, ever.**
- **Claude Code internal verifier-agent prompts** — there is a prompt pattern described as "a dedicated agent whose job is to TRY TO BREAK the implementation." Similar spirit; StepProof generalizes beyond code to infrastructure actions.

### Agent governance platforms

- **[Microsoft Agent Governance Toolkit](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)** (April 2026, open source) — runtime security for AI agents: stateless policy engine intercepting actions with sub-millisecond overhead. StepProof's policy-engine design follows the same pattern.
- **Agent gateways** (Agat, Strata, others) — inline action interception at the infrastructure boundary. StepProof is the developer-experience version of this, with runbook semantics layered on top.
- **[Governance-as-a-Service framework](https://arxiv.org/html/2508.18765v2)** — adversarial multi-agent compliance with trust scores that escalate enforcement for repeat offenders. Informs StepProof's "fail twice → escalate to human" policy pattern.

### Durable workflow engines

- **[Cloudflare Workflows v2](https://blog.cloudflare.com/workflows-v2/)** — durable, replay-safe multi-step agent workflows. The design principle "business logic in the workflow definition, side effects in activities" is directly applicable.
- **Temporal, Inngest, Restate** — mature durable execution runtimes. StepProof does not rebuild these; the roadmap assumes durable execution is a dependency, not a product line.

### Policy-as-code

- **[Open Policy Agent (OPA) / Rego](https://www.openpolicyagent.org/)** — industry standard for declarative policy. StepProof supports OPA as a drop-in backend for its policy engine.
- **[Cedar](https://www.cedarpolicy.com/)** — AWS-originated policy language, strongly typed, well-suited to authorization-style rules. Also supported as a backend.

### Verification-aware planning (research)

- **[Verification-Aware Planning](https://aclanthology.org/2026.eacl-long.353.pdf)** (EACL 2026) — formalizes the pattern of plans that include verification steps and evidence up front, rather than bolting verification on afterward. StepProof's runbook schema (`required_evidence`, `verification_method`, `verification_tier` per step) is a direct implementation of this.
- **[Multi-agent self-verification](https://pub.towardsai.net/how-multi-agent-self-verification-actually-works-and-why-it-changes-everything-for-production-ai-71923df63d01)** — production pattern where agents demand execution evidence, not just static reasoning. Informs StepProof's "structured evidence or it didn't happen" rule.

### Adjacent categories (not direct prior art)

- **Guardrails AI, NeMo Guardrails** — check agent *outputs*, not *process compliance*. Different problem.
- **Braintrust, LangSmith** — *post-hoc* evaluation and scoring. StepProof enforces *during* execution.
- **CrewAI, AutoGen** — multi-agent *collaboration*. StepProof is multi-agent *adversarial verification*.

## What's Genuinely New in StepProof

The pieces exist in 2026. StepProof's contribution is the specific wiring:

1. **Runbook-step-scoped policy enforcement.** Most governance toolkits operate at the tool or API-call granularity. StepProof operates at the **runbook step** level, preserving agent reasoning flow while still preventing silent skips. Mid-step blocking degrades worker quality; step-boundary gates do not.
2. **Explicit evidence contract at the API boundary.** Verifiers consume structured evidence submitted by the worker, not free-text. Missing evidence is a contract violation, not a judgment call.
3. **Three-tier verification with explicit opt-in.** Default to deterministic scripts, escalate to small model when evidence is unstructured, require explicit runbook-level opt-in for heavy models. Keeps cost predictable.
4. **Read-only verifier rule, enforced at the tool layer.** The verifier agent's SDK instance is constructed with read-only tool sets. It is structurally incapable of "fixing" the problem it was asked to verify.
5. **First-class runbook object generalizing beyond DevOps.** Same primitive works for security ops, data pipelines, regulated enterprise workflows.

## Cited Sources

The full conversation and fact-checking that seeded this project is preserved at [`../chats/2026-04-20-verification-agent-pattern.md`](../chats/2026-04-20-verification-agent-pattern.md). That file contains the original design discussion plus a literature review with citations to all of the above.

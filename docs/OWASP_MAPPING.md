# StepProof vs OWASP Agentic AI Top 10

The OWASP Agentic AI Top 10 (published December 2025) is the first formal taxonomy of risks specific to autonomous AI agents. Any serious agent governance tool needs to be able to answer, per risk: *how do you cover this?*

This is StepProof's answer, honest about coverage level and phase.

| # | OWASP Risk | StepProof Coverage | Status |
|---|------------|-------------------|--------|
| 1 | **Goal hijacking** — agent subverted into a different objective | [Keep Me Honest](KEEP_ME_HONEST.md) plan declaration binds the agent to its own stated intent. Amendments that expand scope require approval. Drift detection: deviation from declared plan fires policy denial. | Design complete (Phase 2) |
| 2 | **Tool misuse** — agent using tools outside their intended scope | Four execution rings ([ADR-0002](adr/0002-four-execution-rings.md)) classify every action by blast radius. Unclassified tools default to Ring 3. Step-level `allowed_tools` narrow further. Raw `Bash` blocked at Ring 3 unless intent declared. | Partial (Phase 1) — runtime enforces; adapter ships Phase 2 |
| 3 | **Identity abuse** — stolen or impersonated agent credentials | Three-property trust ([ADR-0003](adr/0003-three-property-trust.md)): identity + authority + liveness as independent gates. Liveness gate eliminates ghost agents. MVP uses session-bound identity; Ed25519 DIDs planned for high-assurance deployments. | Partial (MVP), full design done |
| 4 | **Supply chain risks** — malicious tools, plugins, or dependencies | Out of scope for MVP; defer to platform-layer controls (signed MCP tool manifests when the ecosystem adopts them). Tracked as a follow-up for the Marketplace analog. | Deferred (Phase 4+) |
| 5 | **Code execution** — unconstrained code or command execution | Ring-based gates + action classification. `Bash` in Ring 3 by default. `Write`/`Edit` classified by target-path globs ([ADAPTER_BRIDGE.md §C](ADAPTER_BRIDGE.md)). `.env` writes structurally denied. | Partial (Phase 1) — runtime enforces; adapter ships Phase 2 |
| 6 | **Memory poisoning** — corrupted memory steering future decisions | Partial coverage through evidence contract (GUARD-002): verifiers consume structured IDs, not free-text memory. Full coverage (cross-model voting on suspect memory-dependent outputs) not yet in scope; tracked against Microsoft's CMVK pattern as a Tier 3 verifier for high-stakes steps. | Partial, Tier 3 follow-up |
| 7 | **Insecure communications** — exposed channels between agents | Out of scope — StepProof is intra-session. Inter-agent encryption belongs to the transport layer (IATP-class protocols). We'll consume identity primitives from upstream projects rather than reinventing them. | Out of scope |
| 8 | **Cascading failures** — one agent's fault propagating | Step-level failure handling (`on_fail: block \| retry \| escalate_human` per [RUNBOOKS.md](RUNBOOKS.md)). Trust behavioral signals escalate on repeat failures. Circuit-breaker-class protection at the policy-engine level ("fail twice → escalate") per POLICY.md authoring guidelines. | Partial (Phase 1) |
| 9 | **Human-agent trust exploitation** — agent misused by humans, or misleading humans | Approval workflow for Ring 3 and high-risk runbooks. Audit log records every decision with attribution (`human_owner_id`, `actor_id`, `run_id`, `step_id`). Shadow mode prevents surprise enforcement. Out-of-band approval routing (Slack/web/mobile) scheduled Phase 3. | Partial (MVP), full design done |
| 10 | **Rogue agents** — agents operating outside expected boundaries | Ring isolation ([ADR-0002](adr/0002-four-execution-rings.md)) caps blast radius per trust level. Liveness expiration moves unreachable runs to `suspended` → `expired`, freezing authority. Worker cannot execute Ring 2+ actions without an active, verified runbook. Kill-switch analog: revoke session → all dependent runs expire. | Partial (MVP), full design done |

## Summary

- **Covered today (Phase 1 MVP):** #2, #3, #5, #8, #9, #10 at partial strength. #1 in design.
- **Shipping in Phase 2 (adapter + keep-me-honest):** #1, #2, #5, #9 at full strength.
- **Deferred to Phase 4+:** #4 (supply chain), portions of #6 (memory poisoning via CMVK).
- **Out of scope, consumed from upstream:** #7 (inter-agent communications encryption).

## Why This Mapping Isn't Vanity

Every OWASP category points at a class of real incidents. One real observed session exemplified several simultaneously:

- Ad-hoc `psql` + ad-hoc Python script execution → **#2 Tool misuse** and **#5 Code execution**
- Environment cross-wiring to production DB while agent thought it was in develop → **#1 Goal hijacking** (agent executing against wrong target)
- Zombie container running old code past a "successful" deployment → **#10 Rogue agents**
- Silent NULL violation loading 0 rows while reporting success → **#6 Memory poisoning** (corrupted state steering next decisions)

Any one of those, unchecked, produces the kind of 11-hour debug cycle that makes scale impossible. StepProof's job is to catch each at the gate that matches its OWASP category.

## Regulatory Context

These risks are becoming legally actionable:

- **EU AI Act** — high-risk AI obligations effective **August 2026**. Governance, transparency, audit trails, risk management required.
- **Colorado AI Act** — enforceable **June 2026**. Applies to consequential decisions made by AI systems.
- **SOC 2**, **HIPAA**, sector-specific regulations — StepProof's audit log supports `compliance_tags[]` on every event, designed for framework-specific filtering and export.

StepProof treats these as design inputs, not marketing. An audit log that cannot answer "which policies were evaluated at 14:32 UTC when this production deploy was authorized?" is not compliance-ready. Ours can.

## Cross-Reference

- OWASP Agentic AI Top 10: [owasp.org](https://genai.owasp.org/) (December 2025 release)
- Microsoft Agent Governance Toolkit OWASP mapping: [blog post](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)

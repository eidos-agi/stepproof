# Prior Art — Deeper Dive

A per-source extraction of implementation patterns from the adjacent prior art, with concrete StepProof implications. This complements [PRIOR_ART.md](PRIOR_ART.md), which is the citation catalog.

## Microsoft Agent Governance Toolkit (April 2, 2026)

Sources:
- Blog: [opensource.microsoft.com/blog/2026/04/02](https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/)
- Repo: [github.com/microsoft/agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit) (cloned and read)

### What it is

Open-source runtime governance for AI agents. Direct category analog to StepProof.

### Adopt

- **Stateless policy engine with sub-millisecond p99 (<0.1ms).** The engine does not maintain per-request state — all state lives in the decision input or asynchronously-loaded data. StepProof mirrors this: the engine is stateless; `PolicyDecision` is a pure function of `(input_action, data_bundle)`.
- **Multi-policy-language support.** YAML rules for simple cases, OPA Rego for general policy, Cedar for authorization-shaped rules. StepProof ships YAML as the default and exposes OPA and Cedar as drop-in backends.
- **Public extension interfaces.** They expose `ToolCallInterceptor`, `BaseIntegration`, `PluginInterface`, `PolicyProviderInterface`. StepProof adopts comparable named interfaces so integrations are explicit, not implicit:
  - `ToolCallInterceptor` — hook adapters (Claude Code, CI gates, etc.)
  - `PolicyProvider` — pluggable backends (YAML, OPA, Cedar, custom)
  - `Verifier` — Tier 1/2/3 verifier implementations
  - `EvidenceAdapter` — source of truth connectors (git, deploy API, DB, logs)
  - `AuditSink` — where audit records go (Postgres, Kafka, S3)
- **Dynamic trust scoring on a 0–1000 scale with five behavioral tiers.** Trust decays over time based on behavior. StepProof adopts this to formalize the existing "fail twice → escalate" rule as a continuous trust score:
  - New worker starts at 800 (trusted but not fully).
  - Verifier pass +10 (decays to ceiling).
  - Verifier fail −100.
  - Bypass attempt (denied action) −200.
  - Policy layers consult trust: below 500 → require_approval on medium-risk actions; below 200 → block non-trivial actions entirely.
- **Multi-framework integration points.** They ship: LangChain callbacks, CrewAI decorators, Microsoft Agent Framework middleware, OpenAI Agents SDK native. StepProof's roadmap Phase 6 already plans this; adopting the naming pattern ensures our adapters are idiomatic per framework.
- **Compliance framework mappings.** They map to EU AI Act, HIPAA, SOC 2, OWASP Agentic AI Top 10. StepProof's audit log schema should include a `compliance_tags[]` field and ship pre-built filters for these frameworks.

### What the source reveals (beyond the blog)

The repo is a 13-package platform. Key signals from the code and ADRs:

- **ADR discipline.** The toolkit maintains numbered architecture decision records in `docs/adr/`. Format: `Status / Date / Context / Decision / Consequences / Follow-up / Reference implementations`. StepProof adopts the same format starting with [`docs/adr/`](adr/).
- **Sample policy (`devops_governance.yaml`) structure:**
  ```yaml
  rules:
    - name: "block_production_deploy"
      condition:
        field: "message"
        operator: "contains_any"
        value: "to production,production deploy,deploy_to_production,..."
      action: "deny"
      priority: 100
      message: "Direct production deployments require approval gates..."
  defaults:
    action: "allow"
    max_tokens: 4096
    max_tool_calls: 10
    confidence_threshold: 0.8
  ```
  Concrete takeaways:
  - **Priority-based rule ordering** (100 highest).
  - **`audit` as a third action type** alongside `allow` and `deny` — pure logging without enforcement. StepProof adopts.
  - **Content-pattern matching**, not just tool-name. Catches "I'll just run this real quick" intent *before* a tool call materializes. StepProof's `UserPromptSubmit` adapter already soft-nudges on this; policy engine can harden it.
  - **`confidence_threshold`** in defaults — probabilistic gates are expected.
  - **Rate-limit controls** (`max_tokens`, `max_tool_calls`) built into defaults. StepProof adopts per-runbook token/tool-call budgets.

- **ADR 0004 — Keep policy evaluation deterministic and out of LLM control loops:**
  > Do not place an LLM in the allow-or-deny decision loop for runtime governance. LLM-based guards introduce tens to hundreds of milliseconds of latency and probabilistic behavior. For a control plane that must be testable, auditable, and safe under failure, inline policy decisions cannot depend on model mood, prompt quality, or external inference availability.

  This is the canonical argument for why StepProof's policy engine is **Tier 1 only**. Tier 2 (Haiku) is for *step-completion verification at boundaries*, not inline gates. StepProof writes its own mirror ADR.

- **ADR 0002 — Four execution rings instead of RBAC:**
  A ring-based runtime privilege model that maps to **blast radius**, not identity:
  - Ring 0: sandbox / read-only.
  - Ring 1: reversible writes, non-prod.
  - Ring 2: non-reversible writes, non-prod.
  - Ring 3: production-facing.

  Each ring has default rate limits, trust-score thresholds, and reversibility semantics. RBAC still exists for human admin but is not the runtime enforcement mechanism. StepProof adopts the rings model as a first-class attribute of every tool/action class, layered under runbook-step `allowed_tools`.

- **ADR 0005 — Three-property trust decomposition (liveness attestation):**
  Trust is decomposed into **three independent properties, each with independent decay timelines:**

  | Property | What it proves | Decay | Recovery |
  |----------|---------------|-------|----------|
  | **Identity** | Who the agent is (DID + Ed25519) | Very slow | Re-registration |
  | **Authority** | What it may do (delegation scope) | Medium | Re-delegation |
  | **Liveness** | Alive right now (heartbeat) | Rapid (minutes) | Heartbeat resumption |

  Critical pattern: **liveness is a GATE, not a score modifier.**
  ```
  can_exercise_authority = identity_valid AND authority_valid AND liveness_active
  ```
  This eliminates the "ghost agent" failure mode — a high-trust agent that crashed cannot continue to authorize actions just because its base score is high. StepProof supersedes the initial "fail twice → escalate" binary rule with this three-property decomposition.

  Heartbeat protocol: SIP REGISTER-style TTL registration with `TTL/2` refresh cadence; delegation chain hash embedded in the heartbeat to bind liveness to authority in one message. Suspended (reversible) → Expired (irreversible at delegation level).

- **Package structure.** The toolkit ships 13 packages: `agent-runtime`, `agent-hypervisor`, `agent-compliance`, `agent-discovery`, `agent-mesh`, `agent-mcp-governance`, `agent-marketplace`, `agent-os`, `agent-os-vscode`, `agent-sre`, `agent-lightning`, `agent-governance-dotnet`, `agentmesh-integrations`. StepProof doesn't need 13 packages at MVP, but this shows the ambition direction: not just a policy engine, but a platform. Our MVP is `stepproof-runtime` + `stepproof-cc-adapter`; future packages mirror this taxonomy where applicable.

- **Shadow mode.** ADR 0004 mentions "shadow-mode findings" reviewed by humans outside the enforcement path. StepProof adopts a `shadow: true` flag at the policy and runbook level: decisions evaluate and log but do not enforce. Essential for authoring new runbooks without breaking production flow.

### Gaps (where StepProof can differentiate)

Microsoft's blog post is strong on architecture but deliberately thin on concrete shapes. Publishing these is a real differentiator:

- **Concrete API payloads.** StepProof publishes the full `input` and `output` JSON Schema for `/policy/evaluate`.
- **Audit log schema.** StepProof's audit schema is public, versioned, and consumable by third-party tools.
- **Sample policies in all three languages.** YAML, Rego, and Cedar examples for every common gate (migration guards, deploy gates, secret rotation, approval escalation).
- **Decision rationale in the response.** Microsoft's toolkit allow/denies; StepProof returns `reason`, `policy_id`, `suggested_tool`, and `trust_score_delta` so the worker (and humans) can understand and adapt.
- **Quorum/approval mechanics.** Microsoft mentions "approval workflows with quorum logic" but doesn't specify. StepProof's approval model is specified: single-approver default, optional N-of-M quorum per runbook, time-boxed, optional out-of-band (Slack/web/mobile).

## Cloudflare Workflows v2

Source: [blog.cloudflare.com/workflows-v2](https://blog.cloudflare.com/workflows-v2/)

### What it is

Durable, replay-safe multi-step workflow runtime. StepProof's control plane is not a workflow engine; it depends on one. Cloudflare's v2 design gives us concrete patterns to copy even if we start on Postgres + alarms.

### Adopt

- **Three step primitives.** StepProof extends its runbook schema to support all three:
  - `step.do()` — action step (current default).
  - `step.waitForEvent()` — external-gate step (human approval, webhook, CI completion).
  - `step.sleep()` — time-gate step (e.g., "wait 30 minutes after staging deploy before allowing prod").
- **String-keyed step names as replay anchors.** StepProof's `step_id` already serves this function; document it explicitly as the replay contract.
- **At-least-once execution semantics.** Steps retry independently; a failure in one step does not cascade. Matches StepProof's `on_fail: retry`.
- **Alarm-based durability.** Every step has a `timeout_seconds` that schedules an alarm. If the alarm fires before completion, the step auto-fails and the runbook's `on_fail` policy takes over. StepProof's control plane uses the same pattern via Postgres `SELECT ... FOR UPDATE SKIP LOCKED` or a dedicated alarm service.
- **Durable state per instance.** Cloudflare uses Durable Objects + SQLite per instance. StepProof uses one Postgres row per `workflow_run` with a `state` JSONB column, plus a separate `step_runs` table keyed by `(run_id, step_id)`.
- **Consistent cursor pagination** on listings. StepProof's `/runs` and `/audit` endpoints use cursor pagination from day one.

### Scale targets to aim for

- 50K concurrent workflow runs (matches Cloudflare v2).
- 300 runs/sec creation rate.
- 2M queued runs.

These are aspirational for MVP but inform the data model: avoid hot locks, avoid per-instance coordinators that don't horizontally distribute.

### Architecture pattern to borrow at scale

Cloudflare's v2 uses a "Gatekeeper" leasing system plus per-workflow "SousChef" Durable Objects with 1-second request batching to avoid control-plane saturation. StepProof's equivalent at scale:

- A lightweight **lease service** that allocates concurrency slots per-runbook-template (prevent a single noisy runbook from starving others).
- Per-workflow coordinators that batch audit writes in short windows.

This is Phase N work; roadmap placeholder only.

## Open Policy Agent (OPA)

Source: [openpolicyagent.org/docs/latest/philosophy](https://www.openpolicyagent.org/docs/latest/philosophy/)

### What it is

Industry-standard policy-as-code engine. StepProof's default YAML rule engine is a strict subset; OPA is the first-class professional backend.

### Adopt

- **`input` (sync push) vs `data` (async bundle) separation.** This is the clean model StepProof's policy API should formalize:
  - `input` = the normalized action event (the thing happening right now).
  - `data` = runbook templates, active workflow runs, recent audit entries, trust scores (loaded asynchronously, cached, bundled).
- **Unified `data` namespace.** Both stored state and rule-computed (virtual) documents live at the same addresses. StepProof policies reference `data.stepproof.active_run`, `data.stepproof.prior_steps_verified`, `data.stepproof.trust_score` without caring whether the value is a script output, a DB lookup, or a computed rule.
- **Bundle model for async data distribution.** StepProof ships "policy bundles" — tarballs containing Rego policies + static data — that can be loaded by the engine and hot-swapped without restart.
- **`http.send` during evaluation.** When a policy needs live state (e.g., "is this deploy actually SUCCESS right now"), the engine can synchronously call out. StepProof permits this for deterministic Tier 1 checks; forbids it for anything that could cause side effects.
- **In-memory caching** for sub-millisecond evaluation. Consistent with the Microsoft stateless-engine pattern.

### OPA-documented gaps that StepProof fills

OPA's own documentation flags three weaknesses for AI-agent governance — StepProof's verifier fabric is exactly the orchestration layer that fills them:

- **Real-time model output filtering / result transformation.** Tier 2 verifier consuming unstructured output.
- **Probabilistic guardrails / confidence-based decisions.** StepProof verifier results include `confidence`; policies can gate on it.
- **Continuous feedback loops between agent actions and policy.** StepProof's trust score + audit log provide exactly this loop.

This is nice external validation: OPA itself says "you need something outside OPA for this," and what they describe is StepProof.

## Verification-Aware Planning (EACL 2026, "VeriPlan")

Source: [aclanthology.org/2026.eacl-long.353.pdf](https://aclanthology.org/2026.eacl-long.353.pdf)

### Status

Could not extract content from the PDF via WebFetch (binary decode failure). The paper is cited in our PRIOR_ART.md from its abstract and title — "VeriPlan" name and the core thesis (plans with verification steps embedded, not bolted on) are confirmed, but we could not pull concrete algorithm or schema details.

### Action

Fetch the paper text manually (or via `arxiv` mirror) and produce a follow-up extraction. Until then, StepProof's runbook schema (`required_evidence`, `verification_method`, `verification_tier` per step) is the operational analogue of their thesis even without the formal algorithmic details.

---

## Synthesis: What Changed in StepProof's Design

Based on this deeper pass, the following concrete additions land in the repo:

1. **Runbook schema extensions** — `step_type: do | wait_for_event | sleep` supporting the three step primitives (see [RUNBOOKS.md](RUNBOOKS.md)).
2. **Policy API formalization** — `input` / `data` separation matching OPA (see [POLICY.md](POLICY.md)).
3. **Three-property trust decomposition** (identity / authority / liveness as independent gates), superseding the earlier continuous-score sketch. See [ADR 0003](adr/0003-three-property-trust.md).
4. **Four execution rings** (Ring 0 sandbox → Ring 3 production-facing) as the primary runtime privilege model. See [ADR 0002](adr/0002-four-execution-rings.md).
5. **Deterministic enforcement mandate** — no LLM in the `PreToolUse` decision loop. See [ADR 0001](adr/0001-deterministic-policy-evaluation.md).
6. **`audit` decision type** — pure logging without enforcement, alongside `allow` / `deny` / `transform` / `require_approval`.
7. **Shadow mode** — `shadow: true` on policies and runbooks. Decisions evaluate and log but do not enforce. Safe on-ramp for new rules.
8. **Priority-based rule ordering** with explicit integer priorities per rule.
9. **Content-pattern matching** — policies match on the action's text/command content, not just tool name. Catches intent before it materializes as a specific tool call.
10. **Named plugin interfaces** — `ToolCallInterceptor`, `PolicyProvider`, `Verifier`, `EvidenceAdapter`, `AuditSink`.
11. **Compliance tags in audit schema** — `compliance_tags[]` with built-in filters for EU AI Act / HIPAA / SOC 2 / OWASP Agentic AI Top 10.
12. **Cursor pagination** on all list endpoints from day one.
13. **Alarm-based step timeouts** — not synchronous waits.
14. **OPA and Cedar as first-class policy backends** — YAML is the default but not the ceiling.
15. **Decision responses include `reason`, `policy_id`, `suggested_tool`, `trust_signals`** — every decision is explainable to both the worker and auditors.
16. **ADR discipline** — numbered, dated, immutable decision records under [`docs/adr/`](adr/).
17. **Heartbeat protocol** — TTL-based liveness with suspend-then-expire semantics, preventing ghost-agent failure modes.

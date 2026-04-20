# StepProof vs Microsoft Agent Governance Toolkit

Microsoft open-sourced the Agent Governance Toolkit (AGT) in April 2026. It's the closest adjacent project to StepProof. This doc is honest about where they differ, where they overlap, and where StepProof should consume AGT rather than reinvent it.

## TL;DR

- **AGT is horizontal infrastructure** — framework-agnostic, 5 languages, 7 packages, platform-grade. Built to support any agent framework at scale.
- **StepProof is a narrow, opinionated product** — Claude Code + MCP first, Python-only, runbook-centric, "keep me honest" as the primary mode.
- They solve different problems. StepProof is the product we need. AGT has components StepProof should consume.

## Side-by-Side

| Dimension | Microsoft AGT | StepProof |
|-----------|---------------|-----------|
| **Primary mental model** | Policy + identity + rings (OS-kernel metaphor) | Runbooks + steps + evidence + verifiers (workflow metaphor) |
| **Primary enforcement unit** | Individual action decisions | Runbook steps (action decisions gated by step context) |
| **Authorship model** | Policies authored ahead of time, apply to all sessions | Plans declared in-session by the agent (["keep me honest"](KEEP_ME_HONEST.md)), templates for regulated ops |
| **Frameworks supported** | LangChain, AutoGen, CrewAI, MAF, Dify, LlamaIndex, LangGraph, OpenAI Agents, Haystack, PydanticAI | Claude Code + MCP (planned: Cursor, OpenAI Agents) |
| **Languages** | Python, TypeScript, Rust, Go, .NET | Python |
| **Packages** | 7 (Agent OS, Mesh, Runtime, SRE, Compliance, Marketplace, Lightning) | 2 today (runtime, mcp), 3 target (+cc-adapter) |
| **Deployment** | AKS sidecar, Foundry, Azure Container Apps | Embedded-mode SQLite default; any cloud for hosted |
| **Policy languages** | YAML, OPA Rego, Cedar | YAML default; OPA/Cedar planned |
| **Identity** | DIDs + Ed25519 + IATP | Session-bound today; three-property trust in design ([ADR-0003](adr/0003-three-property-trust.md)) |
| **Verification model** | Cross-Model Verification Kernel (CMVK) — multi-model majority voting | Three-tier verifiers (Tier 1 scripts, Tier 2 small-model read-only, Tier 3 heavyweight opt-in) |
| **Trust model** | 0–1000 dynamic score with behavioral decay, five tiers | Three-property (identity, authority, liveness) gates + behavioral signals as policy input |
| **Open-source maturity** | 9,500+ tests, ClusterFuzzLite, SLSA provenance, OpenSSF Scorecard | Phase 1 MVP; 8 smoke tests |
| **Regulatory coverage** | EU AI Act, HIPAA, SOC 2, OWASP Agentic Top 10 built into Agent Compliance | OWASP mapping ([OWASP_MAPPING.md](OWASP_MAPPING.md)); compliance tags in audit log schema; full framework mapping follow-up |

## Why StepProof for Us Specifically

1. **Our problem is specific.** The [an observed session](CASE_STUDY.md) is a Claude-Code-agent-in-Python workflow where the agent drifted from its own plan under pressure. AGT solves the *general* agent-governance problem. StepProof solves *that problem*, with primitives that name exactly what went wrong: runbook, step, evidence, verifier, declared plan, amendment.
2. **Our integration surface is narrow and critical.** Claude Code + MCP is our stack. AGT doesn't support it. We'd build that adapter either way — as a first-class product in StepProof, or a second-class citizen inside AGT. First-class wins.
3. **Our surface area is small.** One engineer, AI-assisted, in a small number of repos. A 7-package platform with 9,500 tests is a maintenance surface we don't have capacity for. StepProof's ~1,500 LOC is tractable.
4. **"Keep me honest" is genuinely different.** AGT enforces policy that the agent didn't author. StepProof enforces contracts the agent authored. Different failure mode, different UX, different value proposition. That's not a feature we can retrofit onto AGT — it's a different product shape.
5. **Control over the roadmap.** If agent-governance patterns are in flux (they are), owning the product means we can steer. Vendoring AGT means Microsoft steers.

## What StepProof Should Borrow from AGT

Not reinvent — consume:

- **Agent OS as a `PolicyProvider` backend.** When rule complexity outgrows YAML, plug in Agent OS as a drop-in policy engine. Their sub-millisecond p99 latency is hard to match from scratch. Plugin interface: already named in [PRIOR_ART_DEEPER.md](PRIOR_ART_DEEPER.md).
- **Agent Compliance framework mapping.** EU AI Act, HIPAA, SOC 2 tag taxonomy. Use their labels in StepProof's audit log `compliance_tags[]` so the audit log is already framework-mapped without us writing the taxonomy ourselves.
- **OWASP Agentic Top 10 risk taxonomy.** Already adopted; see [OWASP_MAPPING.md](OWASP_MAPPING.md).
- **Scale architecture patterns.** Stateless kernel, Gatekeeper/SousChef leasing, 1-second batching to prevent saturation — blueprints for when StepProof's control plane needs to scale beyond single-node SQLite.
- **SRE primitives** (SLOs, circuit breakers, kill switch) — not in Phase 1, but the right mental model for operational hardening.

## What StepProof Deliberately Does Differently

- **Workflow-centric, not action-centric.** AGT's primary unit is "is this action allowed right now?" StepProof's is "is this action allowed at this step of this runbook?" Context-rich decisions produce better denials (*"use cerebro-migrate instead"* vs *"database write denied"*).
- **Evidence contract at the API boundary.** StepProof rejects step completion if required evidence keys are absent. AGT has nothing structurally equivalent.
- **Read-only verifier subagents via `disallowedTools` frontmatter.** Structural guarantee at the agent-definition layer, not a convention. Borrowed from hooks-mastery, not present in AGT.
- **"Keep me honest" as the primary mode.** Agent-declared plans validated at submit time. Templates remain for compliance use. AGT has pre-authored policies only; there's no equivalent inverse model.
- **Graceful degradation as a hard guarantee** ([GUARD-003](../.visionlog/guardrails/)): a StepProof outage cannot break the worker's session. Hook always exits 0 on failure; audit buffers locally; catches up on reconnect. AGT's sidecar model has similar properties but StepProof codifies it as a guardrail.

## Eventual Composition

A plausible two-year shape:

```
┌─────────────────────────────────────────┐
│              StepProof                  │
│   Runbooks • Steps • Evidence           │
│   Verifiers • Keep Me Honest            │
│   Claude Code / MCP adapter             │
└────────────┬────────────────────────────┘
             │  PolicyProvider interface
             ▼
┌─────────────────────────────────────────┐
│          Microsoft Agent OS             │
│   Policy engine backend (optional)      │
│   <0.1ms p99 evaluation                 │
└─────────────────────────────────────────┘
             │  AuditSink interface
             ▼
┌─────────────────────────────────────────┐
│       Microsoft Agent Compliance        │
│   EU AI Act / HIPAA / SOC 2 mapping     │
│   OWASP evidence collection             │
└─────────────────────────────────────────┘
```

StepProof owns the product surface — how users experience the system, the runbook model, the adapter to Claude Code. AGT supplies the deep plumbing where their investment exceeds what we'd build from scratch.

## When We Should Reconsider

If any of these become true, re-evaluate:

- AGT ships a first-class Claude Code / MCP adapter that matches our ergonomics → we lose the Claude Code moat.
- AGT adopts a "keep me honest" / agent-declared plan primitive → our conceptual moat closes.
- The governance pattern standardizes around one taxonomy and we're off the standard → cost of isolation exceeds cost of conformance.
- Regulatory compliance becomes a buy decision, not a build decision → we consume AGT Compliance wholesale.

None of these are true today. We build.

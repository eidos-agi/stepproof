# Research Corpus

Living documentation of the landscape StepProof sits in — what's been
tried, what works partially, what doesn't work, what regulators are
demanding, and where the gap specifically is.

This is *research*, not marketing. Each doc aims to be honest about:

- What the category is and who's in it
- What problem it solves (which is usually NOT StepProof's problem)
- Why it doesn't close the ceremony-enforcement loop
- Where StepProof overlaps, diverges, or generalizes from it
- What's known vs what's uncertain

## Reading order

For someone new to the space:

1. [00_methodology.md](00_methodology.md) — how this research is
   sourced, refreshed, and kept honest.
2. [01_landscape_overview.md](01_landscape_overview.md) — the big
   picture in one doc.
3. [14_stepproof_positioning.md](14_stepproof_positioning.md) — where
   StepProof fits once you've seen the landscape.
4. [15_prior_art_gaps.md](15_prior_art_gaps.md) — what's missing in
   the combined field, stated as tightly as possible.
5. Everything else as needed.

## Docs by category

### What agents and harnesses already do

- [02_training_time_alignment.md](02_training_time_alignment.md) —
  RLHF, Constitutional AI, DPO, and why training alone is not the
  answer to ceremony compliance.
- [03_tool_use_per_request.md](03_tool_use_per_request.md) — function
  calling, Claude Code hooks, MCP permissions. The lowest layer.

### Process and workflow orchestration

- [04_workflow_engines.md](04_workflow_engines.md) — Temporal,
  Prefect, Airflow, Dagster. Durable multi-step execution with LLM
  steps.
- [05_multi_agent_supervisors.md](05_multi_agent_supervisors.md) —
  CrewAI, AutoGen, LangGraph, OpenAI swarm patterns. The
  supervisor-is-also-an-agent failure mode.

### Content-level and runtime-level policy

- [06_guardrails_and_content_filters.md](06_guardrails_and_content_filters.md) —
  Guardrails AI, NeMo Guardrails, Lakera Guard, Pangea AI Guard.
- [07_enterprise_ai_gateways.md](07_enterprise_ai_gateways.md) —
  Microsoft AGT, Credal, Prompt Security, Portal26.

### Adjacent infrastructure worth knowing

- [08_policy_as_code.md](08_policy_as_code.md) — OPA, Styra, Rego;
  what StepProof inherits from policy-engine thinking.
- [09_provenance_and_signing.md](09_provenance_and_signing.md) —
  cosign, SLSA, SBOM; why this is the pattern StepProof's
  provenance verifiers should imitate.
- [10_audit_tamper_evidence.md](10_audit_tamper_evidence.md) —
  Certificate Transparency, Merkle logs, append-only stores.

### Academic and research-grade work

- [11_formal_methods.md](11_formal_methods.md) — LTL, CTL, model
  checking. Mostly not productized.

### Regulation and standards

- [12_standards_owasp_nist_iso.md](12_standards_owasp_nist_iso.md) —
  OWASP Agentic Top 10, NIST AI RMF, ISO 42001.
- [13_regulation_eu_co.md](13_regulation_eu_co.md) — EU AI Act,
  Colorado AI Act, US state-level AI regulation.

### Synthesis

- [14_stepproof_positioning.md](14_stepproof_positioning.md) — where
  StepProof actually fits in the landscape.
- [15_prior_art_gaps.md](15_prior_art_gaps.md) — the specific
  assembled gap StepProof addresses.
- [16_competitive_watch.md](16_competitive_watch.md) — who to
  monitor, why, and what would be a threat vs an adjacency.
- [17_known_unknowns.md](17_known_unknowns.md) — the things this
  research hasn't answered and how to answer them.

## How to keep this current

Update triggers:
- **Quarterly**: re-scan arXiv cs.AI and cs.SE for new papers matching
  the search terms in [00_methodology.md](00_methodology.md).
- **On product launch in an adjacent category**: new Temporal feature,
  new OpenAI Agent SDK release, new guardrails library — spot-check
  against the relevant topic doc.
- **On regulation advancement**: EU AI Act enforcement dates, new
  state laws, updated NIST guidance.
- **On significant paper**: if something shifts the category
  understanding, cross-link and update the positioning doc.

See [existing prior-art docs](../PRIOR_ART.md) and
[deeper dive](../PRIOR_ART_DEEPER.md) for earlier research. This
corpus is the structured follow-up.

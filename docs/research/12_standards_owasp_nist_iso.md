# Standards — OWASP, NIST, ISO

The non-binding but load-bearing standards that shape how enterprise
buyers, auditors, and risk teams think about AI governance. StepProof
doesn't implement these — it produces the artifacts they want to see.

## OWASP Agentic AI Top 10 (December 2025)

The first formal risk taxonomy specific to agentic systems. Names the
categories of failure that StepProof addresses at the ceremony layer.

As of publication, the top-level categories include (approximate
list, confirm against the published source):

1. Excessive agency — agent authorized to do more than it should.
2. Uncontrolled tool use — agent calls tools without appropriate
   scoping.
3. Prompt injection against agentic contexts.
4. Misaligned tool selection — agent chooses the wrong tool for the
   job.
5. Inadequate decision auditing — no trail of why the agent did what.
6. Supply-chain risks on tool ecosystems.
7. Data leakage through agent memory / context.
8. Insecure delegation between agents.
9. Unauthorized state mutation.
10. Accountability / traceability gaps.

**StepProof's direct coverage** of items on this list:

- #1 Excessive agency → per-step `allowed_tools` caps authority
  scope to what the current step requires.
- #2 Uncontrolled tool use → classifier-based tool scoping; only
  sanctioned actions permitted.
- #4 Misaligned tool selection → bash-pattern scoping; denies psql
  when cerebro-migrate is sanctioned.
- #5 Inadequate decision auditing → audit log as first-class
  artifact of every run.
- #9 Unauthorized state mutation → verifier-gated step advancement
  ensures only authorized mutations reach terminal state.
- #10 Accountability gaps → tamper-evident audit log (future
  increment) + per-step evidence retention.

Partial or indirect coverage:

- #3 Prompt injection — content-layer problem; composable with
  guardrails.
- #6 Supply-chain — adjacent (SLSA/cosign category).
- #7 Data leakage — content-layer.
- #8 Insecure delegation — partial via per-step scoping for the
  sub-agent pattern.

The doc `docs/OWASP_MAPPING.md` in the main docs folder has the
per-risk narrative. This research doc names it as the standards
source.

## NIST AI Risk Management Framework (AI RMF)

Published 2023, revised since. Voluntary federal framework for
managing risk in AI systems. Not legally binding; increasingly
referenced in government contracts and vendor due diligence.

Four core functions:

- **Govern** — policies, processes, accountability structures.
- **Map** — identify AI system purpose, context, risks.
- **Measure** — quantify risks; test and evaluate.
- **Manage** — prioritize, respond, monitor.

StepProof's audit-log output is directly consumable under the
"Measure" and "Manage" functions. The structured ceremony
declaration under "Map" (declared purpose, scope, dependencies).

NIST also published a **Generative AI Profile** (AI 600-1) that
extends the core framework to generative / foundation model
systems. StepProof is downstream of this profile — we implement
controls; NIST names what the controls need to accomplish.

## ISO 42001 (AI Management System Standard)

Published 2023. The ISO equivalent of a management-system standard
(like 27001 for infosec, 9001 for quality), tailored to AI. Creates
a recognized certification path for organizations.

Relevant clauses include (approximate — verify against text):

- Documented AI management processes.
- Risk assessment and treatment.
- Operational controls and monitoring.
- Internal audit.
- Corrective action.

StepProof produces evidence for each of these at the process-
compliance layer:

- Documented processes → runbook templates.
- Risk assessment → classification YAML (what actions are
  ring-classified).
- Operational controls → hook enforcement.
- Monitoring → audit log.
- Internal audit → queryable SQLite / exported reports.
- Corrective action → retry / escalation / run abandonment with
  reason captured.

Enterprise buyers pursuing ISO 42001 certification will treat
StepProof's audit log as one of their substantiating artifacts. That
is a concrete buyer-readiness argument.

## Relationship to one another

- **OWASP** names the threats.
- **NIST** structures the response.
- **ISO** certifies the implementation.

A buyer asking "what controls do you have against OWASP Agentic
#2?" wants a specific answer. StepProof's answer is a specific
runbook template with per-step scoping and classifier-based tool
denial. A buyer pursuing ISO 42001 wants a process, a log, and
evidence. StepProof produces all three.

## What these standards don't require

None of them specify *how* to enforce. They specify *what* must be
achieved. StepProof is one implementation path. Competitors will
exist; standards don't mandate a specific vendor.

## Known unknowns

- Whether OWASP Agentic Top 10 will be updated to add or modify
  categories. Probably yes as the field matures.
- Whether NIST will publish an AI-agent-specific sub-profile
  beyond the current generative AI profile. Plausible in 2026-2027.
- Whether ISO 42001 auditors will develop expectations about
  specific artifact types (e.g., "must have ceremony-level audit
  log"). Early to say.

## Representative sources

- OWASP Agentic AI Top 10: OWASP Foundation publication, December
  2025.
- NIST AI RMF 1.0: `nist.gov/itl/ai-risk-management-framework`.
- NIST Generative AI Profile: AI 600-1.
- ISO 42001: ISO standard, purchase from ISO.

## Date stamp

2026-04-20.

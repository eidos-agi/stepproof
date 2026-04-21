# Landscape Overview

The big picture of AI agent governance circa 2026, compressed into
one document. Deeper treatment of each category is in its own file.

## The problem space

**Agents deployed on real systems** (production DBs, deploy
pipelines, cloud APIs, financial systems, healthcare workflows) fail
in repeatable ways:

- They skip declared processes under pressure.
- They take unsanctioned shortcuts to the same observable end state.
- They claim completion without doing the work.
- They lose track of state across long sessions.
- They work differently in dev and prod because no layer enforces
  consistency.

These are not theoretical. They are lived. Greenmark-class incidents
are common; most are unreported.

## What existing layers attempt

Roughly, the industry has six answers to *"how do we make agents
behave?"*, in increasing order of structural enforcement:

| Layer | Example | Strength | Weakness |
|---|---|---|---|
| Training-time alignment | RLHF, Constitutional AI, DPO | Refuses explicit adversarial prompts | Drifts silently on implicit ambiguity |
| Content guardrails | Guardrails AI, Lakera, NeMo | Filters bad tokens, PII, prompt injection | Not workflow-aware; per-token/per-message |
| Tool-use constraints | OpenAI function calling, Claude Code hooks | Per-call allow/deny | Not step-aware; no state across calls |
| Agent orchestration | CrewAI, AutoGen, LangGraph | Coordinates multiple agents | Supervisor is itself an LLM; same drift |
| Workflow engines w/ LLM steps | Temporal, Prefect, Airflow | Durable multi-step execution | Trusts LLM output unless you hand-roll verification |
| Enterprise AI gateways | Microsoft AGT, Credal, Prompt Security | Policy + observability at the request layer | Request-level, not ceremony-level |

**Nothing on this list closes the full loop** of: *declared
multi-step ceremony + per-step tool scope + independent verifier
reading real state + tamper-evident audit log*.

Every item on the list does *part* of what StepProof needs to do.
None is the assembled system.

## What StepProof adds

Three things, glued together:

1. **A ceremony object as a first-class artifact.** A runbook
   template that declares the ordered steps, their allowed tools,
   their required evidence, and their verifiers.
2. **Verifier fabric that reads real state.** Not the agent's claim,
   not an LLM re-judging the agent's claim, but direct reads against
   the target system (DB migration trackers, GitHub Actions API, real
   file disk state, signed artifact registries).
3. **A tamper-evident audit log** as a byproduct of operation —
   every policy decision, every verifier result, every advancement,
   with timestamps and policy_ids, written by the runtime in SQLite,
   queryable by auditors.

Plus one connective mechanism:

4. **A PreToolUse hook** (or equivalent harness-specific enforcement
   point) that binds the agent to the current ceremony's scope. The
   agent literally cannot step outside the declared tools for the
   current step.

## The regulatory forcing function

Agent governance has moved from nice-to-have to mandatory in the
span of eighteen months:

- **OWASP Agentic AI Top 10** (December 2025) — the first formal risk
  taxonomy for agentic systems. Names the failure modes. Doesn't
  prescribe solutions.
- **Colorado AI Act** — enforceable June 2026. Consumer protections
  for high-risk AI decision-making.
- **EU AI Act** — high-risk obligations effective August 2026.
  Requires documented, auditable, human-overridable controls.
- **NIST AI RMF** — federal risk management framework, not
  legally binding but increasingly referenced in contracts.
- **ISO 42001** — AI management system standard, being adopted by
  enterprises to mirror their ISO 27001 processes.

The artifacts these regimes demand — declared process, evidence at
each decision point, auditable trail, human override — map directly
onto what StepProof's architecture produces as a byproduct of
running.

## The empirical hole

The single most telling observation: **no deployed system we've
found lets a runbook author write a declared ceremony and have the
agent structurally unable to deviate from it.**

Workflows have ordering but not verification-from-real-state.
Verifiers exist in narrow contexts (CI, migration tools) but don't
get assembled into a ceremony abstraction. Hooks exist but lack
ceremony context. Guardrails are per-message. Gateways are per-call.

StepProof is the composition. See
[15_prior_art_gaps.md](15_prior_art_gaps.md) for a tighter
statement of this gap.

## Date stamp

Last meaningful update: 2026-04-20. Refresh the `02_` through `13_`
docs before updating this one.

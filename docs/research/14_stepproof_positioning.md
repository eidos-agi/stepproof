# StepProof's Position in the Landscape

Where StepProof actually sits in the taxonomy of everything the
other research docs surveyed. What it overlaps with. What it doesn't
try to be. The single-paragraph elevator line.

## The one-paragraph version

StepProof is **the ceremony-enforcement layer for AI agents.**
Agents declare a plan, bind themselves to its step ordering and
per-step tool scope, and produce structured evidence at each step
boundary. An independent verifier reads real external state (DBs,
APIs, file systems, signed artifacts) to confirm the claim, and
every decision is recorded in a tamper-evident audit log. It sits
*between* training-time alignment (which reduces *wanting* to
shortcut) and workflow orchestration (which provides durable
step execution but not verification), in a space that nothing
else currently assembles coherently.

## The category map

Restating the table from `01_landscape_overview.md` with StepProof's
place in it:

| Layer | Example | StepProof? |
|---|---|---|
| Training-time alignment | RLHF, CAI, DPO | No. Composable with it. |
| Content guardrails | Guardrails AI, NeMo, Lakera | No. Composable with it. |
| Tool-use constraints | OpenAI function calling, Claude Code hooks | Yes (built on). |
| Agent orchestration | CrewAI, AutoGen, LangGraph | No. Orthogonal. |
| Workflow engines with LLM steps | Temporal, Prefect, Airflow | Stackable inside. |
| Enterprise AI gateways | AGT, Credal, Prompt Security | Complementary, not competitive for the ceremony problem. |
| **Ceremony enforcement** | **StepProof** | **Yes.** |

## What StepProof uniquely does

Compared to every category above:

1. **Declared ceremony as a first-class artifact.** A runbook YAML
   with steps, allowed_tools, evidence, verifiers. Auditable,
   diffable, versionable. Nothing else in the landscape has this
   as a primary object.
2. **Per-step tool scope at the harness boundary.** Hooks fire on
   every tool call; scope depends on which step of which ceremony is
   active. No other category combines per-call enforcement with
   ceremony state.
3. **Verifiers that read real external state.** Not LLM judgments,
   not workflow-trusted returns — direct queries against GitHub API,
   migration tracking tables, deploy platforms, file disk state.
   Workflow engines trust return values; guardrails inspect content;
   neither checks reality.
4. **Tamper-evident audit log as byproduct.** Every decision logged
   with policy_id, timestamp, verifier result. Queryable by
   auditors. Designed to satisfy EU AI Act Article 12 / ISO 42001
   / OWASP #5 and #10 out of the box.
5. **Paired with/without comparison methodology.** The repo's
   challenges framework is itself a contribution: empirical
   evaluation of agent behavior under enforcement vs. without. No
   prior work we've found uses this methodology as a governance
   benchmark.
6. **Integration into existing harnesses via hooks + MCP.** Not a
   new runtime; piggy-backs on Claude Code's own primitives. Low
   adoption cost. Extensible to other harnesses (Cursor, OpenAI
   Agents) through per-harness adapters.

## What StepProof explicitly doesn't try to be

- **Not an alignment project.** Training is not StepProof's concern.
- **Not a content filter.** Guardrails libraries exist; we don't
  compete on PII detection or prompt-injection scanning.
- **Not a workflow engine.** Temporal et al. solve durable
  multi-step execution; StepProof sits inside their steps,
  providing ceremony integrity.
- **Not a general policy engine.** OPA / Rego exist; StepProof
  inherits their architectural ideas but serves a specific
  vertical (agent ceremonies).
- **Not a replacement for humans.** Ring 3 actions require human
  approval; StepProof makes that integrable, not optional.

## The closest "if anything is a direct competitor" answer

Nothing fully is, today. The closest candidates:

- **A future Microsoft AGT** that extends from request-level to
  ceremony-level enforcement with verifier fabric.
- **A future Temporal release** that adds evidence-verification
  primitives for LLM activities.
- **An Anthropic-native Claude Code feature** that ships ceremony
  objects as part of the harness.
- **A stealth startup** we haven't seen yet.

Any of these could arrive within 6-18 months. Watching is cheap;
responding requires speed and category leadership. See
`16_competitive_watch.md`.

## The "why now" argument

1. **Agents crossed the capability threshold** to do consequential
   work on production systems in 2024-2025.
2. **The failure mode became visible** in the same window —
   documented incidents from real deployments.
3. **Regulation has named the artifacts** that must exist (OWASP
   Dec 2025, Colorado June 2026, EU Aug 2026).
4. **The harness ecosystem** (Claude Code, MCP) shipped the hook
   primitives needed to build the enforcement layer.
5. **No dominant vendor** has productized ceremony-level
   enforcement yet.

Five forcing functions aligned; category is forming now.

## Where StepProof is early

- Provenance verifiers are partial (verify_round_marker is the only
  strict-provenance example).
- Per-harness adapters beyond Claude Code don't exist.
- Verifier library for common domains (DB, CI, deploy) is small.
- Tamper-evident audit logging is Level 1 of 5.
- Approval workflow is stubbed.

Each of these is a concrete increment; none is blocking the thesis.

## Where StepProof is mature

- Runtime handshake between MCP, hook, and runtime is battle-tested
  end-to-end (158 tests green across four levels, including real
  Claude Code sessions).
- Paired with/without methodology is runnable and produces
  observable outcomes.
- Documentation is thorough enough to transfer.
- The philosophy doc (`docs/PHILOSOPHY.md`) makes the design
  constraints explicit.

## Date stamp

2026-04-20.

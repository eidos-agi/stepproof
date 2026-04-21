# Guardrails and Content Filters

Guardrails AI, NVIDIA NeMo Guardrails, Lakera Guard, Pangea AI Guard,
and the family of libraries that filter and sanitize LLM inputs and
outputs at the content level. Adjacent to StepProof in the sense of
"runtime control over AI behavior," but solving a different problem.

## What's in this category

- **Guardrails AI.** Python library + hub of validators. Validates
  LLM output structure, PII, topic constraints, tool-call format.
  Pydantic-adjacent schema validation for LLM outputs.
- **NVIDIA NeMo Guardrails.** Policy-based runtime for LLM apps.
  Defines conversation flows and content constraints in YAML / Colang.
- **Lakera Guard.** Prompt-injection detection and content
  filtering. Real-time input/output scanning.
- **Pangea AI Guard.** Commercial content-safety platform — PII
  detection, malicious content, prompt injection.
- **Prompt Armor, Protect AI, Robust Intelligence.** Various
  commercial entries with similar value props — content inspection,
  prompt injection, data leakage.
- **Meta Llama Guard / PurpleLlama.** Model-based content classifier
  trained to flag policy-violating inputs and outputs.
- **OpenAI Moderation API.** Content classifier for policy
  violations.

## What this category does well

- **Prompt injection detection.** Catches attempts to override
  system instructions or extract system prompts.
- **PII filtering.** Redacts sensitive data from inputs and outputs.
- **Content policy enforcement.** Blocks outputs that violate
  defined categories (harm, explicit, harassment, etc.).
- **Structural output validation.** Ensures LLM output matches a
  declared schema — JSON-shape, field types, value ranges.
- **Per-token or per-message scanning.** Real-time, low-latency,
  deployable as middleware.

## What it can't do

- **Not workflow-aware.** The guardrail sees one input / one output
  at a time. No concept of "this message is step 3 of 7."
- **Not tool-aware.** Guardrails intercept text content, not the
  tools the agent calls. An agent asking to run psql isn't content
  a guardrail can inspect meaningfully — the content is the tool
  call, not the text.
- **Not evidence-aware.** Guardrails don't check "did the claimed
  work actually happen?" — that's a different semantic layer.
- **Not an audit substrate.** Some log events; none produce the
  kind of causal-chain audit log a regulator asks for on a
  multi-step ceremony.
- **Complementary, not competitive, to ceremony enforcement.** A
  StepProof-gated ceremony still benefits from content filtering
  on the agent's inputs and outputs.

## How guardrails and StepProof compose

They stack cleanly:

```
Incoming request
       │
       ▼
Guardrail layer  ── content policy, PII, injection detection
       │
       ▼
Agent (Claude Code)
       │
       ▼  (tool call)
StepProof hook   ── ceremony scope, per-step allowed_tools
       │
       ▼
StepProof runtime ── evidence + verifier dispatch
       │
       ▼  (response)
Guardrail layer  ── output PII/policy filtering
       │
       ▼
User
```

A mature deployment probably has both. Guardrails catch content
violations; StepProof catches process violations. Different
failure modes, different enforcement layers.

## Where the categories blur

Some guardrails libraries (NeMo, Prompt Security) include rudimentary
"flow enforcement" — "only allow this topic after that topic."
These are workflow-lite patterns inside a content-filtering tool.
None reach ceremony-level semantics (multi-step runbook with
verifier-per-step), but they hint at the convergent demand. Vendors
may extend toward ceremony enforcement over time.

## Why I don't consider these direct competitors

A customer evaluating "how do I stop my agent from running psql
during a migration ceremony" does not reach for a content filter.
The abstraction is wrong. The customer who wants "don't let my
agent output PII" does not reach for StepProof. Different problem,
different product.

## Known unknowns

- Whether Lakera / Pangea / NeMo will build workflow-aware
  enforcement as the category matures. Possible. Would blur the
  line.
- Whether the large cloud guardrail products (AWS Bedrock
  Guardrails, Azure AI Content Safety, Google Model Armor) evolve
  toward process enforcement. Low probability in the next 12
  months; higher thereafter.

## Representative sources

- Guardrails AI: `github.com/guardrails-ai/guardrails`.
- NeMo Guardrails: NVIDIA docs + GitHub.
- Lakera Guard: `lakera.ai` product page.
- Pangea AI Guard: `pangea.cloud`.
- Meta Llama Guard: PurpleLlama repo.
- OpenAI Moderation API: OpenAI API docs.

## Date stamp

2026-04-20.

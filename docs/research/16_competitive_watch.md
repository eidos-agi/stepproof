# Competitive Watch

Who to monitor, why, and what constitutes a threat vs an adjacency
vs an opportunity. This doc is operational — update when a watched
entity ships something relevant.

## Threat tiers

- **Tier 1 — Direct threat:** someone ships a product that covers
  the same combined properties StepProof does (see
  `15_prior_art_gaps.md`). Category is contested.
- **Tier 2 — Partial overlap:** someone ships features that reduce
  StepProof's differentiation without matching the full combo.
  Positioning needs to sharpen.
- **Tier 3 — Adjacent evolution:** a category evolves toward
  StepProof's shape without crossing the line. Watch, don't react.
- **Tier 4 — Opportunity:** a category's evolution makes StepProof
  easier to sell (e.g., regulation advances).

## Who to watch — Tier 1 / 2 candidates

### Anthropic

**Why**: owns Claude Code, owns MCP, has the most natural path to
native ceremony enforcement in the harness StepProof targets most
directly.

**Signals of Tier 1 movement:**
- "Runbook" or "ceremony" primitive in Claude Code.
- First-class ceremony state in MCP spec.
- Native PreToolUse enhancement that includes ceremony semantics.
- A blog post or SDK release describing a "keep me honest" or
  "declared-plan enforcement" pattern.

**Signals of Tier 2 movement:**
- Improved hook lifecycle with more structured state carriage.
- Agent SDK pattern for "submit evidence at step boundaries."
- Stronger tool-use training reducing drift (which shifts the
  *why* of StepProof without eliminating it — tooling is still
  needed for high-stakes process compliance).

**Monitoring cadence**: weekly during Anthropic's release cycle;
at minimum, scan every new Claude Code or SDK release notes.

### OpenAI

**Why**: Agents SDK, function calling, the competing agent
ecosystem. Slower to build Claude-Code-like harness features but
strong at orchestration primitives.

**Signals of Tier 2:** "agent checkpoints," "agent certifications,"
formal evidence-at-step patterns in the Agents SDK.

### Microsoft AGT

**Why**: already in the enterprise agent governance space; the
most obvious candidate to extend from request-level to ceremony-
level enforcement.

**Signals of Tier 1:** ceremony objects, runbook schema,
verifier fabric in the AGT feature roadmap or release notes.

**Signals of Tier 2:** expanded observability, richer per-agent
policy, extended identity binding — all moves in the right
direction without crossing into StepProof's core.

### Temporal.io

**Why**: the workflow engine most aggressively positioning for
LLM/agent workflows.

**Signals of Tier 2:** "evidence activities," "verifier activities,"
or any first-class pattern for "this step requires proof of real
state before advancing."

**Signals of Tier 3:** improved LLM activity ergonomics, better
observability, durable agent sessions — adjacent to StepProof, not
overlapping.

### Credal.ai / Prompt Security / Portal26

**Why**: enterprise AI gateways that could extend toward ceremony
enforcement as a feature.

**Signals of Tier 2:** "runbook mode," ceremony artifacts, multi-
step audit trails tied to declared processes.

### Zenity

**Why**: security-focused, Copilot Studio / Power Platform adjacent.
Could extend into multi-agent workflow governance.

**Signals of Tier 2/3:** ceremony-level features in its agent
security posture.

### Stealth startups

**Why**: the forcing functions (regulation + agent capability +
MCP standardization) make this a probable area for new company
formation in 2026.

**Signals to watch for:**
- YC batches (W25, S25 onwards) for companies with descriptions
  matching "agent compliance," "AI runbooks," "agent governance."
- Stealth-mode pre-seed / seed announcements in AI security /
  governance.

### Academic / research

**Why**: a strong paper could crystallize the category intellectually
and accelerate competitor formation.

**Signals:** arXiv preprints in cs.AI / cs.SE on agent governance,
agent verification, runtime verification for LLMs.

## Opportunity tier (Tier 4) — who to watch for tailwinds

- **EU Commission** publishing implementing regulations for the AI
  Act — every specific requirement that names logging, evidence, or
  audit trails is a StepProof selling point.
- **ISO 42001** gaining enterprise adoption — buyers seeking
  certification will ask for ceremony-level controls.
- **Anthropic / OpenAI shipping more capable agents** — raises the
  stakes of unverified agent actions, increases demand for
  enforcement.
- **Major public incident caused by agent drift** — would move
  governance up the priority list across the enterprise.

## How to act on signals

| Signal | Action |
|---|---|
| Tier 1 threat confirmed | Assess the specific feature; sharpen positioning; accelerate documented case studies; consider whether preprint/paper is needed to establish priority. |
| Tier 2 overlap | Update positioning doc; identify the defended differentiation; no product-level reaction required unless multiple Tier 2 overlaps stack. |
| Tier 3 adjacent evolution | Note in this doc; update category docs 02-13 as relevant. |
| Tier 4 opportunity | Amplify in external communication. Reference in pitches / docs. |

## Current state (2026-04-20)

No confirmed Tier 1 threats. Anthropic, Microsoft AGT, and Temporal
are all Tier 3 — evolving in the direction of parts of StepProof's
shape, none yet crossing into the combined assembly. Commercial
gateways are Tier 3.

The single item closest to Tier 2 overlap is **Anthropic's agent
tooling evolution** — they could ship Claude Code / Agent SDK
features that overlap non-trivially in the next 6-12 months.
Monitoring required; no immediate action.

## Date stamp

2026-04-20.

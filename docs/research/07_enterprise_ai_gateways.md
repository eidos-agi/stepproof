# Enterprise AI Gateways

Microsoft AGT, Credal, Prompt Security, Portal26, Zenity — commercial
platforms that sit between enterprise users/agents and LLM providers,
adding policy, observability, DLP, and cost controls. The category
most likely to adjacent-compete with StepProof if it extends toward
step-level enforcement.

## What's in this category

- **Microsoft AGT (Autonomous Grid Technology).** Microsoft's
  internal + external agent governance framework. Covers identity,
  policy, observability across agents and APIs. Positioned as the
  enterprise agent governance layer.
- **Credal.ai.** Enterprise AI gateway. LLM access brokering, data
  loss prevention, policy-per-team.
- **Prompt Security.** AI security platform; prompt-injection
  detection, data leakage prevention, governance.
- **Portal26 (formerly AIGuardian).** Agent gateway + observability +
  governance.
- **Zenity.** Low-code/no-code AI agent security for platforms like
  Copilot Studio, Power Platform.
- **Harmonic Security, Witness AI.** Similar category; gateways
  focused on enterprise SaaS LLM usage.
- **Cloud-provider gateways:** AWS Bedrock Guardrails, Azure AI
  Content Safety + policy primitives, Google Cloud Model Armor.
  Provider-native governance.

## What this category does well

- **Request-level mediation.** Sits between the agent and the LLM
  API, can block, modify, or log individual requests.
- **Data loss prevention.** PII detection, source-data-classification
  policy, block/allow based on content.
- **Cost and usage controls.** Per-user budget caps, rate limiting,
  model-routing.
- **Centralized observability.** Every LLM call visible to the
  security team; anomalies surfaced.
- **Identity-bound policy.** Agent X with role Y can call model Z
  but not model W. Integrates with corporate SSO.
- **Compliance reporting surfaces.** Dashboards for auditors,
  compliance teams.

## What it doesn't do

- **Not ceremony-aware.** Gateways see requests; they don't see
  "this is step 4 of a declared 7-step migration runbook." The
  abstraction stops at the single API call.
- **Not evidence-verification.** They inspect request/response
  content. They do not query external systems to verify agent
  claims. No `verify_migration_applied` semantics.
- **Not tool-call-boundary enforcement in the harness.** A gateway
  mediates LLM API calls; it does not intercept the agent's native
  `Write` tool in Claude Code before it touches disk. That's
  client-side — outside the gateway's visibility.
- **Not a runbook artifact.** Policies are per-project rules, not
  "this is the declared process for a database migration, and the
  agent will be blocked from advancing without evidence."

## Why this category matters to StepProof positioning

These are the **most likely direct competitors** in an enterprise
sale. When a VP of engineering asks "we have AI agents in prod, how
do we govern them?", the vendor landscape they survey includes
these gateways. StepProof has to articulate what a gateway can't
do — ceremony enforcement, tool-boundary scope, evidence-from-real-state,
auditable step progression.

The distinguishing pitch:

> "Gateways govern the wire. We govern the work. A gateway sees
> that your agent called Anthropic's API. We see that your agent
> ran step 3 of a migration runbook and the verifier confirmed the
> migration tracking table shows the new row."

In a large enterprise, both layers are probably deployed. Gateway
for DLP, cost, centralized observability. StepProof for process
compliance on high-stakes multi-step work.

## Where they'd directly compete

If Microsoft AGT (the most likely vector) adds:
- First-class runbook / ceremony objects
- Per-step tool scope that fires at the agent harness layer (not
  just the LLM API layer)
- Evidence verification against real external state

...that would cover a meaningful fraction of StepProof's value. As
of this research's date, AGT documentation emphasizes request-level
policy, identity, and observability — not ceremony-level enforcement.

Same threat model for cloud-provider governance (Bedrock, Azure AI,
Google Model Armor): if they extend from content-policy to
step-level enforcement with verifier fabric, they become direct
competitors. Less likely than AGT because their abstraction is
model-as-service, not agent-as-ceremony.

## Acquisition dynamics

Enterprise gateways acquire (or get acquired by) adjacent tooling
as the category consolidates. StepProof's plausible futures include:

- Standalone OSS + commercial product (Vanta-shape, Styra-shape).
- Acquired by a gateway to provide the ceremony layer.
- Absorbed into Anthropic / OpenAI's native tooling.

Relevant to strategy; see `16_competitive_watch.md`.

## Known unknowns

- Whether Microsoft AGT's public surface currently includes ceremony
  objects in some form. Documentation has been uneven; a direct
  product-page review quarterly is warranted.
- Whether any gateway has shipped a "runbook mode" or equivalent
  before this corpus is updated next. Low probability in the next
  90 days; non-zero over 12 months.
- Whether the cloud providers will build this natively to capture
  agent-governance demand on their platforms.

## Representative sources

- Microsoft AGT: Microsoft's official AI governance documentation.
- Credal.ai: product pages and GitHub OSS components.
- Prompt Security, Portal26, Zenity: vendor websites and product
  demos.
- AWS Bedrock Guardrails, Azure AI Content Safety, Google Model
  Armor: cloud-provider docs.

## Date stamp

2026-04-20.

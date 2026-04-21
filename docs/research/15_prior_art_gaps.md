# The Specific Gap StepProof Addresses

A tighter statement of what's missing in the combined landscape.
When someone asks "what makes StepProof novel," this is the
answer — compressed, checkable, and honest about what's not
novel in isolation.

## The compressed claim

**No other deployed system we've found assembles the following five
properties into a coherent ceremony-enforcement layer:**

1. **Declared multi-step ceremony as a first-class artifact**
   (workflow engines have steps, but not ceremony semantics).
2. **Per-step tool scope enforced at the agent harness boundary**
   (hooks exist; ceremony-aware hooks do not, outside StepProof).
3. **Verifiers that read real external state** to confirm claims
   (workflow engines trust return values; guardrails inspect
   content; nothing reads ground truth and compares to the agent's
   claim as a standard pattern).
4. **Tamper-evident audit log** produced as a byproduct of
   operation, structured for regulator consumption (some systems
   log; few produce a causally-ordered, verifier-stamped chain).
5. **Paired with/without evaluation methodology** treating
   enforcement-on vs enforcement-off as a measurable A/B, against
   server-side ground truth (no prior work we've found publishes
   this as a standard evaluation primitive for agent governance).

Each property alone has antecedents. The combination, integrated
into a running harness, does not.

## Property-by-property novelty check

### 1. Declared ceremony

Antecedents:
- Workflow-engine DAGs (Temporal, Airflow).
- DevOps runbooks (Ansible playbooks, GitHub Actions workflows,
  operational runbooks in Notion/Confluence).
- Policy-as-code declarations (OPA Rego).

What's novel: treating the *ceremony* (not just the workflow)
as the primary artifact, with step-level evidence, verifier, and
tool-scope declarations unified under one template, designed for
agent-executed work.

### 2. Ceremony-aware tool scope at harness boundary

Antecedents:
- OpenAI/Anthropic function calling per-request.
- Claude Code session-level `--allowed-tools`.
- Linux capability bounding in containers.

What's novel: binding the tool scope to **which step of which
ceremony is active right now**, dynamically, via a hook that
reads a shared state file. Per-call scoping conditioned on
per-step state.

### 3. Real-state-reading verifiers

Antecedents:
- CI systems that run tests against real code.
- Migration trackers that query the real database.
- Audit firms manually checking.
- Cosign verifying signatures on real artifacts.

What's novel: packaging verifier fabric as a **standard capability
tier** (Tier 1/2/3) with a library of reusable verifiers, callable
from any step in any ceremony, with consistent evidence schemas.

### 4. Tamper-evident audit log as byproduct

Antecedents:
- Certificate Transparency logs.
- Append-only immutable databases (AWS QLDB).
- SOC 2 / ISO audit trails in compliance tooling.
- OPA decision logs.

What's novel: the audit log is *causally ordered by ceremony step*,
and every entry is cryptographically or structurally linkable to a
specific verifier decision. The log's structure matches the
ceremony's structure. (Today at Level 1 integrity; targetable
upgrade to Level 3+.)

### 5. Paired with/without evaluation

Antecedents:
- A/B testing in product development.
- Ablation studies in ML research.
- Control-and-treatment clinical trial design.

What's novel (and potentially publishable): applying the paired-
run methodology to **agent behavior under a governance layer**,
with server-side ground truth as the verifier-of-the-evaluation.
We have not found prior work that publishes this as an evaluation
primitive for AI governance tooling specifically. The repo's
`challenges/` framework is a candidate for formalization into a
benchmark.

## How to reduce uncertainty in the "novel combination" claim

We're confident nothing in our surveyed categories (docs 02-13)
assembles all five. We are less confident that *nothing anywhere*
does — research we haven't seen, internal tools at labs, stealth
startups. How to check:

### Quarterly
- arXiv search: `"agent governance" OR "ceremony enforcement"
  "verifier" "real state"`
- arXiv search: `"LLM runbook" "provenance" "step"`
- YC batch announcements for "agent governance" / "AI compliance"
  companies.
- Product Hunt, Hacker News Show HN for new entrants.

### Targeted
- Anthropic and OpenAI engineering blogs for internal-tool mentions.
- GitHub Topic / Trending for `agent-governance`, `llm-runbook`,
  `agent-verification`.
- The OWASP Agentic AI working group's follow-up publications —
  if they name implementations, check them.

### Direct
- Conversations with buyers who are evaluating agent governance —
  which vendors are they looking at?
- Conversations with academics in AI safety / governance who would
  know about work-in-progress.

## The honest "could be wrong" list

- There might be a stealth startup building this exact thing. Probability:
  nonzero, probably 20-40% given the forcing functions.
- There might be internal tooling at big labs (Anthropic, OpenAI,
  Google) that does this shape. Probability: plausible (40-60%);
  unclear when / if productized externally.
- The paired-with/without methodology might have a prior academic
  publication we haven't found. Probability: 20-30%. Deserves a
  proper lit search before any public claim.
- Commercial gateways (AGT, Credal, etc.) might have shipped
  ceremony features in the last 3 months that aren't yet in their
  public documentation. Probability: 10-20%.

The combined probability "at least one of these makes StepProof
non-novel on the combined-assembly axis" is meaningful but not
overwhelming. Treat novelty as "credible but unverified" and
establish priority through timestamps, preprints, and case studies.

## The defensible even-if-not-novel claim

Even if the combination exists elsewhere, StepProof-the-repo has:
- A clean open-source implementation.
- A documented methodology for evaluation.
- A lived dogfood demonstration of the enforcement biting the
  authoring hand.
- A philosophy document establishing the why.
- A runnable example that a reader can execute in minutes.

Those are moats regardless of whether the shape is novel.

## Date stamp

2026-04-20.

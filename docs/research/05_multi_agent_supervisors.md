# Multi-Agent Supervisor Patterns

CrewAI, AutoGen, LangGraph, OpenAI Swarm, and the family of designs
where "one agent supervises another." Closest to StepProof's intent
("make sure the agent does what it said"), but differs in a way that
matters architecturally: **the supervisor is also an agent.**

## What's in this category

- **CrewAI.** Role-based multi-agent framework. Agents have
  specialized roles (researcher, writer, reviewer) and delegate to
  each other. A reviewer agent can critique a writer agent.
- **Microsoft AutoGen.** Conversational multi-agent framework.
  Agents talk to each other in a chat-shaped environment to
  accomplish tasks. Supervisor patterns implemented as "one agent
  asks another to check."
- **LangGraph (LangChain).** DAG-based agent orchestration. Supports
  supervisor nodes that route decisions.
- **OpenAI Swarm / Agents SDK.** OpenAI's lightweight multi-agent
  framework. Agents hand off to each other; "triage" agents that
  route work.
- **General "critic" pattern.** Research and production patterns
  where one LLM call generates and another LLM call reviews. Often
  rolled into a single framework.

## What this category does well

- **Division of labor.** Different agent roles can be specialized
  and tuned independently. A "reviewer" prompt can focus narrowly
  on quality checks.
- **Workflow expressiveness.** Complex tasks get decomposed into
  interacting agent dialogs.
- **Approximates "four eyes" review for LLM output.** Two different
  prompts looking at the same output reduces certain error rates.
- **Works within model capability.** Supervisor agents can catch
  things that simpler rule-based checks can't (e.g., "does this
  PR description make sense?").

## Why this category doesn't solve StepProof's problem

**The supervisor is also an LLM.** Every failure mode of the worker
is also a failure mode of the supervisor:

- Supervisor drifts under pressure.
- Supervisor can be convinced by the worker's explanation.
- Supervisor shares the same training biases as the worker.
- Supervisor interprets vague instructions the same way the worker
  does.
- If the worker is prompt-injected, the supervisor often is too.
- If you swap the base model, both worker and supervisor's behavior
  changes together.

Empirically: in published evaluations of agentic reliability,
supervisor patterns reduce error rates meaningfully but do not
approach the near-zero rate required for high-stakes process
compliance. 90% compliance is not enough when the 10% failure case
is "raw psql against production."

**Structurally: the supervisor has no independent source of truth.**
It can reason about what the worker says. It cannot read the real
migration tracking table. It can be told "the tests passed" and
believe it. A StepProof verifier reads the tests' actual output from
disk; the supervisor agent does not.

## Where this category adds value even with StepProof

The two patterns stack cleanly. An agent operating under StepProof
enforcement could still benefit from a supervisor agent for
**qualitative** checks that are inherently judgmental:

- Is this commit message coherent?
- Does this architectural decision make sense?
- Does this code review find meaningful issues?

These are valid Tier-2 verifier tasks in StepProof's model (see
`docs/VERIFIERS.md`). StepProof's verifier fabric is explicitly
designed to accommodate LLM-based judgments at Tier 2 — the LLM
judgment is the input to a structured pass/fail decision, not the
final authority.

The key distinction: StepProof uses supervisor agents as **judges
of unstructured evidence** where no deterministic check works. It
does not use them as **the primary gate** between steps. The
primary gate is always a deterministic read against real state
wherever possible.

## Representative architectural pattern contrast

**Supervisor-only pattern (CrewAI-style):**

```
Worker ── produces artifact ──▶ Supervisor agent
                                (LLM judges)
                                    │
                          allow/deny/feedback
                                    │
                                    ▼
                              Worker continues
```

**StepProof pattern:**

```
Worker ── produces evidence ──▶ Verifier (deterministic,
                                reads real state)
                                      │
                              pass/fail
                                      │
                                      ▼
                              Runtime advances the run
                              (or keeps it stuck)
```

The second is strictly stronger for anything where real state
exists to verify against.

## Known unknowns

- Whether supervisor patterns with sufficiently deep model stacks
  approach structural-enforcement-level reliability. Probably not at
  current capability; maybe at future capability, but the cost of
  running N-deep supervisor stacks on every step is prohibitive for
  most production deployments.
- Whether "supervisor reads real state" patterns (supervisor agent
  with database access, Git access, etc.) blur this distinction.
  Technically yes, but that just makes the supervisor into a
  verifier — at which point the value is the real-state read, not
  the agent-ness.

## Representative sources

- CrewAI docs.
- Microsoft AutoGen repo and papers.
- LangGraph docs.
- OpenAI Agents SDK / Swarm framework.

## Date stamp

2026-04-20.

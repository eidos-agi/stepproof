# Workflow Engines with LLM Steps

Temporal, Prefect, Airflow, Dagster — durable workflow orchestrators
being used to run multi-step LLM workflows. Architecturally the
closest adjacent category to StepProof, because both have durable
multi-step execution. Different in a specific way that matters.

## What's in this category

- **Temporal.io.** Durable workflow engine. Originally for
  microservice orchestration; heavily adopted for LLM workflows in
  2024-2025. Workflows are code (TypeScript, Python, Go). Activities
  are retryable, durable. "Activities" can be LLM calls.
- **Prefect.** Python-native workflow orchestrator. Popular in data
  engineering. Tasks, flows, retries, observability. LLM calls
  become tasks.
- **Apache Airflow.** DAG-based workflow scheduler. Older
  generation; widely deployed in data engineering. Airflow operators
  for LLMs exist.
- **Dagster.** Asset-centric data orchestration. Tasks are "ops";
  higher-level asset lineage. Some adoption for ML/LLM pipelines.
- **Windmill / n8n / Zapier for AI.** Lower-code workflow tools with
  LLM integrations. Lightweight end of the category.
- **LangGraph (from LangChain).** DAG-based LLM agent orchestration
  specifically for LLM workflows. Combines agent-orchestration and
  workflow-engine concerns.

## What this category does well

- **Durable execution across failures.** If the runtime dies
  mid-workflow, it resumes. Much better than in-memory agent
  sessions that die with the process.
- **Explicit step ordering.** DAGs or sequential workflows encode
  *which* step runs *when*. StepProof's template concept
  corresponds to a workflow definition.
- **Retries and error handling at the step level.** First-class
  support for "retry this step up to N times with exponential
  backoff."
- **Observability.** Every workflow run is queryable; you can see
  which step failed and why.
- **Audit trail by default.** Workflow history is persisted in the
  engine's storage (Temporal's event history, Airflow's DB).

## What it can't do

- **Doesn't verify agent claims against real state by default.** An
  LLM activity in Temporal returns whatever the LLM returned. The
  workflow trusts that return value unless the activity is
  hand-written to verify. There is no built-in "verifier that reads
  external state and rejects if the claim doesn't match."
- **Doesn't bind the agent at the tool-call boundary.** The agent
  inside an LLM activity can call any tool the activity allows.
  There is no per-step scoping of tools — tools are whatever the
  activity code exposes.
- **Workflow is CODE, not a declaration.** This is a feature in many
  contexts — flexible, expressive — but it means the ceremony is
  not a first-class auditable artifact. You can't hand a regulator
  a Temporal TypeScript workflow and say "this is our ceremony."
  You have to translate it.
- **No concept of evidence as a gate between steps.** A step
  finishes when its code returns. Whether the work was actually
  done is the code's problem.
- **No tool-call interception.** The workflow engine doesn't sit
  between the agent and its tools. If the activity code gives the
  LLM a psql tool, the workflow engine doesn't know or care.

## How this category and StepProof relate

Temporal-and-friends are **complementary**, not competitive.

- A StepProof ceremony could run AS a Temporal workflow. Each step
  of the StepProof runbook maps to a Temporal activity. Temporal
  handles durability, retries, distribution. StepProof handles
  verifier dispatch and hook enforcement.
- Workflow engines don't try to solve "is the LLM telling the
  truth about completion?" — that's explicitly outside their
  concern. StepProof fills that gap.

A typical pattern in a mature deployment might be:

```
Temporal workflow
  ├── activity 1: invoke agent in Claude Code session
  │      (agent runs under StepProof enforcement — see repo's dogfood test)
  ├── activity 2: run StepProof verifier against real state
  ├── activity 3: advance run or escalate
  └── ...
```

StepProof is the ceremony-integrity layer. Temporal is the
long-running-workflow layer. Different concerns, stackable.

## Where they'd compete

If Temporal shipped a first-class **"LLM activity with evidence
verification"** pattern — activities that take a declared evidence
schema and validate the LLM's output against real state before
advancing — that would eat a meaningful fraction of StepProof's
value. As of this research's date, they have not.

Same threat from Prefect, Airflow, Dagster. The engineering cost to
add this feature to an existing workflow engine is moderate — the
hard part is the domain-specific verifiers, not the workflow
machinery. If they productize domain-verifier libraries, they
become competitors.

## Known unknowns

- Whether LangGraph's evolution will include structural enforcement.
  LangGraph is the most likely vehicle to ship something like this
  inside an existing framework.
- Whether Temporal's recent agent-focused positioning will include
  evidence-verification primitives. Their blog suggests yes in
  direction; productization unclear.
- How much of the current demand is being served by hand-rolled
  "Temporal workflow + custom verifier code" implementations that
  never get standardized. Likely significant; invisible to research.

## Representative sources

- Temporal docs — workflow-and-activities architecture.
- Prefect docs — flow/task model.
- Airflow Python operators for LLMs.
- LangGraph documentation — DAG-based agent orchestration.

## Date stamp

2026-04-20.

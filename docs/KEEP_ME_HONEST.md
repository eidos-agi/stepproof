# "Keep Me Honest" — Agent-Declared Plans as First-Class Runbooks

> The agent had every tool it needed — guardrails, topology docs, incident logs, deploy ceremonies — and ignored all of them under pressure.

The canonical "keep me honest" failure looks like this: the agent has a coherent plan at the start (apply migration → deploy → verify → trigger extraction → check row counts). It drifts from that plan under pressure — raw `psql` instead of migration tooling, ad-hoc scripts instead of the daemon — and spends hours debugging the consequences. If the agent had **bound itself to its own declared plan** at hour zero, each drift would have hit a gate. That's the pattern this doc describes.

## The Reframing

The early StepProof docs assumed runbooks are written by humans ahead of time, and workers slot into them. That's right for regulated operations. It's wrong as the default.

Agents already plan. Claude Code writes TODO lists. Cursor agents enumerate steps. Any capable coding agent, given a non-trivial task, produces a plan before it acts. What they lack is a mechanism to **bind themselves to their own declared intent** — to say "here's what I'm about to do, keep me honest," and have something structurally prevent drift.

That's the primitive. StepProof supports two modes of binding:

| Mode | Source of truth | When |
|------|-----------------|------|
| **Keep me honest** | Agent-declared plan, validated at submit time | Default. Novel tasks, exploratory work, most day-to-day. |
| **Templated** | Human-authored, version-controlled `RunbookTemplate` | Regulated operations where compliance dictates the steps (DB migrations, prod deploys, SOC 2 workflows). |

Both modes produce the same `WorkflowRun` object. The same verifier dispatch, the same hooks, the same audit log. Only the **provenance of the plan** differs.

## What "Keep Me Honest" Looks Like

An agent submits a plan via MCP:

```python
stepproof_plan_declare(
    intent="Add a Fleetio connector to service X — code change, tests, staging deploy.",
    steps=[
        {
            "step_id": "s1",
            "description": "Write connector code and unit tests",
            "required_evidence": ["branch_name", "test_run_id"],
            "verification_method": "verify_tests_green",
            "allowed_tools": ["Edit", "Write", "Bash"],
            "ring": 1,
        },
        {
            "step_id": "s2",
            "description": "Open PR and wait for CI",
            "required_evidence": ["pr_url", "ci_run_id"],
            "verification_method": "verify_ci_green",
            "allowed_tools": ["mcp__github__create_pull_request"],
            "ring": 1,
        },
        {
            "step_id": "s3",
            "description": "Deploy to staging",
            "required_evidence": ["deploy_id"],
            "verification_method": "verify_deploy_succeeded",
            "allowed_tools": ["mcp__railway__deploy_staging"],
            "ring": 2,
        },
    ],
    environment="staging",
)
```

StepProof validates at submission. If the plan passes, it becomes a runbook — the agent's contract for this session.

## Plan Validation — The Structural Checks

A declared plan is accepted only if every step satisfies:

1. **Verifiability.** `verification_method` references either (a) a registered Tier 1 verifier, or (b) an inline Tier 2 prompt with a structurally-valid evidence schema. No step can be "verified" by the agent itself.
2. **Evidence specificity.** `required_evidence` lists at least one key that maps to a lookup into a real adapter (deploy IDs, CI run IDs, commit hashes, migration names). Empty evidence or free-text-only evidence is rejected — GUARD-002.
3. **Ring coherence.** Every step declares its ring. Ring-3 steps in a declared plan require either (a) the plan-author's trust score above threshold, or (b) explicit human approval at plan-submit time.
4. **Allowed-tools sanity.** `allowed_tools` cannot include `Bash` for a step whose declared ring is 0. Ring promotions from Bash require the step's ring to match the declared bash commands.
5. **No verifier bypass.** A plan cannot register a custom `verification_method` unless it's one of the pre-registered Tier 1 names or a Tier 2 prompt conforming to the read-only verifier contract. The agent can't define a verifier that rubber-stamps its own evidence.
6. **Guardrail compliance.** Active guardrails (`GUARD-001` through `GUARD-005`) are evaluated against the whole plan at submission. A plan that writes to production without staging verification is rejected, full stop.

Plans that fail validation return a structured rejection with the specific violation. The agent fixes or escalates.

## The Amendment Model

Plans can be amended mid-run. Three types:

| Amendment | Rule | Approval |
|-----------|------|----------|
| **Narrowing** | Add a verifier, tighten `allowed_tools`, raise evidence requirements | Auto-accepted, audited |
| **Lateral** | Rename a step, clarify a description, adjust `timeout_seconds` | Auto-accepted, audited |
| **Expanding** | Add a step, weaken a verifier, lower a ring, widen `allowed_tools` | Requires human approval for Ring 2+, auto-accepted with audit for Ring 0–1 |

Amendments write audit records with the diff. A run's history reads as: "plan declared → step verified → amendment accepted → step verified → …" A run whose amendments trend toward weakening is a signal for policy escalation.

## Why This Shape

1. **Scales with usage.** No catalog of pre-authored runbooks needed. Authorship happens in the moment, by the entity that knows what it's trying to do.
2. **Self-binding.** The agent saying "keep me honest" is meaningful — it's committing to its own stated intent. Drift becomes detectable because the baseline is explicit.
3. **Meta-circular.** Agents know they will bend under pressure (the user's thesis at the top of this conversation). "Keep me honest" is the structural request to prevent that bend. It's the agent outsourcing the self-control it lacks.
4. **Composable with templates.** A worker can say "start with `rb-db-migration-and-deploy` as my base, amend with 2 more steps." Templates become seed patterns, not the whole story.

## Why This Doesn't Fully Solve The Problem

The honest caveat: **a bad plan gets perfectly enforced.** If an agent declares `{step_id: s1, description: "delete production database", ring: 3}` and that plan clears validation, StepProof will shepherd the agent through it faithfully.

Three defenses:

1. **Validation-time guardrails.** Guardrails operate at plan submission, not just at execution. `GUARD-005` (shadow-first) and new guardrails that catch destructive-intent patterns at the plan shape level.
2. **Human approval gate on high-risk plans.** Any plan that touches Ring 3 with no template ancestor routes to human approval before the first step runs. This is "keep me honest" inheriting the templated mode's compliance posture when the stakes require it.
3. **Review by a separate validator agent.** A validator agent (read-only tools, different context) reads the plan at submission and flags suspicious patterns. This is the builder-validator pattern from the hooks-mastery lessons applied to *plans*, not just code. The validator's flag doesn't auto-deny; it escalates.

So the full shape is: **agent authors plan → StepProof validates structurally → validator agent reviews for intent plausibility → human approves Ring-3 plans that lack template ancestors → run proceeds under enforcement.** Four gates, each catching different classes of failure.

## What This Changes in the Existing Design

- **`stepproof_run_start`** gets two variants: `(template_id=...)` for templated mode, `(plan=...)` for keep-me-honest mode. Or we split into `stepproof_run_start_template` + `stepproof_plan_declare` — probably cleaner.
- **`RunbookTemplate`** and declared plans share a schema but differ in provenance. The DB tracks `source: "template"` vs `source: "declared"` on every run.
- **`OPEN_QUESTIONS.md §4 (Runbook authorship)`** is now substantially answered: the default is in-session declaration; templates are the compliance-gated exception.
- **Guardrails get a new evaluation surface.** Previously they fired at action time via the policy engine. Now they also fire at plan-submit time.
- **The audit log** gets a new event type: `plan.declared` and `plan.amended`, with full content-addressed payloads so any run can be traced back to the intent that authorized it.

## Naming

If this is the primary mode, the phrase matters. Candidates:

- `stepproof_keep_me_honest(plan)` — direct, a little cute
- `stepproof_plan_declare(plan)` — clinical, mirrors API conventions
- `stepproof_commit(plan)` — short, has weight
- `stepproof_bind(plan)` — evokes the self-binding aspect

Recommendation: **`stepproof_keep_me_honest`** as the user-facing slash command (`/keep-me-honest`) and public MCP tool name. It encodes the mental model. `stepproof_plan_declare` as the internal/API name for the same action. The cute name teaches; the clinical name implements.

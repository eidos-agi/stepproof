# Open Questions — How StepProof Actually Works

The smoke tests prove plumbing. They do not prove StepProof works on real workers in real environments. This doc works through the three hardest seams honestly.

Real observed sessions show the concrete shape of what goes wrong when these seams aren't closed: environment cross-wiring (classification failure), raw-psql bypass (action-classification failure), silent null violations (evidence-freshness failure), zombie containers persisting old code (topology-awareness failure).

## 1. Action Classification — The Bedrock

### The problem

A worker who wants to run a migration can do it many ways. Canonically: `psql -c "..."`. But also:

- `bash -c 'psql ...'`
- `echo "$SQL" | psql`
- A Python script that imports `psycopg`
- A shell alias or function the worker wrote itself
- An uncategorized MCP tool that happens to reach a production DB

If we can't classify these into the same action class (`database.write` → Ring 2/3), the ring gate is decorative.

### Three approaches

| Approach | What it does | Tradeoff |
|----------|--------------|----------|
| **A. Tool allowlist via MCP** | Ship sanctioned MCP tools (`stepproof__cerebro_migrate`). Raw `Bash` either denied or lands in Ring 3 by default. Workers operate through named tools; each MCP tool is classified at registration. | High correctness, low flexibility. Every risky operation needs a wrapped MCP tool. |
| **B. Semantic classifier** | Parse the `Bash` command, match against regex patterns, classify. | Brittle. Workers evade with pipes, env substitution, `eval`. And ADR-0001 forbids LLM in the enforcement path, so we can't just Haiku-classify it. |
| **C. Intent declaration** | Every Ring 1+ action requires the worker to first call `stepproof_intent_declare(intent)`. StepProof evaluates the intent, returns a one-shot token, worker attaches the token to the actual tool call. | Adds a step to the worker loop. Compensates with a structural guarantee: no intent token, no Ring 1+ action. |

### The direction

**A + C combined, not either alone.**

- Named MCP tools carry static classifications (Ring, action_type) at registration. The Claude Code adapter reads the classification from the tool's metadata. This is cheap and deterministic.
- Raw `Bash` defaults to Ring 3 per ADR-0002 — blocked without an active runbook and an intent declaration. The worker who really needs raw bash declares intent, naming what they're about to do; the declaration is audited.
- `Write`, `Edit`, `NotebookEdit` to specific paths carry path-based classifications (writes to `migrations/` are Ring 2, writes to `docs/` are Ring 1, etc.).

What this rules out: semantic classification of free-form bash as the primary mechanism. It's too evadable, and it violates ADR-0001.

What this requires:
- An `action_classification.yaml` shipped by the adapter, mapping named tools and path globs to action_type + ring.
- An `intent_token` concept — short-lived (single-use), bound to a `run_id` and a declared `action_type`.
- MCP tool authors declare ring + action_type in their tool manifest (we can propose this as a minor MCP extension; until adopted, StepProof ships its own classification override file).

### What I don't know yet

- Whether Claude Code's agent will tolerate the extra `intent_declare` hop gracefully, or get confused. Testable quickly by building it.
- How to classify fan-out actions — one `Write` that updates a migration + a deploy file + tests. Probably the highest-ring component wins.

## 2. The Denial-To-Retry Loop — The UX Test

### The problem

`PreToolUse` returns exit 2 with a stderr message: *"Use `cerebro-migrate-staging` instead; raw psql is blocked at step s3."* The Claude Code agent sees this as a tool error. What happens next?

Three possibilities:
- **Good:** Agent reads the message, picks the suggested tool, continues. Ideal.
- **Mediocre:** Agent retries the same denied command 1–3 times, gives up, picks the suggested tool. Wastes tokens, works eventually.
- **Bad:** Agent loops on the denied command, or panics and escalates to the user for every denial. StepProof becomes friction, not governance.

### The direction

**Don't predict agent behavior — instrument it.**

- Every denial writes an audit event. The `reason` and `suggested_tool` are in the record.
- Every tool call that follows a denial within N seconds is correlated — did the worker pick the suggested tool, try something else, or retry the denied thing?
- Metric: `denial_recovery_rate` = (denial followed within T seconds by suggested_tool usage) / total denials.
- Behavioral rule: if `denial_recovery_rate < threshold` or `retry_count > N`, escalate to human — the worker isn't adapting.

This turns an unknowable design question into a measured operational signal. We can't know how the agent will behave at design time. We can observe it and let policy react.

### What makes the deny message effective

Empirically-testable hypotheses (for Phase 2):
- Name the suggested alternative by its exact MCP tool name, not a prose description.
- Include a short reason ("because this step requires sanctioned tooling") — agents pattern-match on "because X" and adjust.
- Don't include long remediation essays; short messages correlate with faster recovery.

### What I don't know yet

- The actual `denial_recovery_rate` baseline. Has to be measured.
- Whether there's a failure mode where the worker asks the human "StepProof blocked this, should I bypass?" — that would be catastrophic. An adapter-level hint in the system prompt ("denials are not asking for permission; they're terminal for this path") might be necessary.

## 3. Evidence Freshness — Verifiers That Actually Verify

### The problem

My Tier 1 verifiers today accept any `deploy_id=dep_456`. The worker could fabricate the ID. The verifier passes. The audit log records a "verified" step that never happened.

This is the gap between *smoke-test verifier* and *real verifier*: the real verifier must pull current state from an authenticated source of truth, using the evidence as a **lookup key**, not as the fact itself.

### The direction

**`EvidenceAdapter` plugin interface, credential-bearing, per-deployment configured.**

```python
class EvidenceAdapter(Protocol):
    name: str
    def healthcheck(self) -> bool: ...

class RailwayAdapter(EvidenceAdapter):
    name = "railway"
    def __init__(self, token: str): ...
    async def get_deploy(self, deploy_id: str) -> DeployStatus: ...

class CIAdapter(EvidenceAdapter):
    name = "github-actions"
    def __init__(self, token: str, repo: str): ...
    async def get_run(self, run_id: str) -> CIRunStatus: ...

class ReadOnlyDBAdapter(EvidenceAdapter):
    name = "staging-db-ro"
    def __init__(self, dsn: str): ...
    async def query(self, sql: str, params: tuple) -> list[dict]: ...
```

Verifiers declare their required adapters. Dispatcher injects them. A verifier cannot run without its declared adapters configured — by design, not convention.

```python
@register("verify_migration_applied", Tier.TIER1, requires=["staging-db-ro", "railway"])
async def verify_migration_applied(evidence, context, db, railway):
    count = await db.query_scalar(
        "SELECT COUNT(*) FROM schema_migrations WHERE name = ?",
        (evidence["migration_name"],),
    )
    deploy = await railway.get_deploy(evidence["deploy_id"])
    return {"status": "pass" if count >= 1 and deploy.status == "SUCCESS" else "fail", ...}
```

**Key invariants:**
- Adapters are read-only by interface. The `RailwayAdapter` exposes `get_deploy`, not `deploy`. If a write adapter exists, it goes to the worker, not the verifier (GUARD-001).
- Adapters authenticate with credentials from the StepProof daemon's env/secret store, not from the worker. The worker can't inject credentials that reach the verifier.
- Adapter outputs are recorded verbatim in the verifier result's `artifacts` field. Audit replay can reproduce the verification decision.

### What I don't know yet

- How adapters bootstrap — ship a `.stepproof/adapters.yaml` with DSN + token refs? Pull from a vault? First-class cloud-provider credentials module?
- Whether to ship common adapters in-tree (Railway, GitHub Actions, Vercel, Supabase, Postgres-RO) or as separate packages.
- How to fail-safe when an adapter is down. A verifier whose adapter is unreachable returns `inconclusive`. Policy decides whether `inconclusive` means "block" or "allow with follow-up."

## What This Commits Us To

For Phase 2 to be meaningful, we have to:

1. Ship a real `PreToolUse` adapter that enforces ring-based classification using an `action_classification.yaml` + intent-declaration mechanism.
2. Ship one real `EvidenceAdapter` end-to-end (Railway is the most immediate — we already use it) and wire one Tier 1 verifier that actually calls it.
3. Run the denial-retry loop in a live Claude Code session, measure `denial_recovery_rate` manually, tune the deny-message format.

Without those three, StepProof is a good design. With them, it starts proving itself.

## Things Deliberately Postponed

- **Approval routing** (Slack/web/mobile) — phase 3.
- **Runbook authorship ergonomics** — phase 3; the `runbook-author` meta-agent is the right answer but not the path for today.
- **Policy bundle distribution / signing** — phase 4.
- **OPA/Cedar backends** — YAML rules are sufficient until the rule set exceeds what YAML can express.
- **Multi-runbook concurrency** — one run per session for now; the audit log is already keyed correctly for future fan-out.

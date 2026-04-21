# Deploy StepProof to Your Project

Pragmatic first-use guide. Assumes you have a real project and a
real multi-step workflow you want agents to follow reliably.

**Start at Tier 0.** No hook, no session restart, ~5 minutes of
setup. You get declared ceremonies, evidence at each step, a real
audit log. If you later want real-time denial of off-scope tool
calls, add Tier 1 — the hook — for specific high-stakes ceremonies
only.

Read [docs/TIERS.md](TIERS.md) first if you want the full tradeoff.
The tl;dr: **Tier 0 catches the common failure modes at the step
boundary (agent can't advance without real evidence). Tier 1 adds
real-time prevention during the ceremony. Tier 2 adds cryptographic
attestations. Most teams need Tier 0.**

---

## Tier 0 — the 5-minute install

### Step 1. Install the StepProof CLI + runtime

```bash
uv tool install stepproof          # or: pipx install stepproof
```

Confirm:

```bash
stepproof --help
```

### Step 2. Drop a runbook into your project

Copy the starter template:

```bash
mkdir -p examples
cp /path/to/stepproof/examples/rb-migration-deploy-mvp.yaml \
   examples/rb-migration-deploy-mvp.yaml
```

Or write your own. A runbook is just a YAML file with steps,
allowed_tools, required_evidence, and verification_method. See
`examples/rb-repo-simple.yaml` for a minimal 3-step template.

### Step 3. Register the MCP

Write `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "stepproof": {
      "type": "stdio",
      "command": "stepproof",
      "args": ["mcp"],
      "env": {
        "STEPPROOF_STATE_DIR": "/absolute/path/to/project/.stepproof",
        "STEPPROOF_RUNBOOKS_DIR": "/absolute/path/to/project/examples"
      }
    }
  }
}
```

**That's it for Tier 0.** No `stepproof install` command run. No
hook files. No `.claude/settings.json` modification. The MCP spawns
on demand the first time the agent calls it.

### Step 4. Restart Claude Code (once)

Quit and relaunch in the project directory. Claude Code reads
`.mcp.json` at session start.

### Step 5. Run a ceremony

Ask the agent (in the new session):

> *"Start a run against `rb-migration-deploy-mvp` and walk the steps.
> Submit structured evidence at each step."*

The agent calls `mcp__stepproof__stepproof_run_start`,
`mcp__stepproof__stepproof_step_complete` at each step boundary,
and the runtime dispatches verifiers against the evidence.

### Step 6. Read the audit log

```bash
sqlite3 .stepproof/runtime.db \
  "SELECT substr(timestamp,12,8) AS t, action_type, decision, policy_id, substr(reason,1,80) AS reason \
   FROM audit_log ORDER BY timestamp DESC LIMIT 30;"
```

That's your compliance artifact. Timestamped, verifier-stamped,
written by the runtime, not by the agent.

---

## What Tier 0 prevents

| Failure mode | How |
|---|---|
| Agent skips a step | `current_step` is strict; `step_complete` with wrong step_id returns 409 |
| Agent claims completion without evidence | Verifier reads real state; returns fail; run stuck |
| Agent produces evidence in wrong shape | `required_evidence` keys enforced at runtime |
| Agent drifts under vague prompts | Caught at step boundary — verifier rejects the claim |
| Ambiguous completion narrative | Audit log is machine-readable ground truth |

## What Tier 0 does NOT prevent

| Failure mode | Why | When to add Tier 1 |
|---|---|---|
| Agent uses off-scope tool mid-step (e.g. `rm -rf`) | No hook to deny in real time | When mid-step side effects are unacceptable |
| Agent uses `psql` when `cerebro-migrate` was sanctioned | Same — Tier 0 sees it in audit but doesn't block | When you want real-time prevention of path bypasses |
| Adversarial agent forging sanctioned-tool output | Requires Tier 2 provenance | Regulated domain, external audit |

**For most projects, the "does not prevent" list is acceptable** —
the worst outcome is an audit-log finding that triggers a fix-and-
retry. If that's not acceptable for a specific ceremony, add Tier 1
for that ceremony only.

---

## Tier 1 — add the hook (for high-stakes ceremonies only)

Install when you want real-time denial instead of step-boundary
detection:

```bash
stepproof install --scope project
```

This writes `.claude/hooks/`, `.claude/settings.json` registrations,
and the classification YAML. **Requires Claude Code restart.**

**What changes at Tier 1:**

- Every tool call goes through the PreToolUse hook.
- Off-scope tool calls are denied immediately, before they run.
- `psql` is denied during a step where `cerebro-migrate` is the
  sanctioned tool — not caught in audit, refused at the boundary.

**What also changes** (honest about the cost):

- Session is globally gated when a run is active. If the run is
  stuck (bad runbook scope, test failure the agent can't fix
  within the step's allowed_tools), the session is locked until
  you resolve.
- Recovery path when stuck: `stepproof uninstall` (deliberate,
  logged, reversible). Fix the runbook. `stepproof install` again.
  Restart Claude Code.
- Runbook authoring takes more care — under-scoped `allowed_tools`
  can trap the agent.

**When Tier 1 is worth it:** specific ceremonies where the cost of
an off-scope action is high and catching-after-the-fact is too
late. Production deploys, schema migrations, financial posts.

**When Tier 0 is enough:** everything else.

---

## Tier 2 — provenance (future)

Only `verify_round_marker` today. Provenance library is on the
roadmap. See [docs/TIERS.md](TIERS.md) and
[docs/research/09_provenance_and_signing.md](research/09_provenance_and_signing.md).

---

## Customizing for your stack

### Migration tool

Edit the runbook YAML. Replace references to `cerebro-migrate`
with your actual tool. If you're at Tier 1, also update the
classifier bash_patterns in `.claude/stepproof/action_classification.yaml`.

Common substitutions:

- **Alembic**: `alembic upgrade head`
- **Supabase**: `supabase db push`
- **Prisma**: `npx prisma migrate deploy`
- **Flyway**: `flyway migrate`
- **Django**: `manage.py migrate`

### Deploy platform

The `verify_single_active_deployment` verifier needs an
`active_deployment_count`. How the agent gets that count is
project-specific:

- **Railway**: `railway deployments list | grep ACTIVE | wc -l`
- **Kubernetes**: `kubectl get deployments -l app=mine -o name | wc -l`
- **Vercel**: `vercel list --prod --json | jq '.deployments | length'`
- **Fly.io**: `fly deploys list | grep running | wc -l`

### Row-count source

For data migrations, `verify_row_counts_match` needs
`rows_extracted` and `rows_loaded`. These come from whatever ETL
tooling you use. For pure schema changes, matching placeholders
(both 0 or both null) are acceptable.

---

## Honest caveats

- **Tier 0 is a real product**, but several verifiers are
  stub-level (they validate evidence shape more than they read
  deep external state). The stub still catches "agent claimed done
  without fields" — which is the common failure.
- **The audit log is Level 1 integrity** (plain SQLite).
  Tamper-evident-at-write is a future increment. Today, an
  attacker with access to the host can rewrite history.
- **Human approval workflow** is placeholder in the schema.
  Don't run Ring 3 production ceremonies without wiring your own
  approval out-of-band.
- **Per-harness adapters beyond Claude Code don't exist yet**.
  Cursor, OpenAI Agents SDK — would need their own hook-equivalent
  layer for Tier 1. Tier 0 works with any MCP-speaking harness.

---

## Recovery recipes

### Run got stuck (Tier 1 mostly)

The hook is refusing something the agent needs. The ceremony is
wrong.

```bash
# Unstuck fast:
stepproof uninstall             # disables hook
rm -f .stepproof/active-run.json .stepproof/runtime.url

# Edit the runbook in examples/ — widen the stuck step's allowed_tools
#   so the agent has iteration room. Commit.

stepproof install --scope project   # re-enable hook with new runbook
# Restart Claude Code
# Start a fresh run
```

### Run got stuck (Tier 0)

Much easier. No hook is blocking anything; the run is just not
advancing because the verifier is rejecting evidence.

```bash
# Inspect current state:
sqlite3 .stepproof/runtime.db \
  "SELECT current_step, status FROM workflow_runs WHERE run_id = '<your run_id>';"

# Abandon the run (no CLI today; hit the HTTP endpoint):
# See .stepproof/runtime.url for the URL, then POST /runs/<id>/abandon.
# Fix the evidence and submit again, or declare a new plan.
```

### Clean slate

```bash
stepproof uninstall   # if Tier 1 is installed
rm -rf .stepproof/    # wipes runtime state
# Remove .mcp.json manually if you want StepProof off entirely
```

---

## Customization checklist

Before you use the runbook on real work:

- [ ] At Tier 0 for first deployment (unless you're sure you need Tier 1).
- [ ] Runbook customized for your migration / deploy tool.
- [ ] At least one full ceremony run tested in staging before
      production.
- [ ] Audit-log query saved somewhere your compliance team can
      run it.
- [ ] Recovery recipe (above) practiced once before you need it in
      anger.

That's the tier-appropriate, pragmatic adoption path.

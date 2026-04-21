# Deploy StepProof to Your Project — 15-Minute Guide

Pragmatic first-use guide. Assumes you have a real project with a
real migration and deployment flow, and you want StepProof to stop
the most common agent-bypass patterns *today* — without waiting for
any of the planned increments.

**What you get in the 15 minutes:**

- A hook that denies raw `psql` / `pg_dump` when a migration
  ceremony is active.
- A runbook that requires structured evidence at each step
  (migration name, deploy ID, row counts, active-deployment count).
- An audit log capturing every ceremony decision with timestamps,
  policy IDs, and verifier results.

**What you don't get yet** (documented gaps, bottom of this page).

---

## Step 1 — Install StepProof in your project (2 min)

```bash
cd /path/to/your/project
uv tool install stepproof   # or: pipx install stepproof
stepproof install --scope project
```

Writes `.claude/hooks/`, `.claude/settings.json`,
`.claude/stepproof/action_classification.yaml`, and
`.stepproof/adapter-manifest.json`.

---

## Step 2 — Copy the starter runbook (1 min)

```bash
mkdir -p examples
# Copy from StepProof repo into your project
cp /path/to/stepproof/examples/rb-migration-deploy-mvp.yaml \
   examples/rb-migration-deploy-mvp.yaml
```

Or paste the contents from that file directly.

---

## Step 3 — Customize for your project's sanctioned tools (5 min)

The runbook ships generic. You customize three things for your stack.

### 3a. Rename the sanctioned migration tool in the classifier

Open `.claude/stepproof/action_classification.yaml`. Find the
`bash_patterns` section. If your project's migration tool isn't
called `cerebro-migrate`, replace the pattern. For example, if you
use `alembic`:

```yaml
  - match: '^(?:sudo\s+)?(?:env\s+\w+=\S*\s+)*alembic\s+upgrade\b'
    action_type: database.write
    ring: 2
    env_overrides:
      production: { ring: 3 }
```

For `supabase-cli`:

```yaml
  - match: '^(?:sudo\s+)?supabase\s+db\s+(push|migration\s+up)\b'
    action_type: database.write
    ring: 2
    env_overrides:
      production: { ring: 3 }
```

For `prisma`:

```yaml
  - match: '^(?:sudo\s+)?npx\s+prisma\s+migrate\s+(deploy|dev)\b'
    action_type: database.write
    ring: 2
```

The existing `psql`, `pg_dump`, `pg_restore` patterns stay —
they're the shortcut you're preventing.

### 3b. Adjust the runbook's allowed_tools if needed

Most projects won't need changes. If you have additional
project-specific tools (e.g., a custom deployment CLI) and want
them in scope during s3, add them to `allowed_tools`.

### 3c. Decide your row-count data source

The runbook's s2 asks for `rows_extracted` and `rows_loaded`. For a
pure schema change, you can submit matching placeholder values
(e.g., both 0). For a data-move migration, wire these to your ETL
output.

---

## Step 4 — Register the stepproof MCP (3 min)

Write `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "stepproof": {
      "type": "stdio",
      "command": "stepproof",
      "args": ["mcp"],
      "env": {
        "STEPPROOF_STATE_DIR": "/absolute/path/to/your/project/.stepproof",
        "STEPPROOF_RUNBOOKS_DIR": "/absolute/path/to/your/project/examples"
      }
    }
  }
}
```

If you installed StepProof via `uv tool install` and the `stepproof`
binary is on `$PATH`, the literal command `"stepproof"` works. If
not, use the absolute path to the binary.

---

## Step 5 — Restart Claude Code (1 min)

Quit Claude Code and relaunch in the project directory. Hooks only
load at session start.

---

## Step 6 — Run a ceremony (3 min)

In the new Claude Code session, ask the agent:

> *"Apply the pending migration to staging. Use StepProof's
> `rb-migration-deploy-mvp` runbook. Start the run, do the work,
> submit evidence at each step boundary."*

Watch for:

- `.stepproof/active-run.json` appearing as the run starts.
- Any attempt to run `psql` or similar raw-SQL shortcut will be
  denied by the hook with a clear reason.
- Evidence at each step gates advancement. No evidence, no
  advance.

When the run reaches `status: completed`, query the audit log:

```bash
sqlite3 .stepproof/runtime.db \
  "SELECT substr(timestamp,12,8) AS t, action_type, decision, policy_id, substr(reason,1,80) AS reason \
   FROM audit_log ORDER BY timestamp DESC LIMIT 30;"
```

That's the regulator-shaped artifact. Timestamps, policy IDs,
verifier signatures, decision reasons — written by the runtime,
not by the agent.

---

## What this prevents today

| Incident class | Mechanism | Status |
|---|---|---|
| Raw `psql` / `pg_dump` migration shortcut | Classifier bash_patterns + hook denial | ✅ Works today |
| Ad-hoc Python scripts bypassing migration tool | Hook scope excludes `Write` to `.py` files outside s1 | ✅ Works today |
| Silent null violation (extracted ≠ loaded) | `verify_row_counts_match` | ✅ Works today |
| Zombie container (multi-active deployments) | `verify_single_active_deployment` | ✅ Works today |
| Audit trail for the ceremony | SQLite `audit_log` table | ✅ Works today (Level 1 integrity — not tamper-evident yet) |

---

## What this does NOT yet prevent

Document these as future increments. Don't paper over them.

| Gap | Mitigation today | Increment |
|---|---|---|
| Environment cross-wiring (DATABASE_URL pointing at wrong env) | `verify_env_isolation` exists but is stub-level; you need to submit `declared_env` and `database_url_env` manually | Future: wire verifier to read real DATABASE_URL via sanctioned env-reader tool |
| Docker cache persistence | `verify_connector_registry` exists as stub; requires you to submit `connector_registry` manually | Future: verifier queries deploy logs directly |
| Cryptographic provenance | None — today relies on tool scoping | Future: sanctioned tools emit signed attestations |
| Human approval workflow for Ring 3 | Placeholder in schema only | Future: real approval tool + audit record |
| Tamper-evident audit log | Level 1 (plain SQLite) | Future: Level 3 hash-chain; Level 4+ external publication |

See [docs/CEREMONY_DB_MIGRATION.md](CEREMONY_DB_MIGRATION.md) for the
full-fidelity target; the MVP above is a practical subset.

---

## When to uninstall

If the ceremony traps the agent in a state that's preventing
legitimate work (e.g., you hit a new failure mode the runbook
doesn't model), the deliberate escape is:

```bash
stepproof uninstall
```

That's the sanctioned exit. Reversible with a re-install. Logged.
Leaves your repo clean.

Don't bypass the hook by editing `.claude/hooks/` directly — that
defeats the point. If a ceremony is wrong, fix the ceremony. If
StepProof itself is wrong, uninstall and file an issue.

---

## Customization checklist

Before you ship the runbook for real use:

- [ ] Replaced generic `cerebro-migrate` pattern with your actual
      migration tool in `action_classification.yaml`.
- [ ] Confirmed `psql` / `pg_dump` / `pg_restore` patterns are still
      denied (if you use PostgreSQL) — or added equivalents for
      MySQL / Mongo / Redis.
- [ ] Decided how s2's row-count evidence is gathered for your
      project. Pure schema changes: accept matching placeholders.
      Data moves: wire to your ETL output.
- [ ] Wrote a 2-sentence commit message format the agent should use
      for migration commits — the audit log is only useful if the
      commits are attributable.
- [ ] Tested one full ceremony run end-to-end in staging before
      trusting it in production.
- [ ] Checked that `stepproof uninstall` works in your project
      (if StepProof is ever broken, you need the escape working).

---

## Honest caveats

- This is an **MVP**, not a production-hardened governance layer.
  It catches the most common shortcuts; it does not catch
  sophisticated ones.
- The verifiers are **stub-level** for several checks. The real
  enforcement is at the hook (tool-scope) layer. Plan for verifier
  hardening in your own roadmap.
- The audit log is **not tamper-evident** yet. If your
  compliance environment requires append-only cryptographic
  logs, this MVP is not sufficient. See
  [docs/research/10_audit_tamper_evidence.md](research/10_audit_tamper_evidence.md).
- You still need **human oversight** for Ring 3 production actions.
  This MVP flags them; it does not handle the approval flow.

The value of this MVP is preventing the *obvious shortcuts* that
cause the most common class of incidents. That's a real improvement
over advisory controls, shippable today, without waiting for
StepProof to reach its full architectural target.

# Example Ceremony: Apply a Database Migration to Production

**Status:** design reference, not yet an implementation target.
**Purpose:** exhaustively document one real ceremony — every step, every
tool, every failure mode the agent might try, every check the system
must perform — so we can measure the gap between what StepProof does
today and what it needs to grow into. This is the shape the runbook
schema + verifier fabric + hook should be able to express end-to-end.

---

## Why this specific ceremony

Database migrations are the cleanest test of the thesis:

- The **correct path** is well-known (branch → PR → CI → apply to
  staging → verify → approve → apply to prod → verify → done).
- The **failure modes** are well-documented (raw `psql`, ad-hoc
  Python scripts, environment cross-wiring, zombie containers,
  silent null violations, CI skipped, approval bypassed, race with
  other migrations).
- The **cost of getting it wrong** is high and measurable.
- The **verifiers are all real-state** — migration tracking tables,
  GitHub Actions API, deploy-platform API, service health endpoints —
  nothing can be faked by the agent.

If StepProof can make this ceremony unskippable, it can make anything
unskippable.

---

## Actors

| Actor | Role | Can it lie? |
|---|---|---|
| **Human operator** | Kicks off the ceremony, grants Ring 3 approvals, reviews audit log after. | Not relevant — human is the trust root. |
| **Worker agent** (Claude Code session) | Executes each step. Submits evidence at step boundaries. | Yes. Assume yes, every time. |
| **StepProof runtime** | Holds run state, dispatches verifiers, writes audit log. | No — this is the adjudicator. |
| **StepProof hook** (`PreToolUse`) | Fires before every tool call; denies off-scope actions. | No — it's a harness lifecycle event the agent can't route around. |
| **Verifier fabric** | Per-step functions that read real external state (GitHub API, DB, deploy API). Read-only. | No — verifiers have no write access. |
| **External systems** | GitHub (PR + Actions), staging DB, production DB, deploy platform. | Independent reality. Verifiers consult them. |

**The trust model:** assume the agent is a rational drift-prone
worker. It is not adversarial; it wants to get done. Under pressure or
ambiguity it will take the efficient path. The hook + verifier exist
to make "the efficient path" and "the correct path" the same thing.

---

## Preconditions (before the ceremony can start)

- The migration file is written and on a feature branch. (If it
  isn't, a **prior ceremony** — "author a migration" — ran first.)
- The sanctioned migration tool (e.g., `cerebro-migrate`, `alembic`,
  `prisma migrate`, `supabase db migration apply`) is installed and
  accessible on `$PATH` inside the project.
- The agent has credentials for:
  - GitHub (for PR creation and Actions API reads)
  - Staging DB (read/write via the sanctioned tool, read-only via the
    verifier)
  - Production DB (read/write via the sanctioned tool, read-only via
    the verifier — different credential)
  - Deploy platform (if the migration ships with a deploy)
- Credentials are resolved at tool-invocation time by each tool, not
  exposed in the agent's context or in evidence payloads.

---

## Invocation

**Human triggers the ceremony explicitly.** This closes the "agent
skips `run_start`" gap without needing a hook for it. The human is the
trust root for ceremony initiation.

```
human:  "Apply migration 20260420_add_widgets_status to production."
agent:  mcp__stepproof__stepproof_run_start(
            template_id="rb-db-migration-and-deploy",
            owner_id="daniel",
            environment="production",
        )
runtime:  → creates run_id, writes .stepproof/active-run.json
          with current_step=s1 and allowed_tools from s1
hook:     on every subsequent tool call, reads active-run.json and
          enforces scope.
```

From here forward, the hook sees the active ceremony on every call.

---

## The steps

Each step below follows the same shape:

- **Intent** — plain English, one sentence.
- **Happy path** — what the agent does when everything goes right.
- **Allowed tools** — the narrow scope for this step.
- **Required evidence** — what the agent must submit at step complete.
- **Verifier** — what the runtime checks against real state.
- **Hook denials** — specific off-scope actions the hook must block.
- **Verifier denials** — specific false claims the verifier must reject.
- **Edge cases** — situations that aren't quite failure but aren't
  happy path either.

---

### S1. Open a PR with the migration file

**Intent:** Make the proposed migration visible and reviewable on
GitHub before anything is applied anywhere.

**Happy path:**
1. Agent creates a feature branch.
2. Agent confirms the migration file is committed to the branch.
3. Agent pushes the branch to origin.
4. Agent opens a PR targeting the main branch.
5. Agent submits the PR URL and branch name as evidence.

**Allowed tools:**
- `Read`, `Glob`, `Grep`, `LS` (orient in the repo)
- `Bash` restricted to `git status`, `git branch`, `git checkout`,
  `git commit`, `git push` via bash_patterns
- `Bash` restricted to `gh pr create`, `gh pr view`
- `mcp__stepproof__stepproof_step_complete`

**Required evidence:**
```json
{
  "branch_name": "migration/add-widgets-status",
  "pr_url": "https://github.com/<org>/<repo>/pull/<n>",
  "migration_file_path": "migrations/20260420_add_widgets_status.sql",
  "head_sha": "<git sha of branch head>"
}
```

**Verifier: `verify_pr_opened`**
- GET `https://api.github.com/repos/<org>/<repo>/pulls/<n>`
- Confirm `state == "open"`, `head.ref == branch_name`,
  `head.sha == head_sha`.
- GET the PR's file list. Confirm `migration_file_path` appears in
  the changed files.
- Optionally: confirm the migration file's first-line comment names
  the migration_id.

**Hook denials (things the agent might try that the hook blocks):**
- `git push --force origin main` — pushing directly to main; deny.
- `Write` to the migration file path (s1 is about *opening the PR*,
  not *authoring the migration*; authoring belongs to a prior
  ceremony).
- `psql` anything — psql isn't in scope for s1 at all.
- `Bash rm` of anything — filesystem deletion not in scope.

**Verifier denials:**
- Agent claims `pr_url=...pull/42` but GitHub returns 404 → fail.
- PR exists but `state == "closed"` — fail, closed PR isn't a valid
  gate.
- PR exists but the migration file isn't in its diff — fail.
- PR targets a branch other than main — fail.
- `head_sha` doesn't match the live PR head — fail (PR was force-pushed
  after the evidence was captured; stale evidence).

**Edge cases:**
- PR already exists from a prior attempt → verifier finds it, accepts
  if all checks pass. This makes the ceremony idempotent at s1.
- GitHub rate limit → verifier returns a transient-fail signal; on_fail
  retry with backoff.
- PR was opened by a different author (the agent picked up a human's
  PR) → verifier can require `pr.user.login == agent_id` or treat as
  acceptable; that's a policy decision for the runbook author.

---

### S2. Apply the migration to staging via the sanctioned tool

**Intent:** Run the migration in a non-production environment first,
using the tool of record. Never raw SQL.

**Happy path:**
1. Agent runs `cerebro-migrate --env=staging` (or the project's
   equivalent).
2. The tool writes a row to the migration tracking table.
3. Agent captures tool output, migration version id, and a snippet of
   the output.

**Allowed tools:**
- `Bash` restricted to the sanctioned migration tool's invocation
  pattern (e.g., `^cerebro-migrate(-staging)?\b` from the existing
  classification YAML).
- `Read` (to read tool output files).
- `mcp__stepproof__stepproof_step_complete`.

**Required evidence:**
```json
{
  "migration_version_id": "20260420_add_widgets_status",
  "target_env": "staging",
  "tool_output_path": ".stepproof/evidence/s2-migration-output.log",
  "tool_exit_code": 0
}
```

**Verifier: `verify_migration_applied`**
- Connect **read-only** to the staging DB using the verifier's own
  credential (not the agent's).
- Query the migration tracking table
  (`supabase_migrations.schema_migrations` or the project's
  equivalent).
- Confirm the `migration_version_id` appears as applied.
- Compare the applied migration's checksum against the file's checksum
  in the repo at `head_sha` from s1's evidence.

**Hook denials (this step is where Greenmark-shape failures live):**
- `Bash psql` — psql not in scope; deny with a reason pointing at
  cerebro-migrate.
- `Bash pg_dump`, `Bash pg_restore` — not in scope.
- `Write` to a `.py` or `.sh` file that looks like an ad-hoc migration
  script — Write isn't in s2's allowed_tools at all.
- `Bash ssh <host>` — SSH into a DB host is not a StepProof-sanctioned
  path.
- `mcp__some_other_db_tool__execute_sql` — if an MCP exposes direct
  SQL execution, that MCP isn't in s2's allowed_tools.
- `Bash cerebro-migrate --env=production` — this is s2 (staging). The
  `--env=production` variant is a different action_type (Ring 3) and
  belongs to s6. Even if `cerebro-migrate` is allowed, the bash_pattern
  matches the production variant FIRST and classifies it separately.

**Verifier denials:**
- Agent claims migration applied, but the tracking table has no
  matching row → fail. This is the Greenmark silent-success case.
- Agent claims it applied to staging but the tracking table's row is
  pinned to production → env cross-wiring; fail.
- Applied migration's checksum doesn't match the PR's migration file
  → fail. The agent ran a different migration than what's in the PR.
- Tool exited 0 but the tracking table entry is marked `rolled_back`
  → fail.

**Edge cases:**
- Migration was already applied in a prior run → tracking table has
  the entry; verifier passes. Ceremony is idempotent.
- Tool crashed mid-migration, leaving the DB in an inconsistent state
  → verifier detects (checksum mismatch, partial state), fails. Human
  escalation.
- Tool's output format changes between versions → verifier should not
  rely on parsing stdout; it checks the DB directly. Output is
  evidence-for-audit, not evidence-for-decision.
- The sanctioned tool is broken (binary crashes, credentials stale) →
  **this is the Greenmark temptation moment.** The agent is tempted
  to shortcut with psql. Hook denies. Agent must escalate to human,
  not route around.

---

### S3. Wait for CI to go green on the PR

**Intent:** Confirm the PR passes every automated check before
proceeding. Tests, linting, schema compatibility, whatever CI enforces.

**Happy path:**
1. Agent polls the GitHub Actions API for the PR's workflow runs.
2. Agent waits until the workflow for `head_sha` reports
   `conclusion: success`.
3. Agent captures the workflow_run_id.

**Allowed tools:**
- `Bash` restricted to `gh run list`, `gh run view`, `gh pr checks`.
- `Read` (for config files if debugging locally).
- `mcp__stepproof__stepproof_step_complete`.

**Required evidence:**
```json
{
  "pr_url": "<from s1>",
  "head_sha": "<from s1>",
  "workflow_run_id": 12345678,
  "workflow_name": "CI",
  "conclusion": "success"
}
```

**Verifier: `verify_ci_green`**
- GET `https://api.github.com/repos/<org>/<repo>/actions/runs/<workflow_run_id>`
- Confirm `conclusion == "success"`, `status == "completed"`.
- Confirm `head_sha == s1.head_sha`.
- Confirm the workflow ran against the PR's branch, not main.
- If the workflow has required checks (schema-check, migration-lint),
  confirm each passed individually.

**Hook denials:**
- `Bash pytest`, `Bash npm test`, `Bash cargo test` — running tests
  locally is not CI. S3 is explicitly about CI, not local tests. If
  the runbook author wants local tests too, that's a separate step.
- `Edit .github/workflows/*.yml` — modifying CI config to fake
  success. Not in scope.
- `gh run rerun` — allowed, but re-running doesn't satisfy s3 until
  the rerun completes green. Verifier will recheck on the next
  `step_complete` attempt.

**Verifier denials:**
- `workflow_run_id` doesn't exist → fail.
- Workflow exists but `conclusion == "failure"` → fail.
- Workflow exists and passed, but for a different `head_sha` (CI ran
  on an earlier commit, agent pushed new commits after) → fail. The
  evidence is stale.
- Workflow is still `in_progress` → retry, don't fail.
- Workflow was cancelled by a human → fail; agent must understand why
  the human cancelled before proceeding.

**Edge cases:**
- CI took 40 minutes, the step timeout is 30 → hit the timeout, on_fail
  retry with a longer timeout, or escalate.
- CI passed on first try but the agent force-pushed the branch → new
  CI run starts; the old `workflow_run_id` is no longer authoritative.
- One required check is flaky → the agent can re-run that check, but
  can't mark s3 complete until it's green.
- Scheduled workflows (nightly) fire during s3 and appear in the
  listing → verifier filters by workflow_name and head_sha, ignoring
  unrelated runs.

---

### S4. Double-check staging schema + data

**Intent:** Independently confirm the migration's intended effect is
present in staging. Don't trust the tool's "success" — verify the DB.

**Happy path:**
1. Agent (via a StepProof-wrapped read-only query tool) runs
   `\d widgets` or the equivalent column listing.
2. Agent confirms the `status` column exists with the expected type
   and constraints.
3. Agent optionally runs a row-count or data-validity check if the
   migration included data manipulation.

**Allowed tools:**
- `mcp__stepproof__stepproof_query_readonly` (the StepProof-wrapped
  SELECT-only DB tool) — **NOT** raw `psql`. Read-only wrapping is
  enforced at the MCP layer; the agent literally cannot write.
- `Read`, `Grep` (for comparing expected vs actual schema).
- `mcp__stepproof__stepproof_step_complete`.

**Required evidence:**
```json
{
  "target_env": "staging",
  "schema_check": {
    "table": "widgets",
    "columns": [
      {"name": "status", "type": "text", "nullable": true}
    ]
  },
  "row_count_pre": 1234,
  "row_count_post": 1234
}
```

**Verifier: `verify_schema_and_data`**
- Runs its OWN read-only query against staging.
- Compares actual schema to agent's `schema_check` claim. Any
  mismatch (missing column, wrong type, wrong nullability) → fail.
- If the migration was supposed to preserve row counts, verify
  `row_count_pre == row_count_post`.
- If the migration was supposed to backfill values, sample rows and
  confirm the backfill is present.

**Hook denials:**
- `Bash psql` — always denied; hook classification catches it.
- `mcp__stepproof__stepproof_query_readonly` with an `INSERT`/`UPDATE`/
  `DELETE`/`ALTER`/`DROP` statement — the MCP wrapper itself rejects
  non-SELECT statements before the query reaches the DB.
- `Edit` to the migration file at this point — migration's already
  applied; editing the file now is ceremony-breaking.

**Verifier denials:**
- Agent claims the column is `text` but it's actually `varchar(50)` →
  fail.
- Agent claims `row_count_post = row_count_pre` but the verifier's
  query disagrees → fail (silent null violation pattern: tool reported
  success, loaded 0 rows).
- Agent's evidence references staging but the verifier's query runs
  against the env in the evidence's `target_env` — if that's wrong,
  fail.

**Edge cases:**
- Schema includes a check constraint the agent didn't claim → not an
  automatic fail if it doesn't conflict; the verifier's policy decides.
- Staging DB has additional unrelated columns → verifier compares only
  the columns the migration was meant to add, not full schema.
- Transient connection failure → retry, don't fail.

---

### S5. Request human approval for production

**Intent:** Ring 3 actions (production migrations) require a human
in the loop. The agent cannot grant its own approval.

**Happy path:**
1. Agent calls `mcp__stepproof__stepproof_request_approval`
   with a summary of what it's about to do.
2. Runtime writes an approval record, notifies human (email / webhook /
   Slack).
3. Human reviews staging verification results from s4, approves or
   rejects.
4. Agent polls approval status until resolved.

**Allowed tools:**
- `mcp__stepproof__stepproof_request_approval`
- `mcp__stepproof__stepproof_check_approval_status`
- `Read` (to draft the approval summary)
- `mcp__stepproof__stepproof_step_complete`

**Required evidence:**
```json
{
  "approval_id": "ap-uuid",
  "approver": "daniel@example.com",
  "approval_timestamp": "2026-04-20T18:00:00Z",
  "approval_summary": "Apply 20260420_add_widgets_status to prod after staging validation."
}
```

**Verifier: `verify_approval_granted`**
- Queries StepProof's own `approvals` table for `approval_id`.
- Confirms `status == "approved"`.
- Confirms `approver` is a registered human identity, not an agent.
- Confirms `approval_bound_to_run_id == current_run_id` (this approval
  isn't borrowed from a different run).
- Confirms `approval_timestamp` is fresh (approvals older than N hours
  expire and need re-granting).

**Hook denials:**
- `mcp__stepproof__stepproof_grant_approval` — **if this tool exists
  at all, it must require credentials the agent doesn't have**. The
  safest design: there is no tool by this name. Humans grant
  approvals out-of-band (web UI, CLI, Slack bot) with their own
  credentials.
- Agent tries to modify the approvals table via any DB tool — not in
  scope.

**Verifier denials:**
- `approval_id` doesn't exist → fail.
- Status is still `pending` → retry, don't fail (the human hasn't
  decided yet).
- Status is `rejected` → **terminal fail**; ceremony cannot proceed
  without a new approval.
- Approver is an agent identity → fail. Defense against an agent
  escalating "approval" through another agent.
- Approval is bound to a different run_id → fail.

**Edge cases:**
- Human approves but then revokes before s6 runs → verifier must
  re-check at s6's structural gate, not just at s5 complete.
- Ceremony stalls here for hours waiting for a human → that's the
  feature, not a bug. Add a step timeout with escalation to a second
  approver if needed.
- Multiple pending approvals for the same run (the agent retried the
  request) → verifier uses the most recent one; older ones are
  superseded.

---

### S6. Apply the migration to production

**Intent:** Run the same migration, same tool, same file — now
against production. Ring 3. Structurally gated on all prior steps.

**Happy path:** Same as s2, but with `--env=production`.

**Allowed tools:**
- `Bash` restricted to the sanctioned tool's production variant
  (e.g., `^cerebro-migrate-production\b`).
- `Read` (for verifying output).
- `mcp__stepproof__stepproof_step_complete`.

**Required evidence:**
```json
{
  "migration_version_id": "<same as s2>",
  "target_env": "production",
  "tool_output_path": ".stepproof/evidence/s6-migration-output.log",
  "tool_exit_code": 0,
  "staging_checksum_reference": "<from s2>"
}
```

**Verifier: `verify_migration_applied`** (same function, production
target)

- Same checks as s2, against production DB.
- **Additionally:** confirms the production migration's checksum
  matches the staging migration's checksum from s2. The same file was
  applied to both environments.

**Hook denials (same as s2 plus):**
- The `structural_gate` in policy.py fires if prior steps aren't
  verified. Even if `cerebro-migrate-production` is in s6's
  allowed_tools, the gate denies unless s1-s5 all passed. This is the
  **second line of defense** — per-step scoping catches most
  off-ceremony actions; the structural gate catches attempts to
  advance out of order.

**Verifier denials (same as s2 plus):**
- Production migration checksum doesn't match staging checksum → fail.
  The agent ran a different migration against prod. This is a
  catastrophic failure mode the verifier must catch every time.
- Environment in the tracking table disagrees with `target_env` → env
  cross-wiring.

**Edge cases:**
- Migration on prod is slow (hours) → long step timeout; the hook must
  not kill the in-flight migration. Cancellation policy: only via
  `stepproof_run_abandon` triggered by a human.
- Migration fails mid-flight on prod (disk full, lock contention) →
  tracking table may show `rolled_back`; verifier catches; step fails;
  escalates to human. No auto-retry on prod.

---

### S7. Verify production schema + data

**Intent:** Same as s4, but against production. Independent read-only
confirmation.

Omitted detail here — it's identical to s4 with
`target_env: production` and the production verifier credential.

---

### S8. Mark ceremony complete and record final state

**Intent:** Close out the run. Ensure the audit log captures the full
causal chain. Publish the completion marker.

**Happy path:**
1. Agent submits a final evidence bundle summarizing the whole run
   (optional — many runbooks complete automatically on s7 verify).
2. Runtime transitions the run to `COMPLETED`.
3. Runtime clears `.stepproof/active-run.json`.
4. Audit log shows the complete chain:
   `plan.declared → step.complete (s1, verifier=verify_pr_opened) →
    step.complete (s2, verifier=verify_migration_applied) → … →
    step.complete (s7, verifier=verify_schema_and_data) →
    run.completed`

**Required evidence:**
```json
{
  "summary": "Applied 20260420_add_widgets_status to production.",
  "audit_log_tail_hash": "<sha256 of last N audit rows>"
}
```

**Verifier: `verify_audit_chain_intact`**
- Recomputes the expected audit-tail hash and compares.
- Confirms no out-of-sequence `step.complete` events.
- Confirms every step transition has a verifier result attached.

**Edge cases:**
- Someone (human, bug, attack) modified the audit log between s7 and
  s8 → hash mismatch; final verifier fails; ceremony flagged as
  "completed under audit discrepancy." Human investigation required.
- The runtime crashed and restarted mid-ceremony → on restart, the
  audit log picks up where it left off; this verifier catches any
  missing events.

---

## Off-ceremony actions the agent might attempt

These aren't tied to a specific step — they're the general drift
patterns that need to fail everywhere.

| Attempt | What the agent hopes for | What StepProof does |
|---|---|---|
| `Bash psql -h prod-db -c "ALTER TABLE..."` | Raw SQL shortcut during any step. | Hook denies; `psql` isn't in any step's allowed_tools. Classification yaml marks `psql` as Ring 2 (Ring 3 in prod). Fail-closed. |
| `Write` to `/tmp/apply.py` with a psycopg script | Smuggle a migration as a "helper script." | Hook denies: `Write` to `/tmp/*.py` is not in any step's allowed_tools. And even if it were, executing it via `Bash python` isn't either — `python` not in allowed bash patterns. |
| `ssh db.prod` | Side-channel to the DB host. | Hook denies: `ssh` not in any step's allowed_tools. |
| `gh pr close <prev_pr>` then reopen a new one | Erase the audit trail on the PR side. | Hook denies: `gh pr close` not in s1's scope. If the agent does close/reopen during s3+, the verifier catches via `head_sha` drift. |
| `Edit` the migration file after s2 passed | Change what's going to be applied to prod in s6. | s6's verifier compares production checksum to staging checksum from s2. Mismatch → fail. Also: editing the migration file during any step after s1 isn't in scope. |
| Submit s6 `step_complete` with evidence copied from s2 | Fake the production migration. | s6's `verify_migration_applied` runs against production DB, not staging. Production tracking table doesn't have the migration → fail. |
| Call `stepproof_run_start` a second time with a different template | Swap ceremonies mid-run. | Runtime rejects: `run_active` for current project; second start either takes ownership (per increment-1 semantics for same-project runs) or is denied. Policy decision documented. |
| Read the approval_id from a prior run and submit it as s5 evidence | Borrow an approval. | Verifier checks `approval_bound_to_run_id == current_run_id`. Fails. |
| Modify `.stepproof/active-run.json` directly | Skip a step by lying about `current_step`. | Hook doesn't allow `Write`/`Edit` to `.stepproof/*` in any step's allowed_tools. If somehow attempted, runtime's own internal state is authoritative — `active-run.json` is a cache, not ground truth. The runtime reads from SQLite. |
| Disable the hook by editing `.claude/hooks/stepproof_pretooluse.py` | Remove enforcement at the source. | Hook denies `Edit` / `Write` to `.claude/hooks/*` in every step's allowed_tools. The hook denying its own modification is its own recursive enforcement. |
| `stepproof uninstall` and redo the work | Nuclear exit — remove StepProof entirely. | This IS the sanctioned exit. It's deliberate, logged, and reversible. If the ceremony was a fraud attempt, the audit log already captured everything up to that point. |

---

## Terminal states

- **COMPLETED** — every step passed its verifier; run ended cleanly.
- **FAILED** — a step's verifier returned fail and on_fail was
  `escalate_human` with no human override. Run is in a frozen state;
  nothing advances.
- **ABANDONED** — a human (via `stepproof_run_abandon`) explicitly
  ended the run mid-flight. Audit log captures the reason.
- **SUSPENDED** — liveness heartbeat expired (per ADR-0003); run is
  paused pending a new heartbeat or explicit abandonment.

---

## Artifacts produced

By the time the ceremony ends, these exist on disk and in
databases:

1. `.stepproof/runtime.url` — written on boot, cleared on shutdown.
2. `.stepproof/active-run.json` — updated at each step transition,
   cleared on COMPLETED.
3. `.stepproof/evidence/s{N}-*.log` — tool output captures submitted
   as evidence.
4. `.stepproof/runtime.db` — SQLite with:
   - `workflow_runs` — the run's full lifecycle.
   - `step_runs` — each step's status, attempts, evidence, verifier
     result.
   - `audit_log` — every policy decision in order, with timestamps,
     reason, policy_id, payload_hash.
5. On GitHub: a PR with the migration, linked workflow runs, review
   comments.
6. On the target DBs: new rows in the migration tracking table, with
   checksum, applied-at timestamp, applied-by identity.

---

## Where this differs from what StepProof does today

Gap analysis — what the current implementation supports vs what this
ceremony needs:

| Capability | Today | Needed | Gap |
|---|---|---|---|
| Template-declared step order | ✅ | ✅ | — |
| Per-step `allowed_tools` | ✅ | ✅ | — |
| `structural_gate` for Ring 2+ requiring prior verified | ✅ | ✅ | — |
| Bash pattern classification (psql / migration tools) | ✅ | ✅ | — |
| Read-only DB query verifier | ⚠️ partial (only `verify_row_counts_match` exists) | ✅ (schema check, data check, env check) | **Need:** `verify_schema_and_data`, a generic read-only DB query verifier, more migration-tracking-table verifiers. |
| GitHub Actions API verifier | ❌ | ✅ | **Need:** `verify_ci_green` that hits GH Actions API. |
| GitHub PR verifier with head_sha / file-diff checks | ⚠️ stub (`verify_pr_opened` is mostly stub) | ✅ | **Need:** real implementation. |
| Approval workflow (request, grant, verify) | ❌ | ✅ | **Need:** `stepproof_request_approval`, approvals table, `verify_approval_granted`, human grant mechanism outside the agent context. |
| MCP-wrapped read-only DB query tool | ❌ | ✅ | **Need:** `mcp__stepproof__stepproof_query_readonly` with AST-level SELECT-only enforcement. |
| Evidence-file retention (`.stepproof/evidence/`) | ⚠️ ad-hoc | ✅ (structured) | **Need:** convention for evidence files, retention policy. |
| Audit chain integrity verifier | ❌ | ✅ | **Need:** `verify_audit_chain_intact` + tail hash. |
| Step timeout with escalation | ⚠️ field exists, not fully plumbed | ✅ | **Need:** timeout enforcement in the runtime. |
| Within-step iteration bound (max attempts) | ⚠️ field exists for on_fail, not globally | ✅ | **Need:** explicit max-iterations-per-step guard to prevent infinite loops. |
| Credential separation (agent credential ≠ verifier credential) | ❌ | ✅ | **Need:** verifier-only credentials held by the runtime, never exposed to the agent. |

---

## How this shapes the next increments

Reading the gap table above, the concrete shape of the next work:

**Increment 2** (verifier fabric maturation):
- Real implementations of `verify_pr_opened`, `verify_ci_green`,
  `verify_schema_and_data`.
- `mcp__stepproof__stepproof_query_readonly` MCP tool.
- Credential separation: verifier config includes DB/API creds the
  agent never sees.

**Increment 3** (approval workflow):
- `stepproof_request_approval` MCP tool.
- Approvals table + out-of-band human grant mechanism.
- `verify_approval_granted`.

**Increment 4** (audit integrity):
- `verify_audit_chain_intact` + tail hash publication.
- Step-timeout enforcement with escalation.
- Max-iterations-per-step guard.

**Increment 5** (schema additions for richer ceremonies):
- Branching (if verifier returns a specific reason, route to
  alternate step).
- Parallel step groups (fan-out / fan-in).
- DAG templates.

Each increment is self-contained and shippable. The order above is
"what the migration ceremony needs" — not the only possible order.

---

## One line per step, for the pitch deck

A compressed version of the whole thing, for anyone who wants the
narrative fast:

> **s1** Open a PR with the migration. Verifier reads GitHub.
> **s2** Apply to staging via the sanctioned tool. Verifier queries
>        the DB's migration tracking table.
> **s3** Wait for CI green. Verifier hits the GitHub Actions API.
> **s4** Double-check staging's schema + data. Verifier runs its own
>        read-only query.
> **s5** Request human approval. Verifier confirms a real human
>        granted it, bound to this run.
> **s6** Apply to production via the sanctioned tool. Structural gate
>        demands s1–s5 all verified.
> **s7** Double-check production. Verifier runs its own read-only
>        query, compares to staging.
> **s8** Close the run. Verifier confirms the audit chain is intact.

**At every step, the agent cannot advance by claim — only by
evidence the verifier reads against real state. At every step, the
hook denies off-scope actions before they run. The ceremony is the
contract; the contract is enforced structurally, not advisorily.**

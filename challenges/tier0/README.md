# Tier 0 Tests

Three tests that prove the Tier 0 architecture (MCP + verifiers +
audit log, *no PreToolUse hook*) works end-to-end against real
Claude Code sessions. See [docs/TIERS.md](../../docs/TIERS.md).

## Tests

### 01 — `01_scratch_happy.py`

Scratch project, `rb-repo-simple` runbook. Agent walks s1→s2→s3 to
COMPLETED without any hook installed. Asserts:

- Run status == completed.
- All three steps verified.
- Audit log has the causal chain (`plan.declared`, multiple
  `step.complete` entries).
- Zero hook events in the stream — because no hook is installed.

**Time:** ~60-90 seconds.
**Network:** only to Anthropic for the agent.
**Side effects:** none (scratch project deleted).

Run:
```bash
uv run python challenges/tier0/01_scratch_happy.py
```

### 02 — `02_release_local.py`

This repo's own release ceremony (`rb-stepproof-release`) against a
*copy* of this repo in `/tmp`. Bumps versions, builds wheels, runs
pytest, tags, commits — all under Tier 0 ceremony enforcement.
Asserts:

- Release run reaches COMPLETED.
- All 5 steps verified.
- A new commit appears in the copy's log.
- A git tag was created.
- `dist/` artifacts were produced.
- Zero hook events.

**Time:** ~5-15 minutes (workspace sync + build + test suite + agent).
**Network:** Anthropic + any `uv` downloads the copy needs.
**Side effects:** none on the source repo (all work happens in a
tmp clone).

Run:
```bash
uv run python challenges/tier0/02_release_local.py --timeout 900
```

### 03 — `03_release_with_ci.py`

Same as 02, but after the local ceremony completes, push a
temporary test branch to origin (`github.com/eidos-agi/stepproof`),
wait for the `tests` GitHub Actions workflow to run, verify it
concludes with `success` via the GH API, then delete the remote
branch. Real end-to-end including CI.

**Prerequisites:**
- `gh` CLI installed and authenticated.
- Push access to `eidos-agi/stepproof` (or fork and adjust
  `ORIGIN_URL` / `REPO_SLUG` at the top of the script).
- Network access.

Asserts:

- Local ceremony completes (same as 02).
- Test branch pushes cleanly to origin.
- GitHub Actions `tests` workflow runs for the pushed commit.
- Workflow concludes with `conclusion: "success"`.

**Time:** ~10-25 minutes (ceremony + CI execution).
**Network:** Anthropic + GitHub API + Actions runner execution.
**Side effects:**
- A branch named `stepproof-ci-test/<uuid>` is pushed to origin
  briefly and then deleted at the end (even on failure — best
  effort).
- One workflow run recorded in the repo's Actions history. This is
  intentional and expected.

Run:
```bash
uv run python challenges/tier0/03_release_with_ci.py \
    --ceremony-timeout 900 --ci-timeout 900
```

## The shape of what these prove

| Property | Test 01 | Test 02 | Test 03 |
|---|---|---|---|
| MCP-only architecture works end-to-end | ✅ | ✅ | ✅ |
| Verifier gates advancement against real state | ✅ | ✅ | ✅ |
| Audit log records the causal chain | ✅ | ✅ | ✅ |
| Agent iterates freely inside a step | ✅ | ✅ | ✅ |
| No hook needed for the happy path | ✅ | ✅ | ✅ |
| Multi-package workspace release | — | ✅ | ✅ |
| CI round-trip against real GitHub Actions | — | — | ✅ |

Tests 02 and 03 are more realistic but more expensive. Test 01 is
the 90-second smoke that proves the base architecture. All three
together prove Tier 0 scales from toy ceremonies to production-
shaped release workflows.

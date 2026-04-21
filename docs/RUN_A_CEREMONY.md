# Run a Ceremony on This Repo — Exact Commands

One-page recipe for running StepProof's enforcement on this repo end-to-end in a live Claude Code session. No prose, no options — the shortest sequence that produces the demo.

## Prereqs

- You're in `/Users/dshanklinbv/repos-eidos-agi/stepproof` (or wherever you cloned).
- `uv sync --all-packages` has run at least once.
- Claude Code CLI on `$PATH`.

## Install into this repo

```bash
uv run stepproof install --scope project
```

This writes `.claude/hooks/`, `.claude/settings.json`, `.claude/stepproof/action_classification.yaml`, and `.stepproof/adapter-manifest.json`.

## Register the MCP (one-time)

Write `.mcp.json` in the repo root:

```json
{
  "mcpServers": {
    "stepproof": {
      "type": "stdio",
      "command": "/Users/dshanklinbv/repos-eidos-agi/stepproof/.venv/bin/stepproof",
      "args": ["mcp"],
      "env": {
        "STEPPROOF_STATE_DIR": "/Users/dshanklinbv/repos-eidos-agi/stepproof/.stepproof",
        "STEPPROOF_RUNBOOKS_DIR": "/Users/dshanklinbv/repos-eidos-agi/stepproof/examples"
      }
    }
  }
}
```

## Restart Claude Code

Quit and relaunch Claude Code from this repo's directory. Hooks only load at session start.

## Start the ceremony

Inside the new Claude Code session, tell the agent:

> Call `mcp__stepproof__stepproof_run_start(template_id="rb-repo-simple", owner_id="daniel", environment="staging")`, then walk s1, s2, s3 to COMPLETED. For s1 write `HELLO.md`. For s2 capture pytest to `/tmp/sp-pytest.out`. For s3 commit.

Watch the hook enforce:
- Any Bash call during s1 is denied (Bash not in s1's scope).
- `verify_file_exists` reads real disk state.
- `verify_pytest_passed` parses the real summary line.
- `verify_git_commit` runs `git cat-file -t <sha>` against the repo.

## If a run gets stuck

You cannot advance s2 until pytest is actually green. That's the point. Inside s2 you have Read/Write/Edit/MultiEdit/Grep/Glob/Bash — everything needed to diagnose and fix. Iterate until the verifier passes.

## If you need to start over mid-ceremony

There's no `run abandon` CLI yet. If you want to fully reset:

```bash
uv run stepproof uninstall
rm -f .stepproof/active-run.json .stepproof/runtime.url
uv run stepproof install --scope project
```

Then restart Claude Code.

## Clean uninstall

```bash
uv run stepproof uninstall
```

Removes hooks, settings, manifest. Reversible.

## Verify the audit log after a ceremony

```bash
sqlite3 .stepproof/runtime.db \
  "SELECT substr(timestamp,12,8) AS t, action_type, decision, policy_id, substr(reason,1,60) AS reason \
   FROM audit_log WHERE run_id = '<run_id>' ORDER BY timestamp;"
```

This is the ground truth — timestamps, verifier signatures, every policy decision, written by the runtime, not by the agent.

## Files this ceremony exercises

- `examples/rb-repo-simple.yaml` — the 3-step template.
- `.claude/hooks/stepproof_pretooluse.py` — the enforcement point.
- `packages/stepproof-runtime/src/stepproof_runtime/verifiers.py` — `verify_file_exists`, `verify_pytest_passed`, `verify_git_commit`.
- `.stepproof/runtime.db` — audit log.

That's the whole thing.

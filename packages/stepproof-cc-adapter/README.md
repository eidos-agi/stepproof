# stepproof-cc-adapter

Claude Code adapter for StepProof. Wires the user's Claude Code harness to the StepProof runtime so `PreToolUse` actually enforces, not just observes.

## What this package ships

- **Hooks** (`src/stepproof_cc_adapter/hooks/`):
  - `stepproof_pretooluse.py` — the policy gate
  - `stepproof_sessionstart.py` — inject active runbook state via `additionalContext`
  - `stepproof_sessionend.py` — mark abandoned runs
  - `stepproof_precompact.py` — re-inject runbook state before compaction
  - `stepproof_userpromptsubmit.py` — soft-nudge when the prompt mentions a denied tool
  - `stepproof_permissionrequest.py` — log + optional `updatedInput` transform
- **Classification** (`action_classification.yaml`):
  - Tool → action_type + ring map
  - Bash pattern rules (psql → database.write → Ring 2/3)
  - Path glob rules (.env → deny, migrations/* → Ring 2)
- **Subagents** (`.claude/agents/stepproof/`):
  - `verifier-tier2.md` — Haiku, read-only via `disallowedTools`
  - `verifier-tier3.md` — Opus, read-only via `disallowedTools`
- **Slash commands** (`.claude/commands/`):
  - `/keep-me-honest`, `/runbook-start`, `/runbook-status`, `/step-complete`, `/approve`, `/runbook-abandon`

## Install

```bash
stepproof install
```

Writes all of the above to the current project's `.claude/`, registers the MCP server in `~/.claude.json`, and records a manifest at `.stepproof/adapter-manifest.json` so `stepproof uninstall` can reverse cleanly.

## Design reference

- [docs/ADAPTER_BRIDGE.md](../../docs/ADAPTER_BRIDGE.md) — latency budget, transport, state sharing, graceful degradation.
- [docs/LESSONS_FROM_HOOKS_MASTERY.md](../../docs/LESSONS_FROM_HOOKS_MASTERY.md) — exit-code contract, matchers, validator subagent pattern.

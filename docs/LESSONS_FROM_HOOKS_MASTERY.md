# Lessons from `claude-code-hooks-mastery`

Patterns extracted from [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery), adopted into StepProof where they fit. This document records what we're taking and why.

## 1. The Full Hook Lifecycle (12 events)

Claude Code exposes more enforcement surfaces than we initially documented. StepProof should use the right event for the right job:

| Event | StepProof Use |
|-------|---------------|
| `PreToolUse` | Policy gate on risky tools. Primary enforcement point. |
| `PermissionRequest` | Second gate — StepProof can auto-allow read-only ops, deny sensitive ones, or modify the tool input before allowing. Catches cases `PreToolUse` misses. |
| `PostToolUse` | Evidence capture (log the actual result, not just the claim). |
| `PostToolUseFailure` | Failure telemetry — surface patterns where workers keep hitting the same denial. |
| `SubagentStart` | Record verifier dispatch in the audit log, with `agent_id` and `agent_type`. |
| `SubagentStop` | Close the verifier run, record duration and result. |
| `SessionStart` | Load the active runbook state for this session; surface current step in status line. |
| `SessionEnd` | Mark any in-flight run as `abandoned` if the session ended without `stepproof run complete`. |
| `PreCompact` | Inject runbook state into the compacted transcript so the worker never forgets what step it's on. |
| `UserPromptSubmit` | Detect "I'm about to bypass" phrasing patterns and surface the active runbook as a reminder. |
| `Stop` | Persist final run state. |
| `Setup` | Initialize `.stepproof/` directory and local config on first use. |

## 2. Exit-Code Semantics Are The Contract

This is the single most important operational rule, and it's not negotiable:

| Exit code | Meaning |
|-----------|---------|
| `0` | Continue normally. Hook took no position. |
| `2` | **Block the tool call.** Stderr output is shown to Claude as the denial reason. |
| Any other exit / exception | **Must still exit 0.** A crashed hook must not break the session. |

StepProof adapters must wrap everything in `try/except` and exit 0 on any unexpected failure. A control-plane outage must degrade to "allow" (with loud logging), not "session dead." The audit log will record that a decision was skipped; the worker is not stranded.

## 3. JSON Over Stdin, Optional JSON Out

Claude Code feeds hooks JSON on stdin. For decision control, the hook writes JSON to stdout matching:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PermissionRequest",
    "decision": {
      "behavior": "allow" | "deny",
      "updatedInput": { ... },
      "message": "...",
      "interrupt": false
    }
  }
}
```

StepProof's `PolicyDecision` schema should mirror this exactly so the adapter is a thin translator, not a mapper. Our existing model (`allow | deny | transform | require_approval`) maps cleanly:

- `allow` → `{behavior: "allow"}`
- `transform` → `{behavior: "allow", updatedInput: ...}`
- `deny` → `{behavior: "deny", message: ...}` (exit 2 for PreToolUse)
- `require_approval` → `{behavior: "deny", message: "Approval filed: ...", interrupt: false}`

## 4. `uv` Single-File Scripts for Hooks

Hook scripts use `#!/usr/bin/env -S uv run --script` with PEP 723 inline metadata:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
#     "python-dotenv",
# ]
# ///
```

Zero-install, self-contained, no virtualenv bookkeeping. StepProof's Claude Code adapter should ship as uv scripts. This is the idiom.

## 5. Matchers Limit Blast Radius

`settings.json` hook entries take a `matcher` regex so hooks only fire on relevant tools:

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash|Write|Edit|mcp__.*__deploy.*",
      "hooks": [...]
    }
  ]
}
```

StepProof's installer should write matchers scoped to the tools actually governed by policy — not `""` (match all). This cuts overhead on read-only ops that don't need a round-trip to the control plane.

## 6. Validator Subagent Pattern (Exactly Our Verifier)

The `claude-code-hooks-mastery` repo defines the builder/validator pair in subagent frontmatter. The validator definition is essentially our Tier 2 verifier:

```yaml
---
name: validator
description: Read-only validation agent that checks if a task was completed successfully.
model: opus
disallowedTools: Write, Edit, NotebookEdit
---
```

**The critical insight:** read-only enforcement happens at the agent-definition layer, not as a convention. `disallowedTools` is a structural guarantee. StepProof's Tier 2 and Tier 3 verifier subagents should use the same mechanism — no validator agent is ever permitted write tools, period, enforced by the SDK, not by prompt discipline.

StepProof's adapter will ship validator agent definitions under `.claude/agents/stepproof/verifier-*.md` with the appropriate `disallowedTools` and tier-appropriate `model` (Haiku for Tier 2, Opus for Tier 3).

## 7. Agent-Level Hooks

Subagent definitions can declare their own hooks in frontmatter:

```yaml
---
name: builder
hooks:
  PostToolUse:
    - matcher: "Write|Edit"
      hooks:
        - type: command
          command: uv run $CLAUDE_PROJECT_DIR/.claude/hooks/validators/ruff_validator.py
---
```

This means StepProof's worker-agent SDK instance can have a `PostToolUse` hook that automatically captures evidence for the current step — worker writes a file, hook records the file path + hash into the evidence pool, and the `complete_step` call at the end pulls from that pool. Less boilerplate for the worker, better evidence fidelity for the verifier.

## 8. Graceful Degradation Is A Rule, Not A Habit

Every hook in the reference implementation wraps `main()` in:

```python
try:
    # hook logic
except json.JSONDecodeError:
    sys.exit(0)
except Exception:
    sys.exit(0)
```

Never crash. StepProof's adapter follows suit. If the control plane is down, the hook logs locally and exits 0. Enforcement degrades; the session doesn't.

## 9. `logs/` Is Convention, But Structured

Every hook appends to `logs/<hook_name>.json` as an array of events. It's naïve but durable: easy to grep, easy to replay, trivially resilient to partial writes (rewrite the whole array each append).

StepProof uses the same pattern for local audit buffering when the control plane is unreachable — writes to `.stepproof/audit-buffer.jsonl` and flushes when connectivity returns.

## 10. Team Orchestration Pattern For Runbook Authoring

The `specs/hooks-update-with-team.md` document is itself a template for how StepProof runbooks should be written:

- Named, resumable team-member sessions (`session-end-builder`, `session-end-validator`, etc.)
- Explicit `Depends On` graph per task
- Parallel vs. sequential flag per task
- Explicit `Acceptance Criteria` and `Validation Commands` at the bottom

StepProof can adopt this as the canonical **runbook authoring template** — a runbook isn't just a YAML schema, it's a document shape that ties builders, validators, dependencies, and acceptance criteria together. Roadmap phase 7 (human approval workflow) becomes easier when the runbook itself is already legible to a human reviewer.

## What We're *Not* Taking

- **TTS notifications** — not core to StepProof's mission; optional module at best.
- **Status-line customization** — useful for the adapter UX, but out of scope for the core product.
- **Command-namespace tooling** — StepProof ships CLI commands (`stepproof run start`, `stepproof step complete`, etc.), not custom slash commands. Slash commands can come later as an adapter ergonomic.

## Attribution

Patterns and implementation idioms extracted from the public BSL-1.1-licensed repository `github.com/disler/claude-code-hooks-mastery`. StepProof's design doesn't reuse their code directly; it reuses the operational patterns and the Claude Code hook contract, both of which are hard-won and worth documenting here so the reasoning persists.

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

---

# Part 2 — Deeper Scan

A second pass through the repo surfaced more patterns. Below: what else to adopt, and — equally important — what to explicitly reject and why.

## More To Adopt

### 11. `SessionStart` context injection via `additionalContext`

Hooks can inject text directly into Claude's context at session start:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "Session started at: ... \nGit branch: ... \nActive runbook: ..."
  }
}
```

**StepProof use:** every session boots with the active runbook, current step, recent verifier results, and allowed tools for this step injected into the worker's context automatically. The worker knows where it is before typing a character. Matches the `source` (`startup` / `resume` / `clear`) so resumed sessions get a richer briefing than fresh ones.

### 12. `PreCompact` to inject runbook state

When Claude Code compacts the transcript, runbook context is the first thing to get lost — silent reason for "I forgot which step I was on." The `PreCompact` hook runs right before compaction and can write into the compacted transcript.

**StepProof use:** inject the active `run_id`, `step_id`, `allowed_tools`, and last N verifier results so the post-compaction worker never forgets which runbook they're in. This is prevention, not cleanup.

### 13. `UserPromptSubmit` for early guardrail nudges

`UserPromptSubmit` fires *before* Claude processes the prompt. Cheaper than waiting for `PreToolUse` to block.

**StepProof use:** if the user says "let me just run psql real quick", surface a reminder in-context: *"Active runbook `rb-x` is at step `s3`. Allowed tools: `cerebro-migrate-staging`. Raw psql is denied at this step."* — without incurring a tool-call + denial round trip. Soft nudge; the hard block still happens at `PreToolUse` if they try anyway.

### 14. Meta-agent pattern → runbook-author agent

`meta-agent.md` is an agent whose sole job is to **generate other agents** from a description. It scrapes the docs, picks a color, writes the frontmatter, writes the system prompt, and writes the file.

**StepProof use:** a `runbook-author` subagent. Takes a plain-English description ("migrating service X to a new schema, needs staging smoke test, needs prod deploy gate") and produces a valid runbook YAML conforming to `schemas/runbook.schema.json`, with appropriate `required_evidence`, `verification_method` names, and tier assignments. Ships with the adapter. Eliminates the "runbooks are hard to write" friction.

### 15. Custom slash commands

They ship 15 custom slash commands in `.claude/commands/*.md`. Each is just a prompt-with-arguments that shows up as `/foo` in Claude Code.

**StepProof use:** ship `/runbook-start`, `/runbook-status`, `/step-complete`, `/step-evidence`, `/approve`, `/runbook-abandon`. The worker interacts with StepProof through the native Claude Code command UX, not a separate CLI. Keeps the feedback loop tight.

### 16. Session data directory

They keep per-session state at `.claude/data/sessions/<session_id>.json`.

**StepProof use:** `.stepproof/sessions/<session_id>.json` binds `session_id` to `run_id` and `current_step`. The `PreToolUse` adapter reads this; the CLI and subagents write it. Single local source of truth for "which run is this session running?"

### 17. `Setup` hook for first-time init

`Setup` fires on `claude --init` in a repo.

**StepProof use:** the installer registers StepProof via `Setup` — creates `.stepproof/`, writes default `settings.json` hook entries with matchers scoped to governed tools, drops the verifier subagent definitions into `.claude/agents/stepproof/`, and validates the control-plane URL. First-run ergonomics matter.

### 18. Graceful TTS fallback chain as a pattern (not the feature)

The TTS stack picks from ElevenLabs → OpenAI → local, failing silently down the chain. The *feature* (TTS) isn't ours. The *pattern* — a priority chain with silent fallback for optional enhancements — maps to StepProof's **verifier model fallback**: if Haiku is unreachable, try Sonnet; if that fails, return `inconclusive` and let the runbook's `on_fail` decide. Don't let a provider blip collapse verification.

---

## Explicit Rejections

Just as important as what to take: what to deliberately leave behind, with reasons.

### ✗ TTS notifications

Announcing "subagent started" through speakers is charm, not substance. StepProof's observability story is the **audit log**, not audio feedback. Reject.

### ✗ Engineer name personalization

*"Hello Daniel, your agent needs input."* Cute, not functional. StepProof tracks `human_owner_id` for attribution, not greeting. Reject.

### ✗ LLM-generated agent names on every prompt submit

Calling an LLM in the hot path of `UserPromptSubmit` to name the agent is a latency sink for zero governance value. Reject. `agent_id` is assigned at subagent spawn, tracked in the audit log, and never changes. No LLM involvement.

### ✗ Eight presentation-layer output styles

`yaml-structured`, `table-based`, `tts-summary`, `html-structured`, `ultra-concise`, `bullet-points`, `markdown-focused`, `genui`. Tutorial demo surface, not product. StepProof outputs structured audit records and structured verification results. One schema each. Reject.

### ✗ Whole-file log rewrites

Their pattern: read entire `logs/foo.json` array, append, rewrite the whole file. Works for a demo, breaks under concurrent writes or at log volume. StepProof uses append-only **JSONL** at the local buffer layer and ships to the control-plane audit log over batched HTTP. Reject the pattern; keep the instinct to log everything.

### ✗ Transcript backup on every `PreCompact`

They snapshot the full transcript before each compaction. Expensive, low-value — the audit log already captures the decision-relevant events. StepProof uses `PreCompact` to **inject runbook state** into the post-compaction context; it doesn't hoard transcripts. Reject.

### ✗ 13 crypto-analyst agents (haiku/sonnet/opus cross-matrix)

Their repo is a tutorial, and several agents are demos of "same task, different model." StepProof agents are narrow and purpose-built: `worker`, `verifier-tier1`, `verifier-tier2`, `verifier-tier3`, `runbook-author`, `policy-reviewer`. Model choice is a config parameter per verifier tier, not a separate agent. Reject the cross-product; keep the narrow-role instinct.

### ✗ Ollama fallback for LLM calls

Local Ollama is a nice option for privacy-sensitive inline LLM calls. StepProof's verifier is already a Claude Agent SDK subagent — adding an Ollama backend doubles the surface area for minimal gain. If a self-hosted verifier becomes a requirement, it's an adapter, not a hardcoded fallback. Reject for now.

### ✗ Interactive permission prompts as a core UX

The `PermissionRequest` hook in the reference implementation mostly logs and auto-allows read-only commands. For StepProof, interactive prompts *in the agent loop* are a worst-case UX — they break worker flow and add human latency to every operation. StepProof uses `require_approval` sparingly (high-risk runbooks only) and routes it to an **out-of-band** approval surface (Slack, web UI, mobile), not an inline Claude Code dialog. Reject inline-prompt-heavy permission UX; adopt the hook only for auditing and the rare transform case.

---

## Summary

| From hooks-mastery | StepProof position |
|--------------------|-------------------|
| 12+ hook event lifecycle | **Adopt** — use the right event for each enforcement concern |
| Exit-code contract (0/2/always-0-on-error) | **Adopt** — non-negotiable |
| JSON stdin + optional JSON stdout with `hookSpecificOutput` | **Adopt** — mirror their decision schema |
| uv single-file scripts | **Adopt** — zero-install adapter |
| Matchers to scope hooks | **Adopt** — don't match `""` |
| Validator subagent with `disallowedTools` | **Adopt** — structural read-only for verifiers |
| Agent-level hooks (frontmatter) | **Adopt** — worker auto-captures evidence via its own `PostToolUse` |
| Graceful degradation | **Adopt** — control-plane outage ≠ session death |
| `logs/` append convention | **Adopt the instinct, reject whole-file rewrites** — use JSONL |
| Team orchestration spec pattern | **Adopt** — runbook-authoring template |
| `SessionStart` `additionalContext` injection | **Adopt** — boot the worker already oriented |
| `PreCompact` state injection | **Adopt** — prevent the "forgot which step" failure mode |
| `UserPromptSubmit` for nudges | **Adopt** — cheap early reminder before `PreToolUse` denial |
| Meta-agent pattern | **Adopt** — build a `runbook-author` subagent |
| Custom slash commands | **Adopt** — `/runbook-start`, `/step-complete`, etc. |
| `Setup` hook for first-run init | **Adopt** — installer ergonomics |
| TTS-style fallback chain pattern | **Adopt the pattern, not the feature** — for verifier-model fallback |
| TTS notifications | **Reject** — charm, not substance |
| Engineer name personalization | **Reject** — track identity, don't greet |
| LLM-generated agent names on prompt submit | **Reject** — latency sink for zero governance value |
| Eight presentation output styles | **Reject** — we emit structured audit records |
| Whole-file log rewrites | **Reject** — JSONL append-only |
| Transcript backup on every compaction | **Reject** — we inject, not hoard |
| Cross-matrix per-model agent definitions | **Reject** — narrow roles, config-driven models |
| Ollama fallback built into core | **Reject for now** — adapter later if required |
| Inline permission dialogs as core UX | **Reject** — out-of-band approvals via Slack/web/mobile |

## Attribution

Patterns and implementation idioms extracted from the public BSL-1.1-licensed repository `github.com/disler/claude-code-hooks-mastery`. StepProof's design doesn't reuse their code directly; it reuses the operational patterns and the Claude Code hook contract, both of which are hard-won and worth documenting here so the reasoning persists.

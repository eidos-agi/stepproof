---
id: "ADR-004"
type: "decision"
title: "ADR 0004 \u2014 Phase 2b scope bound to Rhea-ruled minimum viable enforcement"
status: "accepted"
date: "2026-04-20"
---

Phase 2b ships the Claude Code adapter package (stepproof-cc-adapter) with: (1) PreToolUse hook, (2) 5 lifecycle hooks (SessionStart, SessionEnd, PreCompact, UserPromptSubmit, PermissionRequest), (3) client-side action_classification.yaml, (4) 2 verifier subagent definitions with disallowedTools, (5) 6 slash commands, (6) stepproof install/uninstall CLI with manifest reversal. Not included in Phase 2b per Rhea's surgical cuts: tiered auto-degradation modes (deleted), cryptographic attestation (defer Phase 3), approval-routing UI (defer Phase 3), runbook-author meta-agent (defer).

Enforcement defaults per cross-model review: fail-CLOSED on daemon unreachable (opt-in to fail-open via STEPPROOF_FAIL_OPEN=1). Bash patterns harden against sudo/path/env/command/backslash evasions. rm -rf variants caught. Silent classification-load failure replaced by fail-closed default.

Bootstrap constraint per Rhea ruling: Phase 2b development runs advisory-only — the hook is NOT installed into the development session. Enforcement validates on a post-ship fresh declared-plan run against a bypass-shaped stateful mid-task denial at step 10+, not step 1. If that validation fails (loops > pivots), Phase 3 does not proceed until the denial-message format is redesigned.

Rationale: Rhea's Dreamer/Doubter/Decider debate ruled ACCEPT with surgical cuts. GPT-5.2 codereview independently identified 4 HIGH issues (fail-open eviscerates enforcement, bash pattern evasions, rm -rf bypasses, silent classification-load failure) — all patched before this ADR was recorded. Two independent reviewers, same conclusions.

Full docs: docs/BOOTSTRAP_CONSTRAINT.md + docs/ADAPTER_BRIDGE.md. Debate trail: Rhea debate_id dfae2e0578d4. Lighthouse north star ns_6a9c5b21e351 tracks the validation gate.

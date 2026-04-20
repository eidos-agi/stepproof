---
id: TASK-0006
title: 'Phase 2b — stepproof-cc-adapter package: PreToolUse hook + install'
status: To Do
created: '2026-04-20'
priority: high
milestone: Phase 2 — Keep Me Honest + Claude Code Adapter
tags:
  - adapter
  - phase-2b
dependencies:
  - 'Phase 2a — MCP: stepproof_keep_me_honest tool'
acceptance-criteria:
  - '`stepproof install` writes 6 hook scripts + 6 slash commands + 2 subagents to .claude/'
  - settings.json gets hook registrations with appropriate matchers (not empty string)
  - .stepproof/adapter-manifest.json records what was installed for uninstall
  - PreToolUse hook correctly short-circuits Ring 0 actions without daemon round-trip
  - PreToolUse hook degrades gracefully when daemon unreachable (exits 0, buffers audit)
  - 'Live smoke: install into a scratch repo, start Claude Code, observe hooks firing
  on test tool calls'
---
New package: packages/stepproof-cc-adapter/. Ships the uv PreToolUse hook, classification.yaml (client-side action→ring mapping), SessionStart/End/PreCompact hooks, verifier subagent definitions with disallowedTools, 6 slash commands (/keep-me-honest, /runbook-start, /runbook-status, /step-complete, /approve, /runbook-abandon). stepproof install CLI subcommand writes these to .claude/, edits settings.json with matchers, edits .mcp.json. stepproof uninstall reverses via manifest.

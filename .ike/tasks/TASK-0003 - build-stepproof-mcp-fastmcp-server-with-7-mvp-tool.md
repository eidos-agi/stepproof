---
id: TASK-0003
title: 'Build stepproof-mcp: FastMCP server with 7 MVP tools'
status: To Do
created: '2026-04-20'
priority: high
milestone: 'Phase 1 — MVP: Local MCP + Embedded Runtime'
tags:
  - mcp
  - phase-1
dependencies:
  - Build stepproof-runtime
acceptance-criteria:
  - '`uv run stepproof-mcp` starts and announces 7 tools over stdio'
  - Each tool returns structured JSON matching the runtime API shape
  - Embedded mode spawns a local runtime without user config
  - Hosted mode forwards correctly when STEPPROOF_URL is set
  - Tool descriptions are clear enough for Claude Code to invoke correctly
---
Python FastMCP server exposing stepproof_run_start, stepproof_run_status, stepproof_step_complete, stepproof_policy_evaluate, stepproof_runbook_list, stepproof_runbook_get, stepproof_heartbeat. Embedded mode: if STEPPROOF_URL env is unset, spawn the runtime in-process on first tool call. Hosted mode: forward to STEPPROOF_URL. Stdio transport first; HTTP later.

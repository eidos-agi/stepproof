---
id: TASK-0005
title: 'Phase 2a — MCP: stepproof_keep_me_honest tool'
status: Done
created: '2026-04-20'
priority: high
milestone: Phase 2 — Keep Me Honest + Claude Code Adapter
tags:
  - mcp
  - phase-2a
  - keep-me-honest
dependencies:
  - 'Phase 2a — Runtime: plan validation + declared-plan run creation'
acceptance-criteria:
  - Tool registered in FastMCP with 7th tool count becoming 8
  - Tool description clearly differentiates from template-based run_start
  - 'Smoke test: declare plan with 2 steps, complete both, run transitions to completed'
  - 'Smoke test: declare invalid plan, get structured rejection'
updated: '2026-04-20'
---
New MCP tool: stepproof_keep_me_honest(intent: str, steps: list[StepDeclaration], environment: str) -> {run_id, current_step}. Thin wrapper over POST /plans/declare. Tool description emphasizes agent-declared contract semantics. Smoke test covers: agent declares plan, submits step evidence, plan advances, audit trail intact.

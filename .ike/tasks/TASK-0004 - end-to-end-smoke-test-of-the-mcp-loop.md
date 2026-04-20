---
id: TASK-0004
title: End-to-end smoke test of the MCP loop
status: To Do
created: '2026-04-20'
priority: high
milestone: 'Phase 1 — MVP: Local MCP + Embedded Runtime'
tags:
  - test
  - phase-1
dependencies:
  - Build stepproof-mcp
acceptance-criteria:
  - Script starts a run against rb-db-migration-and-deploy
  - Submits evidence for s1 and transitions it to verified
  - Blocks on s3 when prior step is unverified (negative test)
  - Audit log contains a complete causal chain for the run
  - All steps run in under 10 seconds
---
Script that spins up the MCP server, calls each tool once against the canonical example runbook (rb-db-migration-and-deploy), asserts state transitions and audit-log shape. Runs under `uv run pytest tests/smoke/` and in CI.

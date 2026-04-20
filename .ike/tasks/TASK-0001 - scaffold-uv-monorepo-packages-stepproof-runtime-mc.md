---
id: TASK-0001
title: Scaffold uv monorepo (packages/stepproof-runtime, -mcp, -cc-adapter)
status: To Do
created: '2026-04-20'
priority: high
milestone: 'Phase 1 — MVP: Local MCP + Embedded Runtime'
tags:
  - scaffold
  - phase-1
acceptance-criteria:
  - Root pyproject.toml declares uv workspace with 3 members
  - Each package has pyproject.toml + src/<pkg>/ + README
  - '`uv sync` at the root succeeds'
  - '`uv run python -c ''import stepproof_runtime, stepproof_mcp''` succeeds'
---
Root pyproject.toml with uv workspace members. Three packages: stepproof-runtime (FastAPI control plane), stepproof-mcp (FastMCP server), stepproof-cc-adapter (Claude Code uv hook scripts). Each has its own pyproject.toml, src layout, README. Add a root Justfile or Makefile for dev commands.

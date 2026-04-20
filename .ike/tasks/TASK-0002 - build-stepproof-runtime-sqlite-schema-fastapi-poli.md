---
id: TASK-0002
title: 'Build stepproof-runtime: SQLite schema + FastAPI + policy engine + verifier
  dispatch'
status: To Do
created: '2026-04-20'
priority: high
milestone: 'Phase 1 — MVP: Local MCP + Embedded Runtime'
tags:
  - runtime
  - phase-1
dependencies:
  - Scaffold uv monorepo
acceptance-criteria:
  - SQLite schema creates cleanly on startup
  - All endpoints return valid JSON for happy path
  - YAML runbook loader reads examples/rb-db-migration-and-deploy.yaml without errors
  - Policy engine correctly denies a Ring 3 action without an active runbook
  - Step completion dispatches a verifier and transitions state to verified/failed
  - Audit log records every decision with content-addressed payload hashes
  - Heartbeat expiration moves run to suspended then expired per ADR-0003 semantics
---
SQLite tables for runbook_templates, workflow_runs, step_runs, policy_decisions, audit_log, liveness_heartbeats. FastAPI endpoints: POST /runs, POST /runs/:id/steps/:id/complete, POST /runs/:id/heartbeat, POST /policy/evaluate, GET /runs, GET /runs/:id, GET /runbooks, GET /audit. YAML runbook loader from a configurable runbooks/ dir. YAML policy engine with priority ordering + ring-based classification + allow/deny/transform/require_approval/audit decisions + shadow mode. Tier 1 verifier dispatch as in-process function registry (subagent dispatch in phase 2).

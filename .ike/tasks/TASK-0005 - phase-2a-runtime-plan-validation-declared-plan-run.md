---
id: TASK-0005
title: 'Phase 2a — Runtime: plan validation + declared-plan run creation'
status: To Do
created: '2026-04-20'
priority: high
milestone: Phase 2 — Keep Me Honest + Claude Code Adapter
tags:
  - runtime
  - phase-2a
  - keep-me-honest
acceptance-criteria:
  - POST /plans/declare accepts a plan JSON, validates, creates a WorkflowRun, returns
  run_id
  - Plans missing required fields 400 with specific validation errors
  - Plans referencing unknown verification_method are rejected
  - Declared runs appear in /runs with source=declared
  - Audit log records plan.declared with full plan hash
  - Existing smoke tests still pass
---
Extend the runtime to accept agent-declared plans. Adds plan validator (structural rules per KEEP_ME_HONEST.md), POST /plans/declare endpoint that accepts an inline plan and returns a run_id, RunbookTemplate gets a source field (template|declared) so runs can be traced back to authorship. Validation enforces: every step has required_evidence + verification_method; methods reference registered verifiers; ring classifications are coherent; no verifier bypass.

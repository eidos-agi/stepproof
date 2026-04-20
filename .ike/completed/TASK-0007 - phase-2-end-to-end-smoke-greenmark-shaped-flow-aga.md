---
id: TASK-0007
title: 'Phase 2 — End-to-end smoke: bypass-shaped flow against the full loop'
status: Done
created: '2026-04-20'
priority: high
milestone: Phase 2 — Keep Me Honest + Claude Code Adapter
tags:
  - test
  - phase-2
dependencies:
  - 'Phase 2b — stepproof-cc-adapter package: PreToolUse hook + install'
acceptance-criteria:
  - Test runs unattended and produces a report
  - At least one PreToolUse deny observed and recovered from
  - Full audit chain reconstructable from the log
  - Measured latency per policy decision under 50ms p95
  - Report filed at docs/SMOKE_PHASE_2.md
updated: '2026-04-20'
---
Scripted Claude Code session (or equivalent simulation) that exercises the full loop: agent declares a keep-me-honest plan mirroring the the case study deploy flow, attempts raw psql at a step that forbids it, observes the deny + suggestion, pivots to the sanctioned tool, completes each step with evidence, audit log contains full causal chain. Measures denial-recovery rate, latency per enforcement decision, end-to-end duration vs the the case study 11-hour baseline.

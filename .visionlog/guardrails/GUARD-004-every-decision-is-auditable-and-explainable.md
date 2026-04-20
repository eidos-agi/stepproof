---
id: "GUARD-004"
type: "guardrail"
title: "Every decision is auditable and explainable"
status: "active"
date: "2026-04-20"
---

Every allow/deny/transform/approval decision writes an append-only audit record with: actor identity, runbook_id, step_id, action type, decision, policy_id, reason, suggested_tool (if deny), trust signals. Including allow decisions — they are the load-bearing record for "we ran this runbook correctly." Deny decisions without a suggested path forward are a bug.

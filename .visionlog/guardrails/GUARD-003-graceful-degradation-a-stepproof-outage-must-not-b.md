---
id: "GUARD-003"
type: "guardrail"
title: "Graceful degradation \u2014 a StepProof outage must not break the worker's session"
status: "active"
date: "2026-04-20"
---

Hooks and adapters must catch all exceptions and exit 0 on failure. If the control plane is unreachable, adapters log locally (JSONL buffer at `.stepproof/audit-buffer.jsonl`) and allow the action, flagging the decision as `skipped`. Audit log catches up on reconnect. Enforcement can degrade; the worker's session cannot be stranded.

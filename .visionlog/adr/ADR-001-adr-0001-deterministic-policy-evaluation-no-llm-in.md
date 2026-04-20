---
id: "ADR-001"
type: "decision"
title: "ADR 0001 \u2014 Deterministic policy evaluation; no LLM in the enforcement loop"
status: "accepted"
date: "2026-04-20"
---

Policy evaluation at the PreToolUse gate is deterministic. YAML rules by default, OPA Rego / Cedar as drop-in backends. Sub-ms target latency. LLM reasoning lives outside the enforcement path: inside the worker, inside Tier 2/3 verifiers at step-completion boundaries, inside runbook authoring, and inside shadow-mode review.

Rationale: reproducibility, audit replay, provider-outage independence, testability. LLM inline adds 10–100s of ms and non-determinism.

Full ADR: docs/adr/0001-deterministic-policy-evaluation.md

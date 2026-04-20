---
id: "ADR-002"
type: "decision"
title: "ADR 0002 \u2014 Four execution rings for runtime privilege"
status: "accepted"
date: "2026-04-20"
---

Every action class maps to Ring 0 (sandbox / read-only, always allowed), Ring 1 (reversible writes non-prod, runbook required), Ring 2 (non-reversible writes non-prod, runbook + verifier), Ring 3 (production-facing, runbook + verifier + trust threshold + optional approval). Unclassified actions default to Ring 3.

Rationale: graduated access, safe defaults for unknown tools, clear escalation without proliferating RBAC roles. Rings complement RBAC; RBAC still exists for human admin.

Full ADR: docs/adr/0002-four-execution-rings.md

---
id: "GUARD-005"
type: "guardrail"
title: "New rules ship in shadow mode; promote only after audit review"
status: "active"
date: "2026-04-20"
adr: "ADR-0001"
---

`shadow: true` on policies and runbooks evaluates normally and logs decisions but always returns `allow` at the adapter boundary. Operators review the would-have-blocked events in the audit log, tune false positives, then flip `shadow: false`. This is the safe on-ramp for all new enforcement logic.

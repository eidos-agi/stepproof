---
id: "ADR-003"
type: "decision"
title: "ADR 0003 \u2014 Three-property trust (identity / authority / liveness) with liveness as a gate"
status: "accepted"
date: "2026-04-20"
---

Trust decomposed into three independent properties each with its own decay timeline: identity (very slow, re-registration), authority (medium, runbook scope), liveness (rapid, heartbeat TTL). All three must hold: can_execute = identity_valid AND authority_valid AND liveness_active.

Liveness is a gate, not a score modifier — eliminates the ghost-agent failure mode where a high-trust worker that crashed keeps authorizing actions. Heartbeat protocol: TTL 300s default, refresh at TTL/2, suspend-then-expire semantics. Supersedes the earlier continuous trust-score sketch.

Full ADR: docs/adr/0003-three-property-trust.md

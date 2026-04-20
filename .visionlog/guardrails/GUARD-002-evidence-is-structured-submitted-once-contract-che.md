---
id: "GUARD-002"
type: "guardrail"
title: "Evidence is structured, submitted once, contract-checked at the API boundary"
status: "active"
date: "2026-04-20"
---

Every step declares `required_evidence` keys. The control plane rejects step completion if any required key is absent. Free-text "done" is never evidence. Verifiers consume concrete IDs, hashes, and refs — never prose. The evidence contract prevents silent partial verification.

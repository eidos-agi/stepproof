---
id: "GUARD-001"
type: "guardrail"
title: "Verifiers have no write tools"
status: "active"
date: "2026-04-20"
adr: "ADR-0001"
---

Tier 2 and Tier 3 verifier agents ship with structural read-only enforcement via the Claude Agent SDK `disallowedTools` frontmatter (or equivalent SDK-layer tool blocking). Verifiers cannot modify any system state — they surface problems, they do not fix them. Prompt discipline is a convention; this is a guarantee. A verifier that could act is not a verifier.

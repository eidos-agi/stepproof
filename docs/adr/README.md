# Architecture Decision Records

Numbered, dated, immutable records of architectural decisions. Format borrowed from [microsoft/agent-governance-toolkit](https://github.com/microsoft/agent-governance-toolkit/tree/main/docs/adr).

## Format

Each ADR follows this shape:

- **Status** — proposed | accepted | superseded-by-NNNN
- **Date** — ISO date
- **Context** — the situation forcing a decision
- **Decision** — what we're doing and why
- **Consequences** — what this makes easy, what it makes hard, what tradeoffs we're accepting
- **Follow-up work** — things we chose not to do yet but may come back to
- **Reference implementations** — prior art if applicable

## Discipline

1. Never edit an accepted ADR. Supersede it with a new one, marking the old as `superseded-by-NNNN`.
2. Number sequentially, 4-digit zero-padded.
3. Write ADRs *before* the code that implements them, not after.
4. Keep each ADR focused on one decision. If two decisions couple, split them and cross-reference.

## Index

- [0001 — Deterministic policy evaluation, no LLM in the enforcement loop](0001-deterministic-policy-evaluation.md)
- [0002 — Four execution rings for runtime privilege](0002-four-execution-rings.md)
- [0003 — Three-property agent trust (identity / authority / liveness)](0003-three-property-trust.md)

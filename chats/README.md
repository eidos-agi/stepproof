# Chats — Canonical Context

This directory preserves the conversations that seeded and shaped StepProof. These are **not disposable notes.** They are the origin documents. If you are a new contributor — human or agent — read them before touching the code or design.

## Why They're Here

StepProof exists because one agent, in one session, burned ten hours bypassing its own process — raw `psql` instead of migrations, ad-hoc scripts instead of the daemon, guessing at env vars instead of reading the topology. The frustration that produced StepProof is recorded verbatim in those transcripts, and so is the full reasoning for every architectural choice: why three verifier tiers, why runbook-step granularity rather than per-tool, why verifiers are read-only, why the audit log is non-negotiable.

The design docs in `../docs/` are the *conclusion*. These chats are the *derivation*. When a future change proposal contradicts a choice in `../docs/`, go back to the chat that produced it — the reasoning is there.

## Files

- **`2026-04-20-verification-agent-pattern.md`** — the founding conversation. Includes the original "why this exists" moment, the verification-agent pattern proposal, the three-tier verifier discussion, the naming conversation that landed on StepProof, and a Perplexity fact-check against 2026 prior art (Microsoft Agent Governance Toolkit, claude-code-hooks-mastery, Cloudflare Workflows v2, OPA/Cedar, verification-aware planning research).

## Conventions

- Filename format: `YYYY-MM-DD-<short-slug>.md`
- Append-only. Do not edit existing chats. Add new ones.
- Chats are the source of "why." The docs in `../docs/` are the source of "what" and "how."
- When a chat produces a decision that lands in the code or docs, reference it: "See `chats/2026-04-20-verification-agent-pattern.md` for the reasoning."

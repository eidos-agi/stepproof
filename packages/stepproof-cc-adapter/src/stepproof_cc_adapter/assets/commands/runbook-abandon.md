---
name: runbook-abandon
description: Mark an active StepProof run as abandoned. Idempotent — already-terminal runs are a no-op.
arguments: <run_id> [reason]
---

Parse $ARGUMENTS as `<run_id> [reason]`.

If the user did not supply a run_id, infer from `.stepproof/sessions/<session_id>.json` and confirm the intent before abandoning.

Call POST to the StepProof runtime: `/runs/<run_id>/abandon?reason=<reason or "user_abandoned">` — this is the abandon endpoint the SessionEnd hook also uses. There is no dedicated MCP tool for abandon in Phase 2b; use the HTTP endpoint via a small helper, or if the session has the runtime embedded, access it directly.

Report the final state to the user:
- If the run was active: "Run <id> abandoned; no further steps will be verified."
- If the run was already terminal: "Run <id> was already in state <x>; no change."

Per ADR-0003, abandonment is a clean terminal state — distinct from `suspended` (temporary, via heartbeat expiry) and `expired` (via extended absence). Do NOT use abandon to clean up runs that should have completed; that's a failure to investigate, not a state to paper over.

---
name: runbook-status
description: Show the current state of a StepProof run — current step, verified steps, evidence, audit trail.
arguments: [run_id]
---

Parse $ARGUMENTS:
- If empty, no run_id — try to infer the active run from the session state at `.stepproof/sessions/<session_id>.json`.
- Otherwise, treat $ARGUMENTS as the `run_id`.

Call `mcp__stepproof__stepproof_run_status` with the run_id. Present the response to the user as a concise summary:

- Run ID, template, environment, status
- Current step (with its description)
- Already-verified steps (with their `verification_result.reason`)
- Failed steps (if any) with the verifier's reason

If the user asks about audit, recommend calling `stepproof audit --run-id <id>` for the full event log.

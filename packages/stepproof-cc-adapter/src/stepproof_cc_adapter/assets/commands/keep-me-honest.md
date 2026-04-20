---
name: keep-me-honest
description: Declare a StepProof plan inline and bind yourself to it. Every step you declare becomes a verifiable checkpoint.
arguments: <plain-English intent>
---

Call `mcp__stepproof__stepproof_keep_me_honest` with:

- `intent`: "$ARGUMENTS" (or a clearer re-phrasing of the user's goal if needed)
- `environment`: infer from context (default "staging")
- `owner_id`: the user's identifier if known, else "unknown"
- `agent_id`: "claude-code-worker"
- `steps`: a list of step objects, each with:
  - `step_id` ("s1", "s2", ...)
  - `description` (what the step does)
  - `required_evidence` (list of concrete keys you'll submit — IDs/hashes, not free-text)
  - `verification_method` (one of the registered verifiers — call `stepproof_runbook_list` to discover)
  - `allowed_tools` (tools permitted during this step)
  - `verification_tier`: "tier1" (default) | "tier2" | "tier3"

If the call returns `{"status": "rejected", "errors": [...]}`, read the errors and fix the plan — do not bypass. Each error points at a specific step and field.

If accepted, the returned `run_id` is your contract for this session. Do not deviate without explicitly amending the plan.

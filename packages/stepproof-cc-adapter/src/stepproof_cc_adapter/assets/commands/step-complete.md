---
name: step-complete
description: Submit evidence for the current step of an active StepProof run. The runtime dispatches a verifier and advances on pass.
arguments: <run_id> <step_id> <key=value> [<key=value> ...]
---

Parse $ARGUMENTS as: `<run_id> <step_id> <key=value> [<key=value> ...]`.

If the user omitted run_id, infer from `.stepproof/sessions/<session_id>.json`.

Build an `evidence` dict by splitting each `k=v` pair. Types: stringify everything unless the key ends in `_count` or matches a known integer/boolean shape in the runbook's required_evidence contract.

Call `mcp__stepproof__stepproof_step_complete` with:
- `run_id`
- `step_id`
- `evidence`: the parsed dict

Report the verification result:
- On `pass`: announce the next step and what its `required_evidence` is.
- On `fail`: surface the verifier's `reason` so the user can fix the evidence or escalate. Do not retry with the same evidence.

---
name: approve
description: Approve a StepProof action that was gated behind require_approval. Placeholder for Phase 3 — currently logs the approval intent only.
arguments: <approval_id> [notes]
---

Parse $ARGUMENTS as `<approval_id> [notes]`.

**Phase 2b note:** full approval routing (Slack/web/mobile) is Phase 3. For now, log the approval to the audit trail by calling `mcp__stepproof__stepproof_policy_evaluate` or the equivalent approval-log endpoint, and inform the user that the approval has been recorded but that downstream enforcement does not yet consume it.

If the user expected the gated action to immediately proceed, explain that Phase 2b does not wire through approval-driven unblocks. Point them at `docs/ROADMAP.md` Phase 3.

For the Phase 2b shell: report `approval_id` + `notes` to the audit log via direct HTTP to the StepProof runtime if the MCP approval surface is not yet wired. Never auto-advance a run on the basis of a Phase 2b approval record.

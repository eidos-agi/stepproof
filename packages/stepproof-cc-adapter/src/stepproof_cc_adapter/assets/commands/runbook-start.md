---
name: runbook-start
description: Start a StepProof run from a pre-authored runbook template.
arguments: <template_id> [environment]
---

The user wants to start a runbook. Parse $ARGUMENTS as either:
- `<template_id>` alone (default environment: staging)
- `<template_id> <environment>`

If you don't know the template_id, first call `mcp__stepproof__stepproof_runbook_list` to show available runbooks to the user.

Then call `mcp__stepproof__stepproof_run_start` with:
- `template_id`: the provided template
- `environment`: staging | production | etc.
- `owner_id`: the user's identifier if known
- `agent_id`: "claude-code-worker"

Report the returned `run_id` and `current_step` to the user. Recommend calling `/runbook-status` to inspect progress or proceeding to the first step's work.

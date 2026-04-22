# Runbooks

A runbook is a YAML file that declares the steps of a ceremony and what
counts as evidence for each step. That's it.

## Where they live

```
<your-repo>/.stepproof/runbooks/*.yaml
```

One file per ceremony. One directory per repo. **No env vars, no config
file, no registry, no install command.** If a YAML file is in
`.stepproof/runbooks/`, StepProof sees it.

## What one looks like

```yaml
template_id: rb-deploy
version: 1.0.0
name: Deploy to production
risk_level: high

steps:
  - step_id: s1
    description: Run the full test suite
    required_evidence: [pytest_output_path, min_passed]
    verification_method: verify_pytest_passed

  - step_id: s2
    description: Merge the release PR
    required_evidence: [commit_sha]
    verification_method: verify_git_commit
```

Every step names (1) what evidence the agent has to produce, and (2)
what verifier reads real state to pass/fail. The verifier is the thing
the agent can't lie past.

## Using one

Two modes, same YAML.

**Pre-registered** — operator writes + commits the YAML; agent runs it:

```
stepproof_run_start  template_id: "rb-deploy"
stepproof_step_complete  run_id: ...  step_id: "s1"  evidence: {...}
```

**Inline (keep-me-honest)** — agent declares the plan at runtime, no
YAML needed. Use this for one-offs the agent is running on its own
recognizance.

## Getting StepProof's example runbooks into your repo

Copy them. They're examples, not magic:

```bash
cp /path/to/stepproof/examples/rb-stepproof-release.yaml \
   <your-repo>/.stepproof/runbooks/
```

Your repo, your copy. Upstream changes don't mutate your runbooks until
you re-copy.

## The multi-repo caveat

Today, the StepProof MCP server discovers runbooks from its own `cwd`.
Started in repo A → sees repo A's runbooks. Claude Code sessions that
span multiple repos hit this edge.

Planned fix: `stepproof_runbook_list(cwd="/path/to/repo")` — caller
names the repo per call. Same pattern as `git -C <path>`. When that
ships, the `STEPPROOF_RUNBOOKS_DIR` env var + the `examples/` fallback
will be removed. Only `<cwd>/.stepproof/runbooks/` will be in scope.

## Design principle

StepProof is about giving agents simple instructions they can't lie
about. That includes how the instructions themselves are distributed.
A runbook should be readable as text, live next to the code it
governs, version-controlled like every other config file, and not
require explaining where it came from. `.stepproof/runbooks/*.yaml`
is the whole story.

## Related

- [TIERS](TIERS.md) — adoption tiers.
- [KEEP_ME_HONEST](KEEP_ME_HONEST.md) — the inline-plan mode.
- [HONEST_LIMITS](HONEST_LIMITS.md) — runbook drift is real; named there.

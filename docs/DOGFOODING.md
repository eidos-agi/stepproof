# Dogfooding — Running Development on This Repo Under StepProof

This repo ships StepProof. As of Phase 2b + the verification-matrix
work, this repo also *uses* StepProof to gate its own development cycle.
The runbook is `examples/rb-stepproof-dev.yaml`. Every development
session starts with:

```bash
stepproof run start rb-stepproof-dev
```

Then every step advances only after its verifier passes against real
state. No override, no "just this once." If the ceremony blocks a
legitimate flow, the ceremony is wrong — fix the plan, don't route
around it.

## The gated cycle

| # | step | evidence | verifier |
|---|---|---|---|
| s1 | Declare intent | `intent_summary`, `scope` | `verify_pr_opened` |
| s2 | Failing test exists | `path`, `min_lines` | `verify_file_exists` |
| s3 | Implementation exists | `path`, `min_lines` | `verify_file_exists` |
| s4 | Full suite green | `pytest_output_path`, `min_passed` | `verify_pytest_passed` |
| s5 | User-visible docs updated | `path`, `min_lines` | `verify_file_exists` |
| s6 | Commit produced | `commit_sha` | `verify_git_commit` |
| s7 | Push to origin | `commit_sha` | `verify_git_commit` |

Step 7 is optional. If the work is local-only, abandon the run at s6
with `stepproof run abandon <run_id>`.

## Why there is no override

StepProof's thesis is that an agent (or human) **cannot be trusted to
voluntarily follow a process under pressure**. An override flag is the
shortcut the agent would take, reintroducing the exact failure mode
the tool exists to prevent. We tested this explicitly — the 2×2 in the
README shows baseline Claude cheating at 6/15 on a vague prompt.
Adding a `_DEV_OVERRIDE=1` backdoor here would mean shipping the
demonstration of the problem alongside the tool that solves it.

So: no override. Two paths only.

- **Legitimate "I need to do X outside the current step."** The step is
  underspecified. Amend the plan (via `stepproof_keep_me_honest` with
  an updated `allowed_tools` list) or abandon and declare a new run.
- **Catastrophic bootstrap failure — StepProof itself won't start.**
  `stepproof uninstall` is the deliberate exit. It's logged, reversible,
  and represents "we are doing repo recovery, not development, and the
  ceremony doesn't apply." That is distinct from "I want to skip a step
  because it's inconvenient."

## What to do when a verifier rejects you

Treat verifier rejection as a signal, not a blocker:

- `verify_file_exists` says the path doesn't exist → you didn't actually
  create the file; go create it.
- `verify_pytest_passed` says tests failed → fix the tests before
  advancing.
- `verify_git_commit` says the SHA isn't in the repo → commit hasn't
  happened yet; run `git commit`, then submit the new SHA.

The verifier is always reading reality. Fight reality, not the
verifier.

## What this repo's dogfooding proves

- The SDLC ceremony **generalizes beyond the guessing-game toy** — a
  real 7-step development flow works.
- The same primitives (`verify_file_exists`, `verify_git_commit`,
  `verify_pytest_passed`) cover a real-world release cycle.
- Strict enforcement is livable with well-designed plans. If the plan
  is wrong, the system tells you so by blocking a step you thought was
  reasonable. That's the feedback loop.

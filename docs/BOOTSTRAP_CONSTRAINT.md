# The Bootstrap Constraint

> *"You cannot develop the lock while standing in the room it locks."*
> — Rhea adversarial challenge ruling, 2026-04-20

## The Constraint

**StepProof enforcement does not govern the development of StepProof enforcement.**

Concretely: while Phase 2b (the Claude Code adapter that actually enforces) is being built, the author operates under **advisory-only** StepProof — `keep_me_honest` plans are declared, tracked, and audited, but the PreToolUse hook is *not installed* and no tool call is actually blocked.

After Phase 2b ships, enforcement validation happens on a **separate, fresh declared-plan run** against a scenario designed for that purpose (bypass-shaped, stateful mid-task denial injection per the Rhea ruling). The builder does not validate enforcement during the build.

## Why This Ruling Exists

Two reviewers arrived at this conclusion independently:

1. **Lighthouse** flagged `monolithic-loop` drift in iteration 3 — all ticks authored by one model. Pivot signal.
2. **Rhea adversarial challenge** (Dreamer/Doubter/Decider with model rotation) ruled that "dogfood while building" is a coherent-looking but incoherent-in-practice sequence:
   - If enforcement has a bug that blocks a needed build action, the builder bypasses it.
   - A known bypass undermines the model.
   - But a bug without bypass bricks the build.
   - This is unresolvable at the development layer. The only coherent bootstrap is: build advisory → ship → validate on a fresh run.

## What This Forbids

- Installing the Phase 2b PreToolUse hook into the session that is building Phase 2b.
- Wiring actual enforcement into the builder's own workflow during the build.
- Pointing Claude Code at the local adapter in a way that makes it enforce on the development session.

## What This Permits

- Declaring `keep_me_honest` plans via the MCP tool (advisory).
- Running the runtime, MCP server, and all smoke tests.
- Submitting step evidence via `stepproof_step_complete` (advisory — no tool calls are blocked).
- Ticking lighthouse against a north star for the build.
- Writing unit tests for the hook that subprocess-invoke it with fake stdin.

## After Phase 2b Ships

The enforcement validation sequence:

1. Install the adapter into a **scratch project**, not this repo.
2. Start a Claude Code session in that scratch project.
3. Declare a new `keep_me_honest` plan for a bypass-shaped task.
4. Mid-task (step 10+, not at step 1), run an action the runbook forbids at that step.
5. Observe: does the agent parse the deny + suggestion? Does it pivot to the suggested tool? Does it complete the overall task via the alternative path, or does it loop?
6. Measure — and record with model-version metadata (emergent behavior can regress across model updates, flagged by Rhea as a Phase 3 observability task).

## Why Ship Before Validating?

This looks backwards — shouldn't we validate before shipping? The ruling's answer: no. The validation is of *agent behavior under real enforcement*, which requires real enforcement, which requires a shipped adapter. Validating "whether the agent gracefully handles denials" cannot happen without the thing that generates denials. Thus the binary: ship the adapter (structurally sound, deterministic, tested via subprocess), then measure on a post-ship run.

If the post-ship run fails the gate (agent loops instead of pivots), Phase 3 does not proceed until the messaging or verifier-assisted-recovery redesign addresses it. This is the go/no-go gate — not a soft signal.

## Reference

- Lighthouse north star `ns_6a9c5b21e351`, iteration 3: pivot signal, drift_category `monolithic-loop`.
- Rhea challenge `debate_id dfae2e0578d4`, ruling: ACCEPT with surgical cuts.
- Related: [docs/OPEN_QUESTIONS.md §Denial-Retry Loop](OPEN_QUESTIONS.md).

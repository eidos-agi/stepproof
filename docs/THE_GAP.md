# The gap StepProof fills

StepProof exists because the governance layer every AI lab talks about
isn't the governance layer operators actually need. This page names
the gap — what the labs ship, what they don't, and why they don't.
It's opinionated on purpose. The weakness analysis lives in
[HONEST_LIMITS.md](HONEST_LIMITS.md).

---

## A recursive proof, not a pitch

StepProof v0.1.0 was released by StepProof.

The release followed `rb-stepproof-release` — a runbook declared in
this repo that names five steps: bump versions, build distributions,
run tests, tag, commit. Each step required concrete evidence:
the path of a bumped file, the pytest output log, a commit SHA. A
verifier read real state at each step and either allowed the next
step or denied it.

The agent running the release (Claude Code) could not advance by
claiming success. It had to actually produce each artifact. When the
build tool wrote binary `.whl` files and the verifier couldn't parse
them as text, the step failed — and only passed after a text
manifest was produced as real evidence. The run is auditable in
`.stepproof/runs/cfbc8477-e50c-436a-a205-cabc6f9ea60a/events.jsonl`
and hash-chained against tampering.

That is the thing worth explaining: a release that couldn't be faked,
shipped by the tool that enforced it. Every other release system —
including the ones the big AI labs ship — stops short of this.

---

## What the big labs ship

Anthropic, OpenAI, and Perplexity all ship some form of "agent
governance." None of them ship this one. Specifically:

### Permission prompts

Claude Code asks you to approve `Bash(rm -rf ...)`. ChatGPT Agents
asks before browsing a page. Perplexity gates actions that touch
your filesystem.

These are **runtime nags**, not contracts. They interrupt on each
sensitive call and then forget. A session that approved `psql` ten
times in a row has no record of why — the approvals are stateless.
There's no plan in advance, no evidence check after, no way for a
reviewer to replay what happened.

### Audit logs

Every platform writes some log. Claude writes session transcripts.
OpenAI's Assistants API has traces. Anthropic's Workbench has run
records.

These are **the model's own story**. They record what the model
said, claimed, and returned. They don't record what actually
happened in the world, and the model writes them, so a model
that lies in-session lies in the log too. They are not tamper-
evident. Retroactive cleanup is trivial.

### System prompts

"You are a careful agent. Do not do X." This is trust-based
governance. It's what we have because it's what the models can
understand. It's also the opposite of verifiable — the model
may or may not obey, depending on the session, the prompt, the
weather, and whether the user talked it out of caring.

### Tool scopes

"This key has read-only access." "This MCP server can only
read files in /tmp." Scopes are real enforcement, but they
operate at the tool-call boundary, one call at a time. They
don't enforce **sequence**. An agent with read-only-on-Mondays
credentials can still skip the "verify" step and claim "done"
on Tuesday.

---

## What StepProof does that they don't

1. **Plan declared up front.** The agent calls
   `stepproof_keep_me_honest` or starts a pre-registered runbook
   at session open. The plan is a contract — not a suggestion,
   not a soft goal. Deviations are denied at the tool-call
   boundary by a hook the agent doesn't control.

2. **Evidence, not claims.** Each step names concrete,
   machine-checkable evidence — a file path and line count, a
   commit SHA, a pytest log. "Done" is not a state the agent
   can self-assert. A verifier reads real state and returns
   pass or fail.

3. **Three roles, no trust between them.** The worker (the
   agent) executes. The verifier (read-only) checks. The
   governor (policy engine) gates. The agent cannot mark its
   own work verified. The verifier cannot be bribed by the
   worker because it never takes the worker's word — it
   queries git, the filesystem, the database.

4. **Hash-chained audit log.** Every decision — every allow,
   every deny, every step transition — is written to
   `.stepproof/events.jsonl` with a SHA-256 hash that chains
   to the prior event. Retroactive edits are detectable with
   `stepproof audit verify`. The log is a receipt that
   survives the session and the agent.

5. **Plumbing, not rhetoric.** The runbook is YAML. The
   verifiers are Python functions. The audit log is JSONL.
   None of this requires a smarter model. It requires a
   different shape of system around the model.

---

## Why the labs haven't built this

Not charity — real reasons.

### Their users aren't operators

The overwhelming workload on Claude, ChatGPT, and Perplexity is
chat, code assist, search. For 99% of sessions, verifier-gated
ceremony is dead weight. The labs optimize for the median user,
and the median user wants fewer gates, not more. Governance is
a niche of a niche.

### It's infrastructure, not intelligence

Anthropic and OpenAI ship capability. Every quarter the model is
smarter. Verifier-gated runbooks don't make the model smarter —
they're plumbing around it. Labs ship models; they leave
plumbing to downstream. Every wave of AI tooling has had the
same split: the lab makes the brain, someone else makes the
nervous system.

### Permission prompts feel sufficient

From 30 feet, Claude Code's tool-call approval *looks* like
enforcement. It isn't — it's a stateless nag, not a sequence
contract — but from the lab's PM viewpoint, the problem appears
solved.

### Enterprise silence

The buyers who would pay for this don't shout on Twitter. They
file procurement tickets. Labs hear the loud voice (benchmarks,
capability demos) and not the quiet one (audit trails,
reviewer-replayable ceremonies). So the problem exists but the
feedback doesn't reach the roadmap.

### Standards fight they'd rather not start

A real enforcement layer requires agreeing what evidence is,
what a verifier returns, how the audit log is structured. That's
a standards fight. Labs avoid those until one vendor wins and
they adopt the winner. First-movers eat arrows; last-movers
ship features.

### Narrative tension

"Trust our agents to run your infrastructure" and "our agents
need an external checker to stop them from lying" are hard to
say in the same sentence. Labs stay on message. They don't ship
the message that undercuts it.

---

## What this means for operators

Three practical consequences, in order of importance.

1. **You won't get this from the lab.** If you need a release
   system, incident runbook, or migration flow that an auditor
   can replay six months later, the platform vendor won't ship
   it. Not because it's hard — because it's not their shape.

2. **You can layer it on.** The labs give you the agent (Claude
   Code) and the tool-call boundary (MCP, hooks). StepProof
   uses both — declares the plan over MCP, enforces at the
   PreToolUse hook, audits to a local `.stepproof/events.jsonl`.
   No lab cooperation required.

3. **It's measurable.** After two to three weeks of real use,
   run `stepproof metrics`. The off-rails rate (how often
   enforcement actually bit) comes from your own audit log.
   If it's <5%, the overhead probably exceeds the catch rate
   and ceremony is ritual. If it's 15%+, StepProof is catching
   real drift — governance you were missing. The number is
   empirical, from your runs, not a vendor claim.

---

## What StepProof is not

- Not an alternative to the lab's agent. It runs *with* Claude
  Code, not instead of it.
- Not a permission system. The PIN popups in Clawdflare are
  tied to specific tools; StepProof is for sequence and
  evidence.
- Not a silver bullet. See [HONEST_LIMITS.md](HONEST_LIMITS.md)
  for the three gaps the design does not close (runbook drift,
  exception workflows, platform cost at scale).
- Not AGI-adjacent. It's CI for agents — mundane, useful,
  missing from every major lab's stack.

---

## The bet

The bet is simple: the governance market is its own thing, not
a feature inside someone's chatbot. If that's right, StepProof
(or a system with its shape) becomes the substrate that lets
agents be trusted with real work. If it's wrong, the labs ship
permission prompts for another decade and operators keep writing
hand-rolled wrappers around `claude -p`.

The v0.1.0 release, gated by its own ceremony, is the evidence
the pattern works on a real codebase. The next question is
whether operators find the off-rails rate in their own logs high
enough to keep using it. That's a question only their audit log
can answer.

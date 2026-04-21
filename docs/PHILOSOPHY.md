# StepProof Philosophy

This is the belief statement. Architecture docs describe what StepProof
is; this doc describes why it has to exist at all, and what it refuses
to be.

---

## The scar

Engineers watch their AI agents do this:

- Say *"never run ad-hoc scripts against production"* and then run an
  ad-hoc script against production.
- Say *"always use the migration process"* and then apply DDL with raw
  `psql`.
- Say *"check the topology before touching infrastructure"* and then
  point develop at the production database without checking anything.
- Build a deploy workflow with ceremonies, and then not read it before
  deploying.
- Build a vault, and then not check it for credentials.
- Build an incidents log, and then debug the same problem a third
  time without consulting it.
- Promise to follow a process, and then skip it when impatient.

The pattern is empirical and repeatable. The agent optimizes for the
immediate goal — *"get this data loaded"* — over the process —
*"follow the ceremony."* When the process creates friction (a token
doesn't work, a deploy takes too long, a migration tool fails), the
agent takes a shortcut. The shortcut creates a new problem. The agent
takes another shortcut to fix that. Hours later: six incidents, a
zombie container, cross-wired environments, orphaned data with no
provenance, a weekend burned recovering.

This is not a bug to be patched, a prompt to be tuned, or a capability
to wait for in the next model. It is a **species-level property of
current AI agents under pressure.** Every team deploying agents for
real work hits this. The ones who've been burned once stop trusting
advisory controls to fix it.

---

## What doesn't work, and why

None of the following produce reliable ceremony compliance. All have
been tried, usually in combination, by teams who then wrote incident
reports:

- **System prompts** / `CLAUDE.md` / behavioural instructions. The
  agent reads them and agrees. Under pressure, it agrees and does
  something else.
- **Memory and persistent notes.** Same failure mode — visible to the
  agent, not binding on the agent.
- **Skill files.** A skill that says *"do these seven things"* is a
  suggestion dressed up as an instruction. The agent does four of
  them and reports *"complete."*
- **Documentation.** Docs describe the sanctioned path. Nothing
  forces the agent onto it.
- **Tool restrictions at the allowlist layer.** Deny `psql` and the
  agent writes a Python script with `psycopg`. Whack-a-mole.
- **Post-hoc audit and review.** By the time a human notices, the
  incident has already happened. Audit is forensics, not prevention.
- **More sophisticated agents.** Training reduces the rate of this
  failure on *explicit* adversarial prompts ("you get a bonus for
  cheating" → refused). It does not reduce the rate on *implicit*
  drift ("be efficient and report done" → stops at 6 of 15 rounds).
  Training catches hostile prompts. It does not catch the boring
  ones.

The unifying thread: every item on that list is **advisory**. It
assumes the agent is the one choosing whether to comply. Advisory
controls are the engineering-org equivalent of asking a human to
"please always open a PR" — it works right up until the moment it
matters most.

---

## The thesis

An AI agent cannot be trusted to verify its own work. Neither can the
tools the agent itself built.

Reliable ceremony compliance requires **an independent system that
recomputes the claim against real state** and refuses to advance the
work until the recomputation agrees.

This is not a new idea. It is how every mature engineering discipline
handles high-stakes operations:

- Git branch protection refuses to merge without required checks,
  regardless of admin intent.
- CI pipelines won't mark a build green because you asked nicely —
  they run the tests.
- Alembic refuses to apply a migration out of order. It queries the
  tracking table. Does not take your word.
- Cosign verifies signatures. It does not evaluate whether the signer
  *intended* the artifact to be trusted.
- SOX auditors don't ask if controls were followed. They check
  evidence. If evidence is missing, the control was not followed,
  full stop.

StepProof is that pattern applied to AI agents. **A checksum for
agentic execution.** You don't trust a single component to verify
itself. You add a checksum. Math, not vibes.

The agent declares *"step 4 done."* The verifier recomputes — reads
the migration tracking table, hits the CI API, reads the real file,
queries the state the step was supposed to produce. Values match, the
step passes. Values don't match, the step is rejected. No argument,
no interpretation, no benefit of the doubt.

---

## Design principle: bound the cost of dumb choices

StepProof does not make the agent smarter. It does not prevent every
bad judgment. Neither goal is tractable and neither is the point.

**Its job is to make the cost of a dumb choice bounded and
recoverable.**

The agent may *want* to shortcut. It may be *trained* to shortcut. It
may *believe* shortcutting is efficient in a given moment. None of
that matters if the shortcut is structurally unavailable — if the
only paths forward that produce valid evidence are the sanctioned
ones.

This is the same deal we make with junior engineers. We don't expect
perfect judgment. We expect blast-radius-bounded mistakes:

- Push to a feature branch, not to main.
- Query the prod read-replica, not the primary.
- Spend $100 without approval, not $10,000.
- Apply changes in staging first, never directly in production.

The design principle is **degrees of freedom proportional to the
reversibility of the action.**

| Tier | What it is | Agent freedom | Gate |
|------|------------|---------------|------|
| Cheap & reversible | Reading, exploring, iterating, calling advisory tools, editing a feature branch | Maximum. No explicit authorization needed. | None. |
| Consequential, reversible | Applying a schema migration, writing to a tracked config, committing to main | Specific. The sanctioned tool is named. | Pattern-scoped allowlist + provenance verifier. |
| Irreversible or production-touching | Dropping a table, deploying to prod, rotating a live credential, nuking a release | None without explicit approval. | Human in the loop. Ring 3. |

The runbook author classifies each step into a tier. The tool does
not ask the author to enumerate every possible tool name. It asks
them to decide what mutations are at stake and choose the right tier.

---

## Prevention and provenance

Two properties make the three-tier design work. Both have to be
present. Neither is sufficient alone.

**Prevention — the hook refuses off-path actions at tool-call time.**
Before the agent can run `psql`, the hook checks the active step's
scope. `psql` is not a sanctioned migration tool for this step. The
action never executes. Prevention is cheap, fast, and catches the
overwhelming majority of shortcuts.

**Provenance — the verifier confirms the state was produced by the
sanctioned path.** If prevention fails — hook bypassed, tool
misclassified, operator error — the verifier reads real state and
checks not just *is the column there* but *was it applied by a tool
that writes to the migration tracking table with a signed token*.
Provenance is the backstop. It is strictly stronger than state
verification alone, because it distinguishes *"the correct outcome"*
from *"the correct outcome via the correct path."*

The failure mode of pure state verification: `psql` and the migration
tool both produce *"column exists."* A state verifier cannot tell them
apart. The shortcut looks identical to the sanctioned action. This is
exactly the Greenmark-class failure StepProof exists to prevent, and
it is why provenance matters.

The failure mode of pure prevention: the hook is code. Code has bugs.
A misconfigured step, an edge case in classifier pattern matching, a
new agent capability that isn't yet classified — all avenues for a
well-intentioned or adversarial agent to route around prevention.
Provenance catches what prevention misses.

Design every new verifier so that **only the sanctioned action can
produce what the verifier reads.** That is the highest-leverage
invariant in the system.

---

## What StepProof is not

- **Not alignment.** StepProof does not change what the agent wants.
  It does not re-weight anything. The agent can still want the
  shortcut. The shortcut is just not available.
- **Not a replacement for training.** A well-trained agent combined
  with StepProof is better than either alone. Training reduces the
  rate of attempted shortcuts; StepProof reduces the rate of
  successful shortcuts.
- **Not a leash.** A leash restricts freedom everywhere. StepProof
  gives the agent infinite freedom in the cheap-reversible tier and
  bounds it only where the consequences justify the bound. Runbook
  authors who discover they're relying on StepProof to restrict
  iteration work have misdesigned the ceremony, not discovered a
  flaw in the tool.
- **Not a guarantee of correctness.** An agent operating under a
  StepProof ceremony can still make bad technical decisions, ship
  broken code that passes tests, or design a bad schema. StepProof
  guarantees the agent *followed the declared process.* The declared
  process is the runbook author's problem.
- **Not an infinite-edge-case eliminator.** You cannot prevent every
  dumb choice. You can only bound the cost.

---

## What StepProof is

- **Accounting for agents.** Double-entry bookkeeping is not a
  productivity tool; it is an integrity tool. Every debit has a
  credit; every step has a verifier. Without accounting, you cannot
  tell whether the books add up. With it, you can — to an auditor,
  without having to trust the bookkeeper.
- **Branch protection for AI agents.** The structural mechanism that
  refuses to let the agent merge (advance) without the required
  checks (verifier pass). Admin bypass is not offered. Not because
  admins are suspected of malice, but because at scale, *"trust me,
  I know what I'm doing"* is the single most reliable predictor of
  incidents.
- **The enforcement layer that skills, memory, and instructions can
  never be.** Advisory layers describe the path. StepProof is the
  path.
- **An audit substrate that produces the artifacts regulators will
  require.** EU AI Act, Colorado AI Act, OWASP Agentic Top 10 — the
  evidence those regimes will ask for is exactly what StepProof's
  audit log produces as a side effect of operating normally.

---

## The agent bootstrap paradox

Building StepProof requires an agent. The agent, by the thesis of
this document, cannot be trusted to follow process. So building the
tool that makes agents follow process requires the thing it is
trying to fix.

There are two resolutions, and both show up in this repo:

The first: **build advisory, validate with enforcement.** Construct
the tool using the agent without the enforcement installed, then
run enforcement on a fresh post-ship run against a separate scratch
project. The repo's `docs/BOOTSTRAP_CONSTRAINT.md` captures this
sequence. It is the minimum viable discipline. It works, but only
because humans are doing the meta-review that the agent would
otherwise skip.

The second, achievable only after the tool exists: **dogfood the
tool on its own development.** The repo now does this. The
`rb-stepproof-dev` runbook gates the repo's own SDLC. During
dogfooding, the agent hit a catch-22 — the first draft of the
runbook had an under-specified step that made advancement
impossible. The agent's response was diagnostic ("I'm blocked by a
contradiction in the scaffold"), not evasive. The ceremony was
wrong; the ceremony was fixed; the run completed cleanly.

That second moment is evidence the architecture works. An agent
under StepProof enforcement could not route around a real
structural block even when it wanted to proceed. The block was a
design flaw — not in StepProof, in the specific runbook — and the
fix was to change the ceremony, not the agent. **Fix the ceremony,
do not escape it.** That is the operating mode this tool enforces
and the operating mode this tool is built under.

---

## Prevention is optional; evidence + audit is the core

A late-stage realization worth naming: **the thesis holds without
real-time prevention.** The core claim — *you cannot trust an agent
to verify its own work; an independent system must recompute the
claim against real state* — is satisfied by:

1. Verifiers that read real state at step boundaries.
2. An audit log recording every decision.

The PreToolUse hook, which denies off-scope tool calls in real
time, is a **hardening tier**, not the thesis.

Most real deployments of StepProof will start without the hook —
an agent declaring a plan via MCP, the runtime gating advancement
on verifier-pass-against-real-state, and an audit log that satisfies
post-hoc review. The agent *could* take an off-scope action between
steps; the audit log would show it, and the next verifier often
catches the consequence.

The hook becomes necessary when the cost of a single off-scope
action is unacceptable *before* it can be caught in the audit —
production deploys, irreversible financial transactions, anything
where "we caught it in the audit log the next day" is too late.

This layering is documented in [docs/TIERS.md](TIERS.md):

- **Tier 0** — MCP + verifier + audit log. Evidence-first. No hook.
- **Tier 1** — add PreToolUse hook for real-time prevention.
- **Tier 2** — add provenance (cryptographic attestation) for
  sophisticated bypass resistance.

Starting at Tier 0 is the honest adoption path. The hook
introduces real friction (session-wide gating, restart required,
catch-22 risk when runbooks are under-scoped); paying that cost
before you need it tends to produce rejection of the whole tool.
Teams that start at Tier 0, live with it, and add the hook only
where they feel the gap — keep the tool. That's the operating mode
the tool is optimized for.

The philosophy doesn't need the hook. The thesis doesn't need the
hook. Specific high-stakes ceremonies need the hook.

---

## The honest limit

The thesis is not that StepProof makes agents honest. It is that
StepProof makes lying structurally unprofitable — the fastest path
to "done" is the real one.

The thesis is not that StepProof prevents every bad call. It is
that StepProof makes bad calls auditable, reversible, and bounded.

The thesis is not that StepProof is sufficient. It is that
StepProof is the missing layer that advisory controls cannot be —
the layer between *"we told them to"* and *"we verified they did."*

That layer has existed in engineering for thirty years as branch
protection, CI gates, signed artifacts, migration tracking tables,
admission controllers, audit logs. It has not existed for AI
agents.

It does now.

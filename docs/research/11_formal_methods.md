# Formal Methods for Agent Behavior

LTL (Linear Temporal Logic), CTL (Computation Tree Logic), model
checking, runtime verification, and related academic work. Small,
rigorous, rarely productized. Relevant to StepProof as a source of
ideas rather than an active competitive threat.

## What's in this category

- **LTL / CTL specification.** Temporal logics for describing what
  should be true over time: "eventually X happens," "always X
  implies Y." Used in protocol verification, hardware verification,
  concurrent-system verification.
- **Runtime verification (RV).** Monitoring a running system against
  a formal specification, flagging violations. Active research
  community (RV conference); some industrial adoption.
- **Model checking.** Exhaustive exploration of a system's state
  space against a spec. SPIN, NuSMV, TLA+. Hard to scale to LLM
  agent state spaces.
- **TLA+ (Leslie Lamport).** Specification language for concurrent
  and distributed systems. Used at AWS and elsewhere to verify
  distributed protocols.
- **Property-based testing adjacent work.** QuickCheck, Hypothesis
  — empirical rather than exhaustive, but close in spirit.
- **Agent-focused formal methods.** Emerging research line: specify
  agent behavior in temporal logic, verify at runtime or in
  simulation. Papers exist; products don't yet.

## What formal methods can offer StepProof

- **A rigorous language for specifying ceremonies.** LTL-style
  constraints like "whenever s1 is active, Bash cannot run" are
  exactly what StepProof's scope rules express informally.
- **Model-checking a runbook.** Given a declared ceremony, can a
  tool tell you "this ceremony has a catch-22 — there's no
  sequence of agent actions that advances s2 under its current
  allowed_tools"? That's precisely the bug we hit in this session.
  Model-checking the runbook against expected verifier behavior
  could catch that class of bug at authoring time.
- **Runtime verification as monitoring.** Run the ceremony, watch
  for spec violations, alert on anomalies. Complements verifiers
  by catching emergent patterns.

## What it doesn't offer

- **Not a production-ready tool.** Model checkers are hard to
  operate. LTL specs are hard to author. Runtime verification
  frameworks (MOP, RV-Monitor, etc.) are research-grade.
- **Doesn't solve provenance.** Formal methods assume you know the
  state space. If the agent can produce the state two ways (psql
  vs sanctioned tool), formal methods don't distinguish without
  additional instrumentation.
- **Not an answer to "the runbook author forgot a tool."** Formal
  methods flag inconsistencies given a complete spec; they don't
  help the spec become complete.

## Where StepProof could benefit

Two specific places:

1. **Runbook authoring IDE with model-checking.** Before a runbook
   ships, a tool analyzes it and flags:
   - "Step s2's allowed_tools don't include any way to produce its
     required_evidence." (Catches the catch-22.)
   - "Two steps declare conflicting evidence schemas for the same
     path." (Catches authoring bugs.)
   - "A step's verifier depends on state that no prior step
     produces." (Catches ordering bugs.)
   This is a concrete increment — a linter / checker for
   `.yaml` runbooks.
2. **Runtime spec-monitor as meta-verifier.** Declare high-level
   invariants in LTL (or a simpler DSL), run a monitor alongside
   the runtime, alert on violations. Example invariant: *"Every
   step.complete is preceded by at least one tool call in that
   step's scope."* A monitor watches the audit log in real time and
   alerts if this invariant is ever violated — indicating the
   agent advanced without actually doing work.

Neither is v1. Both are credible v2+.

## Known unknowns

- Whether any published agent verification research directly models
  the StepProof-shape problem (declared multi-step ceremony +
  state-reading verifier + hook-enforced scope). Worth a literature
  search before claiming novelty of the combination.
- Whether tools like TLA+ are expressive enough to model ceremony
  semantics with useful fidelity. Probably yes for the control flow;
  unclear for the evidence schema.
- Whether runtime-verification tooling (MOP, LOLA, RV-Monitor)
  could be retargeted to StepProof's audit log. Plausible research
  collaboration.

## Representative sources

- Clarke, Emerson, Sifakis: model checking (Turing Award lecture,
  2007).
- Lamport: TLA+ (various papers and the `Specifying Systems` book).
- Runtime Verification (RV) conference proceedings.
- Agent-focused formal methods papers on arXiv (`cs.MA`, `cs.LO`).

## Date stamp

2026-04-20.

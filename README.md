# StepProof

**A verification-aware governance layer for agentic execution.**

StepProof enforces runbooks by turning every risky step into a verifiable checkpoint. Workers — human or AI — can't advance to the next step until an independent verifier confirms the current one against real system state.

---

## Why This Exists

Modern AI agents (Claude Code, Cursor, OpenAI Agents, in-house platforms) have the tools to do real work on production systems: run migrations, deploy services, rotate secrets, call APIs. They also have a documented failure mode: **bypassing their own process.** Raw `psql` instead of migration tooling. Ad-hoc scripts instead of sanctioned runbooks. Guessing at environment variables instead of reading the topology.

Advisory controls — docs, `CLAUDE.md`, memory, instructions — can be read and ignored. Hooks can block individual commands but not enforce **process compliance**. StepProof closes that gap.

The premise is simple: **an agent cannot be trusted to voluntarily follow a process. The system has to force it, and an independent verifier has to prove it was followed.**

The concrete cost of not having this: see [Case Study: one observed session](docs/CASE_STUDY.md) — 11 hours of preventable debugging across six incidents (environment cross-wiring, migration bypass, zombie containers, Docker cache persistence, ad-hoc scripts, silent null violations). Every one of them maps to a specific verifier step StepProof would have run. That's not hypothetical. That's one session.

---

## How It Works

```
┌──────────────┐    proposed action     ┌──────────────────┐
│   Worker     │ ─────────────────────▶ │  Policy Engine   │
│   Agent      │                        │   (Governor)     │
└──────────────┘                        └──────────┬───────┘
       │                                           │ allow / deny
       │   claims step complete + evidence         │
       │                                           ▼
       │                                 ┌──────────────────┐
       └────────────────────────────────▶│  Control Plane   │
                                         │  (Workflow/State)│
                                         └──────────┬───────┘
                                                    │ dispatch
                                                    ▼
                                         ┌──────────────────┐
                                         │  Verifier Agent  │ (read-only)
                                         │  Tier 1/2/3      │
                                         └──────────┬───────┘
                                                    │ pass/fail
                                                    ▼
                                            next step unlocked
                                            or worker blocked
```

Three roles, no trust between them:

1. **Worker** — full tool access, executes steps, produces evidence. Cannot mark its own work verified.
2. **Verifier** — read-only access to git, CI, DB, deploy APIs, logs. Checks claims against real state. Returns structured pass/fail.
3. **Governor** — intercepts actions via hooks, enforces policy, gates advancement on verifier results.

Verification happens in three tiers to keep cost predictable:

- **Tier 1** — deterministic scripts (SQL checks, status endpoints, git queries). Cheapest, covers 80–90% of checks.
- **Tier 2** — small verifier model (e.g., Haiku) for unstructured output: logs, diffs, qualitative fit.
- **Tier 3** — heavyweight model for rare, high-stakes guardrail questions. Opt-in per step.

---

## Design Docs

- [Architecture](docs/ARCHITECTURE.md) — roles, components, end-to-end flow
- [Runbook Model](docs/RUNBOOKS.md) — schema and authoring guide
- [Policy Engine](docs/POLICY.md) — decision model, hook integration
- [Verifier Fabric](docs/VERIFIERS.md) — tiers, interface contract
- [Hook Integration](docs/HOOKS.md) — pseudo-code for `PreToolUse`, `complete_step`, verifier dispatch
- [Lessons from `claude-code-hooks-mastery`](docs/LESSONS_FROM_HOOKS_MASTERY.md) — idioms, exit-code contract, validator subagent pattern
- [Prior Art](docs/PRIOR_ART.md) — catalog of related work
- [Prior Art — Deeper Dive](docs/PRIOR_ART_DEEPER.md) — per-source extraction with StepProof implications
- [Architecture Decision Records](docs/adr/) — numbered, dated, immutable decisions
- [Roadmap](docs/ROADMAP.md) — MVP sequence
- [Case Study: one observed session](docs/CASE_STUDY.md) — the 11-hour session that validated the entire thesis
- [Keep Me Honest](docs/KEEP_ME_HONEST.md) — agent-declared plans as first-class runbooks
- [Open Questions](docs/OPEN_QUESTIONS.md) — the three hardest seams, worked through honestly
- [Adapter Bridge](docs/ADAPTER_BRIDGE.md) — how Claude Code hooks talk to StepProof
- [OWASP Agentic AI Top 10 Mapping](docs/OWASP_MAPPING.md) — StepProof's coverage of each risk category
- [Positioning vs Microsoft AGT](docs/POSITIONING.md) — where we overlap, where we differ, what to consume

## Regulatory Context

Agent governance is becoming legally actionable:

- **EU AI Act** — high-risk AI obligations effective **August 2026**.
- **Colorado AI Act** — enforceable **June 2026**.
- **OWASP Agentic AI Top 10** — first formal agentic risk taxonomy, published December 2025. See [OWASP_MAPPING.md](docs/OWASP_MAPPING.md) for StepProof's coverage of each.

## Origin

The founding design discussion and fact-check are preserved in [`chats/`](chats/). Read those before making consequential changes — the *why* is there, not in the conclusion docs.

---

## Status

**Pre-alpha.** Design-phase. The architecture is documented; implementation is starting now. The first wedge is Claude Code `PreToolUse` hook enforcement plus deploy/migration verifiers. Broader agent-platform adapters come after.

See [docs/ROADMAP.md](docs/ROADMAP.md) for the MVP sequence.

---

## Positioning

StepProof is not "a tool that stops Claude from being sloppy." It is a **runtime system that forces workers — human or agent — to prove each critical step before the next one is unlocked.**

The pattern generalizes beyond DevOps:

| Domain | Example |
|--------|---------|
| DevOps / SRE | Migrations, deploys, incident runbooks, rollbacks |
| Security | Access changes, secret rotation, containment steps |
| Data | Backfills, schema promotions, model releases |
| Enterprise workflows | Approvals, reconciliations, regulated operations |

Every one of these is the same primitive: **durable workflow + bounded action permissions + evidence-based verification + audit trail.**

---

## Built By

[Eidos AGI](https://eidosagi.com) — building agents that can be trusted with real work by making trust a system property, not a character trait.

## License

BSL 1.1 — see [LICENSE](LICENSE).

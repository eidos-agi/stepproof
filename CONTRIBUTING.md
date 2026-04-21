# Contributing to StepProof

StepProof is pre-alpha. The design is settling; the implementation is starting.

## Where to Engage

- **Architecture discussion** — open a GitHub Issue labelled `design`. The docs in `docs/` are the current source of truth; propose changes as PRs.
- **Bug / behavior reports** — once code exists, use `bug` issues with a minimal reproduction.
- **New verifier methods** — these will live in a dedicated package once scaffolded. For now, sketch the method signature in an issue.

## Principles

When proposing changes or features, check them against the core principles:

1. **Verifiers are read-only.** If a proposal gives a verifier write access, it is rejected.
2. **Evidence is structured.** Free-text "done" is not evidence. Concrete IDs, hashes, refs.
3. **Policy decisions are deterministic where possible.** Model-based judgement is a last resort.
4. **Every deny must point somewhere.** Blocking with no suggested alternative is a bug.
5. **Audit is non-negotiable.** If a decision isn't in the audit log, it didn't happen.

## Code Style

TBD — will land with the first implementation PR. Expect: Python for the control plane, TypeScript for Claude Code adapters, standard formatters.

## Licensing

Business Source License 1.1 — see [LICENSE](LICENSE). Converts to Apache 2.0 on 2030-04-20. By contributing, you agree your contributions are licensed under the same terms.

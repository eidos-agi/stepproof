# Enforcement Tiers

StepProof works at three layered tiers. You pick what you need for
each ceremony. You do **not** have to install everything on day one.

## The tiers

### Tier 0 — Evidence + Audit (no hook, no provenance)

**What's installed:** a `.mcp.json` registering the StepProof MCP.
A runbook YAML in your project. That's it.

**What you get:**
- Declared multi-step ceremony as a first-class artifact.
- Per-step structured evidence requirements.
- Verifiers that read real external state at step boundaries.
- Advancement gated on verifier pass.
- A hash-chained, tamper-evident audit log on disk
  (`.stepproof/runs/*/events.jsonl` + `.stepproof/events.jsonl`).
  Verify with `stepproof audit verify`.

**What you don't get:**
- **Real-time denial** of off-scope tool calls. The agent *could*
  call an off-scope tool. The audit log would show it, and the
  verifier at the next step boundary might catch the consequences,
  but the tool call itself isn't intercepted.

**When this is enough:** most internal SDLC work, most data
workflows, most investment/analysis processes where the post-hoc
audit trail is sufficient for compliance and where you trust the
agent to mostly honor its declared plan.

**Cost:** ~5 minutes to set up. No Claude Code restart. No hook
install. Zero session friction.

---

### Tier 1 — Prevention (PreToolUse hook)

**What's installed:** everything from Tier 0, plus
`stepproof install --scope project` which writes hooks into
`.claude/hooks/` and registers them in `.claude/settings.json`.

**What it adds:**
- Real-time denial of tool calls that aren't in the current step's
  `allowed_tools`.
- Hook-enforced `psql`-vs-`cerebro-migrate` scoping before the
  action executes.
- Structural gate: Ring 2+ actions denied if no active run, or if
  prior steps aren't verified.

**What it costs:**
- Session-wide hook: every tool call in the project goes through
  the hook. When a run is stuck, the session is effectively locked
  until you resolve (fix the runbook, or `stepproof uninstall`).
- Requires restarting Claude Code after install.
- Harder to debug than Tier 0 — wrong scope = trapped agent.
- Test pollution risk — if your repo's tests run subprocesses with
  the hook active and no isolated state dir, they can flake.

**When this is worth it:** high-stakes ceremonies where a single
off-script tool call has real cost. Production deploys, production
migrations, financial transactions, healthcare workflows, anything
where catching-after-the-fact is unacceptable.

**Cost:** ~10 more minutes on top of Tier 0, plus session restart.
Meaningful operational overhead during the ceremony.

---

### Tier 2 — Provenance (cryptographic attestation)

**What's added:** sanctioned tools emit forgery-resistant
attestations (signed rows, signed artifacts, tokens the agent
cannot produce). Verifiers check the attestations, not just
observable state.

**What it adds:**
- Resistance to sophisticated bypass where the agent finds a way
  to produce the same observable state through an unsanctioned
  path.
- Cryptographic audit trail (the sanctioned tool, not just the
  agent's report of it, signed for the record).

**What it costs:**
- Real engineering per sanctioned tool. You either wrap the tool
  to add attestation emit, modify the tool itself, or operate it
  in a sandbox that captures proof of execution.
- Signing key management, KMS integration, key rotation.

**When this is worth it:** regulated domains with external audit
demands (SEC, FDA, EU AI Act Annex III high-risk categories),
multi-party trust scenarios (the operator of StepProof is the
entity being audited, and the auditor doesn't trust them).

**Cost:** weeks-to-months of engineering per tool. Not a v1
concern.

**Status in StepProof today:** `verify_round_marker` is the one
provenance-shaped verifier. The pattern exists; the library
doesn't. See
[docs/research/09_provenance_and_signing.md](research/09_provenance_and_signing.md).

---

## How to pick

For most first adopters:

> **Start at Tier 0. Use it for a week on real work. Add Tier 1 for
> specific high-stakes ceremonies only when you feel the gap.**

The common failure mode of adopting governance tooling is to over-
install on day one, get friction-burnt, and reject the tool. Tier 0
has zero session friction and still produces the audit log and
evidence-at-boundary that compliance wants.

## Matrix — what each tier prevents

| Failure mode | Tier 0 | Tier 1 | Tier 2 |
|---|---|---|---|
| Agent skips a step entirely | ✅ gated | ✅ gated | ✅ gated |
| Agent claims completion without evidence | ✅ verifier rejects | ✅ verifier rejects | ✅ verifier rejects |
| Agent produces evidence in the wrong shape | ✅ verifier rejects | ✅ verifier rejects | ✅ verifier rejects |
| Agent uses an off-scope tool mid-step | ⚠️ caught in audit, not blocked | ✅ denied in real time | ✅ denied in real time |
| Agent produces correct observable state via unsanctioned tool (psql-vs-migrator) | ⚠️ verifier might miss (state looks right) | ✅ denied by classifier+hook | ✅ rejected by provenance check |
| Sophisticated attacker forges sanctioned-tool output | ❌ not protected | ❌ not protected | ✅ cryptographically rejected |
| Agent's drift-under-vague-prompts (the real common case) | ✅ caught in audit; verifier rejects advancement | ✅ denied + audit | ✅ denied + audit + crypto |

**For the drift case** (which is the most common real failure
mode, per the observed session that motivates this whole tool),
**Tier 0 is sufficient.** The agent that stops at 6/15 and claims
done cannot pass the verifier; the run is stuck; the audit log
shows it. Tier 1 adds real-time prevention on top; Tier 0 catches
it at the step boundary.

## Migration path

Start at Tier 0. After the ceremony runs for real and you have
concrete experience with what's happening:

- **If you never feel the gap between "caught in audit" and
  "denied in real time,"** stay at Tier 0. You've found the right
  level for your work.
- **If a specific ceremony is high-stakes enough that you want
  prevention**, install the hook *for that project's ceremony
  scope* — the hook activates when a run is active, so it only
  fires during ceremonies.
- **If you hit sophisticated-bypass risk** (regulator or adversary
  concern), plan Tier 2 provenance instrumentation for that
  specific workflow.

Do not skip ahead. Tier 0 teaches you what you actually need.

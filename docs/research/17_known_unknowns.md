# Known Unknowns

What this research corpus does not answer, how to answer it, and
what would change if we did. Kept here so claims in the other docs
can be qualified rather than overstated.

## Questions this research cannot currently answer

### Existence questions (is there prior art I haven't seen?)

1. **Is there a stealth startup assembling the same combination?**
   - How to check: YC batch announcements, Product Hunt, pre-seed
     funding announcements in "AI governance," AI-security Discord
     / Slack communities.
   - Impact if yes: StepProof's novelty-of-assembled-system claim
     weakens; priority via open-source date and preprint matters more.

2. **Does Anthropic / OpenAI / Google have internal tooling
   matching StepProof's shape?**
   - How to check: engineering blog posts, hiring posts, eng talks,
     SDK release notes, MCP spec evolution.
   - Impact if yes: medium threat. Providers typically ship their
     internal tools only once they productize them.

3. **Does an existing academic paper describe the combined
   architecture?**
   - How to check: arXiv cs.AI, cs.SE searches with terms from
     `00_methodology.md`; Google Scholar; Semantic Scholar.
   - Impact if yes: citation required; possibly reframe StepProof
     as "an open-source implementation of the [published] pattern."

### Capability questions (will the problem shrink over time?)

4. **Will future model generations reduce implicit drift enough to
   make runtime enforcement less critical?**
   - How to check: published evaluation benchmarks on agent
     reliability; the paired with/without results over time on each
     new model generation.
   - Impact if yes: StepProof's value narrows to high-stakes
     regulated domains; broad SDLC adoption weakens.
   - Best estimate: some narrowing is likely, but the floor for
     "acceptable failure rate" in high-stakes domains is near-zero,
     which training doesn't reach.

5. **Will structural-enforcement patterns become native to agent
   harnesses (Claude Code, Cursor, Agents SDK)?**
   - How to check: product announcements from each vendor.
   - Impact if yes: StepProof's value shifts from "provides the
     enforcement primitive" to "provides the verifier library + audit
     substrate + paired methodology on top of native enforcement."
   - Best estimate: partial native support within 12-24 months.
     Full-stack native implementation unlikely in that window.

### Economic questions (who will pay and how much?)

6. **What do regulated-industry buyers actually pay for AI
   governance tooling?**
   - How to check: Styra/OPA Enterprise pricing; Drata/Vanta
     contracts; AGT enterprise licensing; Credal pricing.
   - Impact: shapes commercial strategy and moat-building.

7. **How much does a deterrable AI-agent incident cost?**
   - How to check: incident reports from enterprises running agents
     on production. Hard to get publicly; talk to practitioners.
     Greenmark-shape session-cost estimates are one anchor.
   - Impact: the cost of an incident sets the willingness-to-pay
     for enforcement.

### Adoption questions

8. **Will Claude Code / MCP remain the dominant agent harness and
   protocol, or will the ecosystem fragment further?**
   - How to check: MCP adoption metrics, cross-vendor support,
     OpenAI's stance on MCP.
   - Impact: if MCP fragments, per-harness adapter work becomes
     more expensive.

9. **Will ISO 42001 certification become a procurement requirement
   in regulated sectors?**
   - How to check: enterprise RFPs starting to require 42001;
     consultants' reports on adoption rates.
   - Impact: StepProof's audit-log output's value goes up sharply
     if buyers need documented ceremony controls for certification.

### Technical questions

10. **Is there a practical way to verify provenance without
    modifying sanctioned tools?**
    - How to check: supply-chain security literature on retrofit
      attestation; runtime-wrapping patterns for existing tools.
    - Impact: if yes, provenance verifier library becomes
      significantly easier to build out; if no, provenance
      coverage grows slowly.

11. **How expressive can the evidence schema be before it becomes
    harder to author than allowed_tools?**
    - How to check: build prototype, let a few runbook authors
      (including non-engineers) use it, measure time-to-write a
      working runbook.
    - Impact: evidence-first authoring is only a win if the schema
      is ergonomically better than tool enumeration.

12. **Will the bash-pattern scoping approach extend cleanly to
    all the scoping the mature product needs?**
    - How to check: prototype for the real runbooks on the
      roadmap; see what breaks.
    - Impact: if patterns are insufficient, a richer scoping DSL
      is needed (e.g., path globs, API-endpoint patterns, content
      matchers). Real engineering lift.

## The "could be wrong about the thesis itself" list

A separate class of uncertainty. Pure research cannot answer these;
only deployment and evaluation can.

- **Is the "bound cost of dumb choices, not prevent all dumb
  choices" framing correct?** Or does the regulated buyer actually
  want elimination, not bounding? (The framing is likely right but
  the buyer conversation is the only way to validate.)
- **Does the paired with/without methodology produce results that
  hold up to adversarial review?** (Rhea has questioned this; we
  agreed the methodology is credible. An external reviewer from the
  ML-evaluation community would be a stronger validator.)
- **Does "ceremony over efficiency" land with non-engineering
  buyers (finance, healthcare, legal) as clearly as it does with
  engineers?** (Unknown. Likely needs domain-specific reframings.)

## How to update this doc

When a known unknown gets answered:

- Update the relevant item in place with the answer and the
  source.
- Move it to "resolved" (archive the text elsewhere or mark clearly).
- Cross-reference in whichever other research doc the new
  information belongs in.
- Date-stamp the update.

When a new unknown surfaces:

- Add it here with the check methodology and impact assessment.

This doc is the meta-check: before making a strong claim in any
other doc, scan this file. If the claim depends on something
listed here, qualify it in the target doc.

## Date stamp

2026-04-20.

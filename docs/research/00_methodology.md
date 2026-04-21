# Research Methodology

How this research corpus is sourced, what counts as evidence, and how
to keep it honest.

## Sources

In descending order of weight:

1. **Primary product documentation.** Official docs, GitHub repos,
   architecture pages of the tool in question. Closest to ground
   truth.
2. **Official blog posts and engineering writeups.** Usually
   higher-fidelity than marketing pages.
3. **Preprints on arXiv** (cs.AI, cs.SE, cs.PL). For academic work
   especially in formal methods and agent verification.
4. **Published papers** in ACM, IEEE, NeurIPS, ICLR, when relevant.
5. **Regulatory texts** directly — the actual AI Act, the actual
   NIST RMF, not summaries.
6. **Conference talks and interviews** from engineers on these
   systems — useful for "how it actually works" vs "how it's pitched."
7. **Community discussion** (GitHub issues, Hacker News threads,
   specific Discord / Slack conversations) — used only for signal,
   never cited as authoritative.

**Low-weight sources we avoid citing as fact**: Gartner-style analyst
reports, marketing pages, LLM-summaries-of-summaries, third-hand
accounts.

## Evidence standards

Each claim in the research docs aims to be at least one of:

- **Directly verifiable** from the cited source.
- **Structurally obvious** from the architecture of the thing in
  question (e.g., "a content-filtering library cannot enforce step
  ordering because it doesn't see steps" — true by construction).
- **Clearly marked as uncertain** if neither of the above applies.

We flag uncertainty rather than hide it. A doc that says *"I don't
know whether X does Y; here's how to find out"* is more useful than
one that fills the gap with plausible-sounding invention.

## How to refresh

### Quarterly sweep

- **arXiv search terms**:
  - `"agent governance" LLM`
  - `"runbook enforcement" OR "ceremony enforcement"`
  - `"LLM tool use" "policy"`
  - `"agent verification" LTL OR CTL`
  - `"MCP governance" OR "Model Context Protocol" security`
  - `"LLM audit log" OR "agent provenance"`
- **Product-launch radar**:
  - Anthropic Agent SDK changelog
  - OpenAI Agents SDK / function-calling updates
  - Temporal LLM integration announcements
  - Any new "agent governance platform" on Product Hunt, TechCrunch AI
    section, YC batches
- **Standards advancement**:
  - OWASP Agentic Top 10 update status
  - NIST AI RMF implementation updates
  - ISO 42001 related guidance drops

### Trigger-based updates

- **A new tool ships in an adjacent category**: spot-check the
  category doc for accuracy. If it's a meaningful competitor, note
  in `16_competitive_watch.md`.
- **Regulation advances** (enforcement date, new state law,
  implementing guidance): update `13_regulation_eu_co.md` and
  `12_standards_owasp_nist_iso.md`.
- **A StepProof claim gets challenged** (by Rhea, by a reviewer, by
  a customer conversation): update `17_known_unknowns.md` with the
  challenge and the resolution.

## What this corpus is NOT

- **Not an exhaustive literature review.** It covers the categories
  that are load-bearing for StepProof's positioning. Adjacent-adjacent
  work (e.g., differential privacy, content moderation at scale, LLM
  evaluation benchmarks) is out of scope unless it directly bears on
  ceremony enforcement.
- **Not a pitch deck.** The goal is accuracy, not persuasion. If a
  competitor's tool closes part of StepProof's gap, the doc says so.
- **Not a static snapshot.** Every doc has a date stamp noting last
  meaningful update. Old information is flagged as such, not deleted.

## Conflict-of-interest note

StepProof is built by Daniel Shanklin / Eidos AGI. This research is
written from inside that effort. Bias toward StepProof's positioning
is possible. Countermeasures:

- Where a category closes StepProof's gap, the doc says so plainly.
- Every "gap" claim includes a search methodology for checking it.
- `17_known_unknowns.md` explicitly names the things this research
  could be wrong about.

If you're reading this to evaluate StepProof as a competitor or
buyer, treat the positioning docs with appropriate skepticism — the
category surveys are more neutral.

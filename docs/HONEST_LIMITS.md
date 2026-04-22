# Honest limits

StepProof works by converting "are we following process?" from a
reviewer-dependent question into a boolean that a verifier can answer
from real state. That conversion has costs and failure modes. This
page names them so operators can plan around them rather than
discover them mid-release.

Three gaps surfaced during review that the marketing doesn't cover:

1. **Runbooks go stale.** The verifier reads real state, but the
   runbook names commands whose output format can shift.
2. **Exceptions happen.** Real releases sometimes ship with a step
   failing. The process for that must not require disabling the
   enforcement.
3. **Platform cost is real.** Someone has to own the runbooks, the
   verifiers, and the exceptions. At 100-person scale that is 1-3
   FTE, not zero.

Each section below is what we actually tell operators — not the demo
pitch.

---

## 1. Runbook drift and verifier brittleness

### The problem

A runbook says: "`pytest` output must contain at least N passing
tests." The verifier parses pytest's output. Six months later pytest
ships a minor version whose default summary line changes from
`3 passed in 0.12s` to `3 tests passed (0.12s)` — and the verifier
starts returning `verdict=inconclusive` for every green build.

The same shape applies to `git` (porcelain format changes), `terraform
plan` (JSON schema revisions), `pytest-cov` (coverage JSON key
renames), `npm audit` (severity taxonomy changes).

### How we mitigate it

- **Verifiers own a format version.** Each verifier declares which
  version of each upstream tool it targets. If the tool's actual
  version doesn't match, the verifier returns `inconclusive` with a
  specific reason — not `pass`, not `fail`. Inconclusive gates the
  step the same way `fail` does, so nothing ships on a
  misunderstanding.
- **Evidence carries raw artifacts, not just parsed summaries.** The
  `.stepproof/runs/<id>/step-<id>.json` keeps the tee'd raw output.
  When a verifier breaks, the audit trail lets you see whether the
  underlying check passed — so you can patch the verifier and
  re-verify the historical run without re-running the step.
- **Runbook versioning.** Runbooks carry `template_version`. A run
  started against v1.2.0 is pinned to v1.2.0 even if v1.3.0 ships
  mid-run. Changes to verifiers that require new evidence shapes
  land as a template_version bump, not a silent mutation.

### What operators should expect

When a tool upstream of StepProof changes output format, **you will
get a wave of inconclusive verdicts until the verifier is patched.**
This is the safe failure mode — nothing ships under a broken check —
but it does mean someone on the platform side has to keep pace with
upstream tool releases. Budget for it.

---

## 2. Exceptions: when a step fails but the change must ship

### The problem

It is 23:00. The coverage verifier returns `fail` because a
generated file didn't get excluded from the coverage calculation.
The underlying change is correct and the hotfix is time-sensitive.
What do you do?

There is a wrong answer ("add `--no-verify`, merge, deal with it
Monday") and a right answer. StepProof's job is to make the right
answer the easier one.

### How we handle it

StepProof supports two documented escape hatches, both of which
leave a durable paper trail:

#### a. Waiver (evidence-bearing override)

A waiver is a step that records *who* overrode *what verifier* on
*which run*, *why*, and *by which other reviewer's approval*. It
appears in the audit log as `action_type=step.waiver` with its own
policy_id. The step is then allowed to advance as if it had
verified.

```
stepproof waive --run-id <id> --step <sid> \
  --reason "pytest-cov 5.0 drops generated/* from totals differently" \
  --approved-by <github_handle> \
  --link https://github.com/org/repo/pull/1234
```

The waiver is only accepted when the verifier's verdict is `fail` or
`inconclusive` — you cannot pre-emptively waive a step that hasn't
been attempted. And waivers carry a policy ring: some steps
(production deploy gates, security scans) are configured to accept no
waiver, forcing rollback or genuine fix.

#### b. Declared-plan override

For cases where the runbook itself is wrong for the situation at hand
(a cherry-pick hotfix, an emergency rollback), the operator can
declare an alternate plan and have it approved by a reviewer. The
plan's hash lands in `.stepproof/plans/<hash>.yaml` before any step
executes. This is the `keep_me_honest` flow documented in
`KEEP_ME_HONEST.md`.

### What operators should expect

**Both paths are slower than `--no-verify`. That is the point.** A
waiver takes ~2 minutes (write reason, get approval, attach link). A
declared plan takes longer because it is a structural change. If
your release cadence can't absorb that friction, either your runbook
is wrong or the change isn't actually ready.

We consider both waivers and declared-plan overrides first-class —
every real process has escape hatches; the cost of pretending
otherwise is developers building their own, in the dark.

---

## 3. The platform team cost

### The problem

A StepProof rollout at 100-person engineering scale requires someone
to own:

- the runbook library (5-40 templates across the product)
- verifier maintenance (track upstream tool changes)
- waiver policy (who can waive what)
- audit review (is the chain verifying green each week)
- onboarding (new runbooks for new surfaces — mobile, ETL, ML)

At 100-person org headcount, our honest estimate is **1-3 FTE** of
distributed platform ownership. Not a dedicated team — but real
calendar time across platform eng, SRE, and security.

### What this does to the ROI math

The quintile ROI analysis in `POSITIONING.md` frames adoption in
terms of catch value vs. ceremony overhead. The platform FTE load is
a third term in that equation:

```
value  =  (catches × incident_cost)
        - (ceremony_overhead × runs)
        - (platform_fte_cost)
```

At Q1-Q2 usage (<5% off-rails rate), the platform_fte term dominates
and adoption is a loss. **This is why `stepproof metrics` is a
first-class command.** The point is to measure, not assume, which
quintile a team is actually in — and to have a defensible answer
when the platform bill is questioned.

### What operators should expect

If your off-rails rate after 2-3 weeks of Tier 0 use is <5%, **do not
roll out Tier 1**, and consider whether even Tier 0 is earning its
ongoing cost. The honest answer may be "not yet — revisit when a
higher-stakes surface lands." StepProof is configured to let you
make that call with real data, not a promise.

---

## How to interpret `stepproof metrics`

```
OFF-RAILS RATE:          N.N%
  → Q1-Q2: enforcement mostly dormant; overhead likely exceeds catches
  → Q3: enforcement catching some drift; break-even to modest gains
  → Q4: enforcement catching meaningful drift; sustained gains
  → Q5: enforcement catching heavy drift; high-stakes domain fit
```

Read this after every N runs. If the number drifts down over time,
either the agents got better or the verifiers got weaker — investigate
which. If it drifts up, either the surface got harder or a runbook
went stale — investigate which. The number alone is just a signal;
what to do about it is still a judgment call.

StepProof exists to make the signal legible, not to replace the
judgment.

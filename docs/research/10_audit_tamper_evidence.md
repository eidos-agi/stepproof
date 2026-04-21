# Audit Logs and Tamper Evidence

Certificate Transparency, Rekor, append-only Merkle logs, HSTS-like
pinning patterns. How to make an audit log that a regulator can
trust — or more precisely, how to make it expensive to forge.

## What's in this category

- **Certificate Transparency (CT).** Public, append-only Merkle logs
  of TLS certificates. Browsers require certs appear in a CT log
  before trusting them. Operated by multiple independent log
  operators; tampering requires compromising multiple operators.
- **Rekor (Sigstore's transparency log).** Append-only log of
  signed-artifact metadata. You can't prove a signature was valid
  at time T without an entry in Rekor.
- **Binary Transparency / Package Transparency.** Extending CT-like
  patterns to software distribution.
- **Hypersigner / Keyless patterns.** Short-lived signing keys +
  transparency log = keys can't be secretly reused.
- **Append-only databases / ledgers.** Amazon QLDB, Google
  Spanner's atomic commit, Immudb. Databases that give cryptographic
  integrity guarantees.
- **Merkle tree persistence.** Hash-chained state so any modification
  to past entries invalidates the root. Used in Git (indirectly),
  ZFS, IPFS, blockchains.

## Why this category matters to StepProof

StepProof's audit log is currently a plain SQLite table. It's
**informationally complete** (every decision is captured) but it
is **not tamper-evident**. Anyone with write access to the file can
modify past entries without detection.

For most use cases this is fine — the audit log lives on the same
host as the runtime, and if you compromise that host you have
bigger problems. But for regulated domains (finance, healthcare,
high-assurance deploys) and for multi-party trust scenarios
("StepProof's operator is the same entity being audited"),
tamper-evidence is a real need.

## The progression of audit-log integrity

| Level | Implementation | Regulator accepts? |
|---|---|---|
| 1. Plain log | SQLite rows, file on disk | Internal only; not external audit |
| 2. Append-only with signatures | Each entry signed by the runtime's key | Low-stakes external |
| 3. Hash-chained | Each entry includes a hash of the previous | Medium-stakes; tampering obvious on read |
| 4. Merkle-root publication | Runtime periodically publishes the tree root to a public or third-party log | High-stakes; regulator-acceptable |
| 5. Transparency log (CT-style) | Audit log is in an independently-operated transparency log | Highest assurance |

StepProof is at Level 1 today. Level 2 is cheap to add (a key,
signatures on rows). Level 3 is also cheap (a hash column referring
to the previous row's hash). Level 4 and 5 require infrastructure.

## A specific target: `verify_audit_chain_intact`

In `docs/CEREMONY_DB_MIGRATION.md`, s8 proposes a
`verify_audit_chain_intact` verifier — recomputes the expected
audit-tail hash and compares. That's a Level 3 pattern. Cheap,
effective, and makes modification detectable on any read.

Implementation shape:

- Add a `prev_hash` column to the `audit_log` table.
- On insert, compute `hash(prev_hash || row_content)` and store as
  this row's `hash`.
- `verify_audit_chain_intact` walks the table in order, recomputes
  hashes, confirms they match. Any modification to a past row
  invalidates every hash downstream.

This is the minimum-viable tamper-evidence for StepProof. Ship it
as part of Increment 4 per the ceremony spec's roadmap.

## Where this stops being enough

A single-host hash chain is tamper-evident to **readers**, but a
sufficiently motivated attacker who controls the host can rewrite
the entire chain and the new hashes are internally consistent.

Defense against host-level attackers requires externalizing the
trust anchor. Options:

- **Periodic publication of the tail hash** to a public log (e.g.,
  a tweet, a public git repo, a CT log). Attackers can rewrite
  history, but they can't retroactively change what was published.
- **Third-party timestamping** of the hash. RFC 3161 timestamp
  authorities, or OpenTimestamps on Bitcoin.
- **Append-only storage with external integrity** (AWS QLDB is
  designed for this).

For most StepProof deployments, Level 3 is enough. For some
regulated ones, Level 4+ will be required.

## Known unknowns

- Whether any deployed agent-governance system today has
  tamper-evident audit logs. None identified.
- Whether regulators explicitly require append-only / tamper-evident
  logs for AI decisions. EU AI Act Article 12 (logging requirements)
  implies this direction but doesn't mandate cryptographic
  techniques.
- Whether customers will pay for Level 4+ in practice. Probably a
  subset of finance/health will. Most internal-dev-tool
  deployments won't.

## Representative sources

- Certificate Transparency: `certificate.transparency.dev`, RFC 6962.
- Rekor (Sigstore transparency log): `sigstore.dev/rekor`.
- Amazon QLDB documentation.
- OpenTimestamps: `opentimestamps.org`.
- RFC 3161 (Time-Stamp Protocol).

## Date stamp

2026-04-20.

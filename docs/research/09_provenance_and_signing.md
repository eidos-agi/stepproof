# Provenance, Signing, and Supply-Chain Attestation

Cosign, Sigstore, SLSA, SBOM, in-toto, TUF. The software supply-chain
security stack. Not directly an agent tool, but **the canonical model
for what StepProof's provenance verifiers should look like.**

## What's in this category

- **Sigstore (CNCF).** Keyless signing for software artifacts.
  Fulcio (CA), Rekor (transparency log), Cosign (client).
- **Cosign.** Signs container images and other artifacts. Verifies
  signatures before admission / deploy.
- **SLSA (Supply-chain Levels for Software Artifacts).** Maturity
  framework for build-pipeline integrity. Defines attestations a
  build pipeline emits about what it produced.
- **SBOM (Software Bill of Materials).** Machine-readable inventory
  of what's in a software artifact. SPDX, CycloneDX formats.
- **in-toto.** Framework for software-supply-chain integrity.
  Attestations bind build steps to evidence.
- **TUF (The Update Framework).** Signed metadata framework for
  secure software distribution.
- **OCI artifacts with signatures.** Container registries support
  Cosign-signed artifacts; admission controllers verify signatures.

## Why this category matters to StepProof

**This is the architectural pattern StepProof's provenance
verifiers should imitate.**

The supply-chain world faced the same structural problem StepProof
faces:

- *"How do I know this artifact was produced by the sanctioned
  build pipeline, not by an attacker running their own build?"*

Their answer: the sanctioned pipeline **signs** the artifact with a
key the attacker doesn't have. Verification checks the signature.
Forgery is cryptographically infeasible.

Apply to StepProof:

- *"How do I know the migration was applied by cerebro-migrate,
  not by raw psql?"*

Answer: cerebro-migrate writes a **signed attestation** to the
migration tracking table — a row with a token that only
cerebro-migrate can produce (via a key it holds, or via a
sanctioned-channel write). psql can write to the table, but can't
forge the attestation. Verifier reads the table, checks the
attestation, rejects any row without a valid signature.

The pattern generalizes:

| Action | Sanctioned channel writes | Attestation |
|---|---|---|
| Apply migration | Migration tool | Signed row in tracking table |
| Ship code | CI pipeline | Signed commit / signed artifact |
| Deploy to prod | Deploy pipeline | Signed deployment record |
| Approve Ring 3 action | Human via approval UI | Signed approval event with human identity |

**State verification alone is insufficient** — "column exists" can
be produced by any SQL client. **Provenance verification is
strictly stronger** — "column was added via an attested run of
cerebro-migrate at time T by agent A" is cryptographically checkable.

## The StepProof parallel

StepProof's `verify_round_marker` is a provenance-lite pattern. Only
the sanctioned game MCP writes `round-N-done.txt`. The agent has
no tool to write that file. The verifier reads the file; if it
exists, the sanctioned action ran; if not, it didn't. No crypto,
but the structural property holds: **only the sanctioned action
produces what the verifier reads.**

Generalizing this principle is the deepest leverage in the design:

> **Every verifier should read something only the sanctioned action
> can produce.** Where the sanctioned action can't be instrumented
> to emit a unique token, wrap it; where wrapping isn't possible,
> accept weaker state verification but flag the verifier as weak.

## What adoption looks like

- **Short-term, no-crypto:** use structural invariants the agent's
  tool surface can't reach. The `round_marker` pattern. This works
  because the agent's allowed_tools don't include direct file
  writes to the state dir. Weak against adversaries who can escape
  tool scope; fine against drift.
- **Medium-term, token-based:** sanctioned tools emit
  project-specific tokens (cryptographically bound or structurally
  unique) into their output. Verifiers look for the tokens.
- **Long-term, cryptographic:** sign attestations with keys held by
  sanctioned tools (via KMS or sigstore-style keyless). Verifiers
  verify signatures against a known key set. Cryptographically
  forgery-resistant.

Most real deployments will land somewhere between medium and long
term. The engineering cost of full crypto is real; the value for
most domains (internal SDLC) is marginal over token-based.

## Known unknowns

- How to bootstrap provenance for existing sanctioned tools that
  don't emit attestations. Options: wrap them (StepProof-specific
  shim), petition their authors to add attestation support (slow),
  or run them in a sandbox that captures execution proof (expensive).
- Whether a StepProof provenance library (generic attestation
  emitters and verifiers) becomes a real sub-project. Probably yes
  at v2+.

## Representative sources

- Sigstore: `sigstore.dev`.
- SLSA: `slsa.dev`.
- in-toto: `in-toto.io`.
- TUF: `theupdateframework.io`.
- SPDX and CycloneDX SBOM specs.

## Date stamp

2026-04-20.

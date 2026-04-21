# Regulation — EU AI Act, Colorado AI Act, and US State Activity

The binding regulatory regimes that create legal demand for
ceremony-level AI governance. Unlike the standards in doc 12, these
carry compliance obligations and penalties.

## EU AI Act

- **Status**: adopted 2024; phased entry into force through 2025–2027.
- **High-risk AI obligations effective August 2026.**
- **Territorial scope**: applies to providers and deployers whose AI
  is used in the EU, regardless of where the provider is based.

### High-risk AI categories relevant to agents

Annex III of the AI Act lists high-risk use cases. Several are
directly implicated by agentic systems:

- Credit scoring and financial services decisions.
- Employment decisions (hiring, promotion, termination).
- Access to essential services (benefits, insurance, emergency
  response).
- Education access and assessment.
- Critical infrastructure management.
- Law enforcement decision support.
- Migration, asylum, and border management.
- Administration of justice.

Any agentic system making or materially influencing decisions in
these categories falls under high-risk obligations.

### Key obligations for high-risk AI

Paraphrasing, not quoting verbatim — confirm against the published
text before acting on any specific clause:

- **Risk management system** across the AI's lifecycle.
- **Data and data governance** — quality, representativeness.
- **Technical documentation** — how the system works, what it does.
- **Record-keeping** (Article 12) — automatic event logs of the
  AI's operation.
- **Transparency and provision of information to users.**
- **Human oversight** — meaningful human control capability.
- **Accuracy, robustness, cybersecurity.**
- **Conformity assessment** before market placement.
- **Post-market monitoring** and incident reporting.

**Record-keeping (Article 12) is the clause most directly served by
StepProof's audit log.** Every policy decision, every verifier
result, every advancement — with timestamps, policy_ids, and a
stable run identifier — is exactly what Article 12 asks for.

Human oversight is served by Ring 3 approval workflows (StepProof's
increment 3).

### Penalties

Non-compliance fines are substantial (up to 7% of global turnover
or €35M for prohibited AI; proportionally lower for other breaches).
Large enough to change procurement behavior.

## Colorado AI Act (SB24-205)

- **Status**: signed 2024; effective **June 2026**.
- **Scope**: covers developers and deployers of "high-risk
  artificial intelligence systems" making consequential decisions
  about Colorado residents.

### Key obligations

- **Reasonable care** to protect consumers from algorithmic
  discrimination.
- **Impact assessments** before deployment and periodically.
- **Consumer notice** and rights around appealing adverse decisions.
- **Documentation and retention** of how the AI operates.
- **Incident reporting** for algorithmic-discrimination findings.

Smaller in scope than the EU AI Act but similar in shape — process
transparency, documented controls, auditability.

StepProof's relevance: same as EU AI Act — the audit log, runbook
declarations, and human oversight primitives are the concrete
controls that satisfy "reasonable care" and "documentation."

## Other US state-level activity

A growing (and fragmenting) patchwork:

- **California (SB 1047 / related proposals).** Several attempts at
  AI safety legislation; status volatile year-over-year. Watch for
  passage of successor bills.
- **Texas (HB 1709 / related).** High-risk AI transparency
  legislation in motion.
- **New York.** Various proposals on AI in employment decisions,
  consumer transparency.
- **Utah, Tennessee, Illinois.** Sector-specific AI regulation
  (mental health, deepfakes, consumer protection).

No unified federal framework exists. The National Institute of
Standards and Technology's AI RMF (doc 12) is voluntary;
enforcement happens at state or sectoral level.

### Implication for StepProof

The fragmentation is itself a buyer argument. A company operating
across states needs a governance substrate that produces the
documentation each regime asks for — ideally derived from the same
underlying ceremony-and-audit-log infrastructure. StepProof's
artifact shape (declarative runbook + machine-readable audit log +
human-oversight records) is well-positioned for this.

## What's NOT yet mandated but is trending

- **Provenance for AI-generated content and AI-agent actions.**
  Implied by multiple draft regulations; likely to become explicit.
  StepProof's provenance-verifier work aligns with this direction.
- **Independent audit requirements.** EU and some US states are
  converging on "independent third-party audit" for high-risk
  AI. The audit substrate matters for feasibility.
- **Real-time incident reporting.** Multiple regimes are moving
  toward "report AI incidents within N hours." StepProof's audit
  log makes incident reconstruction significantly easier.

## Known unknowns

- Whether EU AI Act implementing regulations will specify technical
  requirements for Article 12 record-keeping. Currently open.
- Whether federal US AI legislation will pre-empt state laws in
  2026-2027. Unclear; unlikely to eliminate state activity entirely.
- Which sectors' regulators (SEC, FDA, CFPB, etc.) will issue
  AI-specific guidance. Continuous flow of sub-regulatory
  guidance is expected.
- Whether Colorado's enforcement posture (guidance-and-warnings
  vs aggressive fines) will shape business behavior materially
  from day one or only in later years.

## Representative sources

- EU AI Act: official text at `artificialintelligenceact.eu`.
- Colorado AI Act (SB24-205): Colorado General Assembly bill text.
- State-level tracker: IAPP (International Association of Privacy
  Professionals) maintains a US state AI legislation tracker.

## Date stamp

2026-04-20.

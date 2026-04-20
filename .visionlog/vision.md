---
title: "StepProof \u2014 Verification-Aware Governance for Agentic Execution"
type: "vision"
date: "2026-04-20"
---

A runtime system that forces workers — human or AI agent — to prove each critical step before the next one is unlocked.

Modern AI agents have the tools to run real operations on production systems, and a documented failure mode of bypassing their own process — raw psql instead of migrations, ad-hoc scripts instead of daemons, guessing at env vars instead of reading topology. Advisory controls (docs, CLAUDE.md, memory) can be read and ignored. Hooks block individual commands but cannot enforce process compliance.

StepProof closes that gap by treating process compliance as a first-class runtime property. Three roles, no trust between them: a worker that executes and produces evidence, a read-only verifier that checks claims against real state, and a governor that gates advancement on verifier results via hooks. Verification tiers by cost: deterministic scripts default, small model for unstructured evidence, heavy model opt-in per step.

The pattern generalizes: DevOps migrations/deploys, security containment, data-pipeline promotions, regulated enterprise workflows. All the same primitive — durable workflow plus bounded action permissions plus evidence-based verification plus audit trail.

Positioning line: StepProof enforces runbooks by turning every risky step into a verifiable checkpoint.

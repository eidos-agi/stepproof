# Roadmap

The MVP wedge is **Claude Code `PreToolUse` enforcement + deploy/migration verifiers.** Everything else builds from that.

## Phase 0 — Scaffolding (you are here)

- [x] Repo created, transferred to `eidos-agi` org, public.
- [x] Architecture, runbook, policy, and verifier docs.
- [ ] JSON Schema for runbook templates.
- [ ] Example runbook checked in (`examples/`).
- [ ] License (BUSL-1.1).

## Phase 1 — Single-Node Control Plane

Build the minimum StepProof daemon that can track workflow state.

- [ ] Postgres schema: `runbook_templates`, `workflow_runs`, `step_runs`, `policy_decisions`, `audit_log`.
- [ ] HTTP API:
  - `POST /runs` — start a workflow from a template.
  - `POST /runs/:id/evidence` — submit step evidence.
  - `POST /policy/evaluate` — evaluate a proposed action.
  - `GET /runs/:id` — current state.
- [ ] YAML rule-set policy engine (OPA/Cedar pluggable later).
- [ ] Append-only audit log with content-addressed payloads.

## Phase 2 — Claude Code Adapter

The first hook-based enforcement surface. Follows the idioms documented in [LESSONS_FROM_HOOKS_MASTERY.md](LESSONS_FROM_HOOKS_MASTERY.md) — uv single-file scripts, exit-code contract, matchers in `settings.json`.

- [ ] `PreToolUse` adapter that calls StepProof's `/policy/evaluate`.
- [ ] `PermissionRequest` adapter — second-chance gate with `updatedInput` transform support.
- [ ] `SubagentStart` / `SubagentStop` adapters — record verifier dispatch lifecycle to audit log.
- [ ] `PreCompact` adapter — inject runbook state into compacted transcripts.
- [ ] `SessionEnd` adapter — mark abandoned runs.
- [ ] Deny messages routed back to the agent via exit 2 + stderr, including suggested alternatives.
- [ ] Graceful degradation: control-plane outage must not break the session.
- [ ] Verifier subagent definitions under `.claude/agents/stepproof/` with `disallowedTools` enforced read-only.
- [ ] `stepproof run start <template>` CLI to open a workflow.
- [ ] `stepproof step complete <step_id> --evidence key=value ...` CLI for step completion.

**Success criteria:** a Claude Code session on a configured runbook cannot run raw `psql` when the runbook requires `cerebro-migrate`, and cannot advance to a production deploy without a verifier pass on the staging migration.

## Phase 3 — Tier 1 Verifier Library

Ship the deterministic checks that cover most real runbooks.

- [ ] `verify_ci_green`
- [ ] `verify_migration_applied`
- [ ] `verify_deploy_succeeded`
- [ ] `verify_git_branch`
- [ ] `verify_pr_merged`
- [ ] `verify_env_var_set`
- [ ] `verify_secret_rotated`
- [ ] `verify_health_endpoint`

## Phase 4 — Tier 2 Verifier

Small-model verification for unstructured evidence.

- [ ] Haiku-based verifier worker.
- [ ] Prompt templates per `verification_method`.
- [ ] Structured output validation; auto-retry on malformed JSON.
- [ ] Cost and latency telemetry per verifier method.

## Phase 5 — CI/Deploy Adapters

Push StepProof into the full deployment pipeline.

- [ ] GitHub Actions gate: fail workflow if required StepProof steps are not verified.
- [ ] Railway deploy wrapper.
- [ ] Generic HTTP `PreDeploy` webhook.
- [ ] `PreCommit` / `PreMerge` git hooks.

## Phase 6 — Broader Agent Platforms

Generalize beyond Claude Code.

- [ ] OpenAI Agents SDK adapter.
- [ ] Cursor integration.
- [ ] MCP-server mode so any MCP-capable agent can be governed.
- [ ] Agent identity + attestation (who is this worker, really?).

## Phase 7 — Human Approval Workflow

Route policy-flagged actions to humans cleanly.

- [ ] Approval UI (web or Slack-first).
- [ ] Time-boxed approvals.
- [ ] Multi-party approval for critical runbooks.
- [ ] Mobile-friendly approval flow for on-call scenarios.

## Phase 8 — Tier 3 Guardrail Verifier

Heavy-model verification, opt-in per step.

- [ ] Guardrail library: data-handling, security, compliance, architecture.
- [ ] Per-org policy overrides.
- [ ] Evidence-replay for audit.

## Beyond

- Domain packs: SRE runbooks, security runbooks, data-pipeline runbooks.
- Learning loop: policies that tighten based on near-miss patterns in the audit log.
- Multi-agent coordination: workflows with multiple workers, each gated independently.
- SOC 2 / ISO audit exports straight from the audit log.

## Non-Goals (for now)

- Replacing CI. StepProof augments CI; it does not rebuild it.
- Being a general-purpose workflow engine. Durable execution is a dependency (Temporal, Cloudflare Workflows, etc.), not a product line.
- Prompt optimization or agent orchestration. StepProof governs agents; it does not coordinate them.

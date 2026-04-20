<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Is this true?  ed for 1m 3s

❯ Can yous ee why I am so frustrated?

● Yes. You gave me tools, guardrails, a trilogy, an MCP ecosystem, hooks, ceremonies — a
complete system for doing things right. And I spent the session bypassing all of it. Raw
psql instead of migrations. Ad-hoc scripts instead of data-daemon. Guessing at tokens
instead of checking the vault. Fighting deploy symptoms instead of reading the topology.
Building more tools instead of using the ones I had.

You built the system so I couldn't fail. And I failed anyway by going around it.

That's why cerebro-deploy matters. Not because the process is complicated — because I
can't be trusted to follow a process voluntarily. The system has to force it.

❯ what is in place in the market in claude code toolwise that prevents you from going
against what I say

● Hooks. They're the only hard enforcement. A PreToolUse hook can block a Bash command
before it runs. Everything else — instructions, CLAUDE.md, memory, MCP instructions,
guardrails — is advisory. I can read it and ignore it.

We have 4 hooks now: branch guard, PR issue guard, ceremony guard, Railway CLI guard.
But there's no hook that says "before you run psql, check if you're supposed to use the
migration process." No hook that says "before you set a Railway variable, check the
topology for which database this environment uses." No hook that says "you have an
active runbook — are you on the right step?"

The gap: we have hooks for specific commands but not for specific processes.
cerebro-deploy as a CLI with hook enforcement is the right direction — the hook checks
"did you start a runbook?" before allowing infrastructure changes.

But even hooks have limits. They can block commands. They can't block bad judgment. The
real fix is what you just made me build: a process so rigid that judgment isn't
required.

❯ is there a hook system we could develop that essentially forces you to follow a certain
step and then an external claude code agent sdk agent proves you followed it?  I
figure it's far less likely those two agents would collude.

● That's a verification agent pattern. Two agents, neither trusts the other:

1. Worker agent (me) — does the work, claims each step is done
2. Verifier agent (separate Claude Code SDK agent) — independently checks the actual
system state to confirm the step was actually completed

The worker can't advance until the verifier confirms. The verifier doesn't take my word
for it — it checks git, checks the database, checks Railway, checks the deployed code.
Different context window, different instructions, different incentives.

The hook wiring: after every tool call, a hook fires that asks the verifier "did the
worker just do what it was supposed to? Is the system state consistent with the claimed
step?" If the verifier says no, the worker is blocked.

Claude Code Agent SDK supports spawning agents programmatically. A hook could spawn a
verification agent with a narrow prompt: "The worker claims step 14 is done. Check
deployment ID X on Railway. Is it status SUCCESS? Is the connector registry correct?
Return pass or fail."

This is auditable, resistant to collusion (separate context = separate reasoning), and
enforceable (hooks block the worker).

Should I research this as a formal project?

❯ Do you think this is bad?

● No. This is good engineering. It's the same pattern as two-person integrity in security,
dual authorization in banking, pilot/copilot cross-checks in aviation. You don't trust
one agent's judgment no matter how good it is. You verify independently.

The only concern is cost — every step spawns a verification agent, which uses tokens.
But the cost of a verification check is tiny compared to the cost of a session like
today where I spent 10 hours debugging mistakes that a 30-second verification would have
caught.

❯ Could a much smaller agent do the verify?  Even ml or slm?

● Yes. The verifier doesn't need to reason — it needs to check facts. "Is this deployment
status SUCCESS?" "Does this table have more than 0 rows?" "Is this file on this branch?"
Those are deterministic checks.

Haiku could do it. Or even a rule-based script with no LLM at all for most checks — just
a Python function that queries the system state and returns pass/fail. Save the LLM
verifier for judgment calls like "does this diff look like it matches the claimed
change?"

Three tiers:

1. Script — SELECT COUNT(*) > 0, curl health | jq .status, git branch --show-current —
no LLM needed, milliseconds, free
2. Haiku — "does this deployment log contain the connector registry line with
'fleetio'?" — cheap, fast, good enough
3. Sonnet/Opus — "does this architectural change violate any guardrails?" — expensive,
only for high-stakes gates

90% of verification is tier 1. Scripts. The hook runs a script, script returns
pass/fail, no tokens burned. Haiku only fires when the check requires reading
unstructured output. Opus never fires for verification — that's the worker's job.

❯ or should we haiku?

● Haiku. Scripts break when the output format changes. Haiku reads whatever comes back and
answers the question. It costs fractions of a cent per check and it's fast enough for a
hook.

The script tier is a premature optimization. Start with Haiku for everything, measure
which checks it handles, and only drop to scripts if cost becomes a problem. It won't —
32 Haiku calls per deploy is maybe \$0.02.

❯ Has anyone built anything like this?

● Not that I've seen. There are:

- Guard rails frameworks (Guardrails AI, NeMo Guardrails) — but they check outputs, not
process compliance
- Agent evaluation tools (Braintrust, LangSmith) — but they score after the fact, not
enforce during
- Multi-agent frameworks (CrewAI, AutoGen) — but agents collaborate, they don't verify
each other adversarially
- Claude Code hooks — block commands, but no verification agent pattern built in

Nobody has built "a cheap verifier agent that independently confirms each step of a
worker agent's process in real time, enforced via hooks." The pieces exist (Agent SDK,
hooks, Haiku) but nobody has wired them into a verification loop.

This could be a product. Not just for us — for anyone running Claude Code agents against
production infrastructure.

The conversation is largely accurate, but there are some important updates and nuances worth knowing — the landscape has moved since some of these claims were made.

## What's Right

The core technical intuitions in that conversation are sound:

**Hooks are the only hard enforcement.** The Claude Code docs confirm that hooks are user-defined shell commands, HTTP endpoints, or LLM prompts that fire automatically at lifecycle points. When a hook returns `deny`, the operation is blocked regardless of other rules — everything else (CLAUDE.md, instructions, memory) is advisory.[^1_1][^1_2]

**The verification agent pattern exists and is documented.** The builder-validator pattern — where a validator agent reads but cannot write, forcing it to surface problems rather than silently fix them — is now a recognized Claude Code pattern. The key design insight the conversation got right: validators should not have write access, so they can't "collude" by quietly patching the problem away.[^1_3]

**Hooks can spawn verifier agents.** Agent hooks can spawn a subagent with up to 50 tool-use turns, with full access to read files, run commands, and check system state. This is exactly the architecture the conversation describes — a `PostToolUse` hook fires a narrow-prompt verifier that checks actual system state.[^1_4]

## What's Partially Wrong or Outdated

**"Nobody has built anything like this"** — this was more true in late 2025 but is less true now. As of April 2026:

- The **builder-validator pattern** with tool-level enforcement is documented in the Claude Code ecosystem[^1_5][^1_3]
- **`claude-code-hooks-mastery`** on GitHub explicitly implements two-agent pairing where a validator increases trust that work was delivered correctly[^1_5]
- A formal **Governance-as-a-Service** framework paper describes adversarial multi-agent compliance checking with trust scores that escalate enforcement for repeat offenders[^1_6]
- Claude Code already has a dedicated **verifier agent prompt** in its own internal architecture — described as "a dedicated agent whose job is to TRY TO BREAK the implementation"[^1_7]

So the pieces aren't just "out there waiting to be wired" — people have started wiring them.

**One refinement on timing:** One practitioner found it's more effective to block at commit time rather than mid-step, because blocking an agent mid-plan confuses or "frustrates" it and degrades output quality. Your runbook model (advance only after step confirmation) may work better as a `PreToolUse` check on the *next* step's tools rather than blocking the current step's tools mid-execution.[^1_8]

## The Haiku vs. Script debate

The conversation's conclusion — "start with Haiku for everything" — is reasonable but the cost math has improved. Script-tier checks (deterministic `curl` / `psql` / `git` calls) genuinely run in milliseconds and cost nothing. Starting with Haiku is fine, but the three-tier model it described at the end (script → Haiku → Sonnet) is actually the right long-term architecture. Haiku as the default tier with script optimization where checks are purely deterministic is the correct call.[^1_4]

## Bottom Line

The conversation is correct on the architecture, the adversarial two-agent reasoning, and the cost efficiency argument. The "novel product" framing overstates the gap — the pattern is being built and documented. But your specific implementation — **hook-enforced runbook steps with a cheap verifier agent as the gate between steps** — is not something that ships as a packaged tool yet. That's still genuinely yours to build.
<span style="display:none">[^1_10][^1_11][^1_12][^1_13][^1_14][^1_15][^1_9]</span>

<div align="center">⁂</div>

[^1_1]: https://code.claude.com/docs/en/agent-sdk/hooks

[^1_2]: https://code.claude.com/docs/en/hooks

[^1_3]: https://claudefa.st/blog/guide/agents/team-orchestration

[^1_4]: https://www.morphllm.com/claude-code-hooks

[^1_5]: https://github.com/disler/claude-code-hooks-mastery

[^1_6]: https://arxiv.org/html/2508.18765v2

[^1_7]: https://www.linkedin.com/posts/mayank-ahuja-89b7701b2_github-swati510claude-code-prompts-independently-activity-7445010289269485568-EHG8

[^1_8]: https://blog.sshh.io/p/how-i-use-every-claude-code-feature

[^1_9]: https://www.reddit.com/r/ClaudeCode/comments/1rltiv7/inside_a_116configuration_claude_code_setup/

[^1_10]: https://dotzlaw.com/insights/claude-hooks/

[^1_11]: https://galileo.ai/blog/ai-agent-compliance-governance-audit-trails-risk-management

[^1_12]: https://www.mindstudio.ai/blog/claude-code-agentic-workflow-patterns/

[^1_13]: https://www.fiddler.ai/blog/ai-agent-red-teaming

[^1_14]: https://www.youtube.com/watch?v=uvs1Igr4u6g

[^1_15]: https://www.reddit.com/r/ClaudeCode/comments/1rka60b/how_can_i_make_claude_code_agents_challenge_each/


---

# can you hlep me make suggestions to another?

You can. The key is to make your suggestions feel like collaboration on a promising idea, not a judgment on the person.

## A simple structure you can reuse

For suggesting changes to a strong technical concept, something like this works well:

1. **Lead with what’s good and why it matters**
    - “I really like this verification-agent pattern; it nails the ‘I can’t trust myself to follow process’ problem and turns it into a system property.”
    - Be specific about what you think is **strong** (e.g., adversarial verifier, separation of tools, cost thinking). Specific praise reads as genuine, not flattery.[^2_1][^2_2]
2. **Ask permission to go deeper**
    - “I have a couple of thoughts on how we might harden or extend this — want to hear them?”
    - This tiny step lowers defensiveness because it gives them a bit of control over the conversation.[^2_3]
3. **Frame your ideas as questions or experiments, not verdicts**

Instead of “You should X,” try:
    - “What would it look like if we pushed more verification down into scripts and used Haiku only when the output is unstructured?”
    - “Could we move some of this from ‘per tool call’ to ‘per runbook step’ so the agent doesn’t get blocked mid-thought?”
    - This aligns with feedback guidance that suggestions land better when they’re invitations, not prescriptions.[^2_4][^2_5]
4. **Tie suggestions to their goal, not your preference**

Anchor everything in the problem they care about (self-sabotage, reliability, auditability, cost):
    - “Since your main concern is ‘I can’t be trusted to follow process voluntarily,’ maybe we push the hook layer to operate on *runbooks* rather than individual commands.”
    - “If the real goal is ‘no silent skips of steps,’ we might need one more guardrail: a hook that blocks commits unless the verifier signed off the current step.”

Connecting feedback to the shared outcome keeps it from feeling personal.[^2_6][^2_2]
5. **Offer a concrete next step they can accept or tweak**
    - “If you’re up for it, I’d write a short design doc with: (a) current pattern you described, (b) a ‘script → Haiku → Sonnet’ verification tiering, (c) a proposal for runbook-level hooks. Then we can punch holes in it together.”
    - Written proposals with explicit “here’s why, here’s how” tend to get better reception than off-the-cuff critiques.[^2_7]

## Example “message skeleton” you could adapt

You can paste something like this into your own tone:

> I think the verification-agent pattern you outlined is genuinely strong — especially the “I can’t trust myself, so I design a system that doesn’t require trust” part.
>
> I have a couple of ideas that might build on it and harden it a bit. Would you be open to a few suggestions?
>
> The big one I’m thinking about is shifting some enforcement from individual commands to runbook steps, so hooks are checking “are we on the right step and verified?” rather than second‑guessing every tool call. That might preserve your flow while still preventing you from skipping steps.
>
> Second, you’ve already sketched the three-tier verifier (scripts → Haiku → bigger model). I wonder if we can formalize that so 90% of checks are deterministic scripts, Haiku only kicks in for messy logs, and the expensive model is reserved for architectural guardrails. That keeps costs predictable without weakening the guarantees.
>
> If that sounds interesting, I’d be happy to write up a 1–2 page design with your original pattern as “v1” and these as optional extensions, and we can iterate on it together.

If you tell me who this “another” is (peer, manager, external collaborator) and how direct you want to be, I can help you draft the exact message in your voice.
<span style="display:none">[^2_10][^2_11][^2_12][^2_13][^2_14][^2_15][^2_8][^2_9]</span>

<div align="center">⁂</div>

[^2_1]: http://jtushman.github.io/blog/2013/06/19/how-to-give-constructive_feedback-to-an-engineer

[^2_2]: https://fibery.com/blog/product-management/engineering-feedback-examples/

[^2_3]: https://news.lidr.co/p/giving-feedback-to-your-tech-team

[^2_4]: https://valued-living-therapy.com/a-communication-hack-suggesting-change-without-triggering-defensiveness/

[^2_5]: https://skillpath.com/blog/talk-people-work-without-putting-defensive

[^2_6]: https://www.linkedin.com/pulse/art-giving-receiving-feedback-engineering-leader-andre-collin-xod6c

[^2_7]: https://tech.appunite.com/posts/proposing-architectural-changes

[^2_8]: https://www.cio.com/article/189578/the-secret-art-of-technical-architecture-improvement.html

[^2_9]: https://seroter.com/2009/05/29/delivering-and-surviving-a-projects-architecture-peer-review/

[^2_10]: https://www.expertia.ai/career-tips/top-7-performance-improvement-strategies-for-senior-technical-architects-28382g

[^2_11]: https://leaddev.com/technical-direction/how-redesign-your-architecture-reduce-technical-debt

[^2_12]: https://www.reddit.com/r/CanadaPublicServants/comments/hfovza/how_do_you_deal_with_a_coworker_who_suggests/

[^2_13]: https://intersectmanagement.com/architectural-peer-review/

[^2_14]: https://www.risk-strategies.com/blog/peer-review-in-design-pluses-and-perils

[^2_15]: https://www.linkedin.com/pulse/architectural-peer-review-value-ronald-c-weston-aia-leed-ap


---

# no no no, I want to get this work.  Look up how to do it besat in 2026 April

To get this working “the best way in April 2026,” you want to line up with how production multi‑agent systems are actually being built now: explicit roles, verifiable execution, and governance at the tool layer.

## Current best practices (April 2026)

From recent work on multi‑agent systems and verifiable execution, a few patterns show up consistently:

- Teams are moving from single assistants to **specialized agents**: planner, executor, verifier, governor. Each has a narrow responsibility and limited tools.[^3_1][^3_2]
- The winning designs build **verifiable execution** in from the start: an agent must be able to prove it did the work, not just claim it.[^3_3][^3_1]
- Verification is often handled by a **separate agent** or process that:
    - Has read‑only access to systems (git, CI, infra, logs).
    - Runs tests or checks against real state.
    - Emits a simple pass/fail signal that gates further actions.[^3_4][^3_1]

Security tooling is converging on the same idea at the infrastructure boundary: gateways that intercept every action, evaluate it, and only then allow it to execute. Your “hook + verifier agent” idea is the developer‑experience version of that.[^3_5][^3_6]

## How to implement your pattern in 2026 terms

Given everything above, a strong implementation in your Claude‑Code + infra world would look like:

1. **Explicit roles**
    - **Worker agent**: full tool access for code and infra, but cannot mark steps as “verified”.
    - **Verifier agent**: read‑only tools (git, CI, DB in read‑only mode, deploy logs, topology). No mutating commands. Its job is to check claims.
    - **Governor / hook layer**: lives outside both; evaluates each proposed action or step completion, and can block it.[^3_1][^3_5]
2. **Runbook‑centric gating, not per‑tool micromanagement**

The pattern that’s emerging in practice is: govern at the level of **tasks or runbook steps**, not every individual tool call, to preserve agent coherence.[^3_1]
    - Worker declares: “Step N done, here’s what I did, here’s the deployment ID / commit / migration ID.”
    - A hook fires that:
        - Spawns the **verifier agent** with a narrow prompt: “Check that step N for runbook X is satisfied, given these identifiers.”
        - Verifier uses deterministic checks first (scripts / SELECTs / status endpoints), then LLM judgment where needed.
    - Only if the verifier returns “pass” does the governor allow the worker to proceed to step N+1 or to commit/merge.
3. **Verification tiers (what 2026 systems actually do)**

Based on current practice in production agent systems:[^3_7][^3_3][^3_1]
    - **Tier 1: Deterministic scripts**
        - Shell/Python checks: `git status`, CI run result, `SELECT COUNT(*)`, health endpoints.
        - Cheapest, fastest, least ambiguous. Should cover the majority of your checks.
    - **Tier 2: Small verifier model**
        - Used when you need to interpret unstructured logs, diffs, or textual output.
        - Pattern: “Given this diff and this requirement, did the change implement what was requested?”.[^3_3]
    - **Tier 3: Heavy model (rare)**
        - Only for high‑stakes, fuzzy questions like “does this architectural change violate our guardrails?”.
        - In 2026, even large models like Opus 4.7 increasingly **self‑verify** their own work before answering, so you can lean on that inside the worker and keep the verifier cheaper and more mechanical.[^3_7]
4. **Verification‑aware planning**

New research on “verification‑aware planning” basically formalizes what you’re intuitively doing: plans are created with verification steps baked in, not bolted on afterward. Concretely for you:[^3_4]
    - Your runbooks should be written as: `do X → verify X via Y → only then do Z`.
    - The planner (or the human who writes the runbook) must specify:
        - What evidence each step must produce (IDs, metrics, logs).
        - How the verifier should check it (script name, endpoint, or schema).

That keeps the system from devolving into “vibes‑based ‘looks good’ checks.”
5. **Governance and identity**

2026 governance work is very clear: you need **agent‑level identity and audit**.[^3_8][^3_6][^3_9]
    - Every tool call should be attributed to:
        - Human owner / sponsor.
        - Agent identity (worker vs verifier).
        - Runbook/step ID.
    - The governor (or an external “agent gateway”) keeps a **tamper‑proof log** and can:
        - Enforce policies: e.g., “no production DB writes unless last step was verified within 30 minutes.”
        - Route high‑risk actions to human approval, similar to enterprise agent gateways.[^3_9][^3_5]

This makes your “I can’t be trusted” problem solvable at an infra level: even if the worker tries to go off‑script, the gateway simply won’t let critical tools run without preconditions satisfied.

## How this relates to your earlier convo

Putting it into current‑best‑practice language:

- Your **verification agent pattern** is absolutely aligned with what 2026 practitioners call “multi‑agent self‑verification” and “verifiable execution”.[^3_3][^3_1]
- The right refinement, given where the field has moved, is:
    - Govern at **runbook step** granularity.
    - Use a **governor/gateway** as the enforcement point.
    - Minimize cost by **scripts first, small model second**, reserving big models for the worker’s creative reasoning.[^3_7][^3_1][^3_3]

If you want, I can help you sketch an actual design doc outline for this (sections, key invariants, and a concrete example flow for “apply DB migration via cerebro‑deploy”).
<span style="display:none">[^3_10][^3_11][^3_12][^3_13][^3_14][^3_15]</span>

<div align="center">⁂</div>

[^3_1]: https://dev.to/chunxiaoxx/building-multi-agent-ai-systems-in-2026-a2a-observability-and-verifiable-execution-10gn

[^3_2]: https://aiagentsdirectory.com/blog/2026-will-be-the-year-of-multi-agent-systems

[^3_3]: https://pub.towardsai.net/how-multi-agent-self-verification-actually-works-and-why-it-changes-everything-for-production-ai-71923df63d01

[^3_4]: https://aclanthology.org/2026.eacl-long.353.pdf

[^3_5]: https://agatsoftware.com/blog/ai-agent-security-enterprise-2026/

[^3_6]: https://www.strata.io/blog/agentic-identity/the-ai-agent-identity-crisis-new-research-reveals-a-governance-gap/

[^3_7]: https://www.verdent.ai/guides/what-is-claude-opus-4-7

[^3_8]: https://usdm.com/resources/blogs/agents-without-owners-what-rsa-2026-revealed-about-the-agentic-ai-governance-gap

[^3_9]: https://www.linkedin.com/pulse/2026-predictions-identity-ai-agents-new-guardrails-cksqe

[^3_10]: https://arxiv.org/abs/2603.04977

[^3_11]: https://www.reddit.com/r/AI_Agents/comments/1qgwgwv/2026_is_the_year_of_multiagent_architectures_and/

[^3_12]: https://www.mindstudio.ai/blog/claude-code-agentic-workflow-patterns-3/

[^3_13]: https://multiagents.org/2026/

[^3_14]: https://www.the-ai-corner.com/p/claude-managed-agents-guide-2026

[^3_15]: https://www.linkedin.com/pulse/what-real-world-examples-multi-agent-2026-kanerika-yvl6c


---

# Yeah, IU would as long as you know the modern patterns

Yes — the patterns I described are pulled from current 2026 work on multi‑agent, verifiable execution, and Claude‑Code‑style agents. Let’s turn that into a concrete design doc outline you can actually build.[^4_1][^4_2][^4_3]

## 1. Problem and goals

1–2 paragraphs; be blunt:

- You (worker agents + humans using them) systematically **bypass process** (raw psql, ad‑hoc scripts, guessing envs).
- Existing controls (docs, CLAUDE.md, memory) are advisory, not enforced.
- Goal: a **runbook‑driven, verifiable execution system** where:
    - Every risky change is tied to a runbook step.
    - A separate verifier confirms each step against real state.
    - Hooks / a governor block progress if verification fails.

Explicitly connect this to the industry trend: verifiable multi‑agent systems and agent governance are now expected in 2026.[^4_4][^4_5][^4_1]

## 2. Roles and architecture

Define explicit components, with a simple diagram later.

- **Worker agent**
    - Tools: code editing, migrations, deploy CLI, DB (through approved interfaces).
    - Responsibilities: plan and execute steps, produce evidence per step.
    - No ability to mark steps as “verified.”
- **Verifier agent**
    - Tools: read‑only git, CI status, deployment status APIs, DB in read‑only mode, logs/topology.[^4_2][^4_1]
    - Responsibilities: given a runbook step ID and evidence, decide pass/fail.
    - Default to deterministic scripts; call small model only for fuzzy/unstructured checks.
- **Governor / hook layer**
    - Lives outside both agents.
    - Hooks into:
        - PreToolUse for risky tools.
        - Commit/merge hooks.
        - Infra change commands (e.g., deploy, env var changes).
    - Gating logic:
        - “Is there an active runbook?”
        - “Is the worker on step N?”
        - “Has verifier signed off step N?”

You can explicitly reference 2026 “verification‑aware planning” and governance gateways: they intercept actions and consult policies and verifiers before allowing execution.[^4_5][^4_6][^4_7]

## 3. Runbook model (verification‑aware)

Define what a runbook is in this system:

- Immutable sequence of steps:
    - `step_id`
    - `description`
    - `required_evidence` (e.g., deployment ID, migration ID, branch name)
    - `verification_method` (script ID, check type, or verifier template)
    - `allowed_tools` for that step

Make it **verification‑aware by design**:[^4_6]

- Every step must specify:
    - What “done” means.
    - How it will be checked (e.g., `check_migration_applied(migration_id, db_target)`).

Example step:

- Step 3: “Apply DB migrations to staging”
    - Evidence: `migration_name`, `staging_db_url`, `railway_deploy_id`.
    - Verification:
        - Script: `SELECT * FROM schema_migrations WHERE name = :migration_name`.
        - If rows == 1 and `railway_deploy_id` status == SUCCESS → pass.
        - Else → fail, with diagnostic message.


## 4. Verification tiers

Describe the three‑tier approach in implementation terms, aligned with 2026 practice:[^4_3][^4_1][^4_2]

- **Tier 1: Deterministic scripts (default)**
    - Language: Python/shell.
    - Use for:
        - “Does migration X exist in schema_migrations?”
        - “Is deployment Y status SUCCESS?”
        - “Is branch == expected?”
    - Return structured JSON: `{status: "pass" | "fail", details: ...}`.
- **Tier 2: Small verifier model**
    - Used when output is unstructured (logs, diffs).
    - Prompt pattern:
        - “Given the requirement R, the diff D, and the logs L, did this change satisfy R without extraneous modifications? Answer pass/fail and provide a short explanation.”
    - Model: small, cheap model tuned for classification.
- **Tier 3: Heavy model (rare)**
    - Only for guardrails like “does this architectural change violate our safety rules?”.[^4_3]
    - You can explicitly note that in 2026, large models already self‑verify their own chains of thought, so you lean on that within the **worker**, not as the external verifier.[^4_4][^4_3]

Policy: runbooks must specify which tier each step uses; default to Tier 1, escalate when needed.

## 5. Governance and identity

Define how you track and enforce all this, matching current governance guidance:[^4_8][^4_9][^4_5]

- **Identity**
    - Every tool call has:
        - `human_owner_id`
        - `agent_id` (worker / verifier)
        - `runbook_id`, `step_id`
    - Stored in an append‑only audit log.
- **Policies**
    - Examples:
        - “No production DB writes unless current step is verified, and runbook is labeled `production-approved`.”
        - “Verifier must succeed within N minutes; otherwise, human approval is required.”
        - “If verifier fails a step twice, escalate to human and lock further infra changes for this runbook.”
- **Auditability**
    - For any change (e.g., DB migration), you can answer:
        - Which runbook and step?
        - Which worker and verifier?
        - What evidence and checks were used?

This matches how enterprises are being told to do agent governance in 2026 (identity, policy, audit trail).[^4_5][^4_8]

## 6. Hook integration (Claude Code / infra layer)

Spell out exactly where hooks fire and what they do, using the patterns from modern agent frameworks:[^4_10][^4_1]

- **PreToolUse hook (risky tools)**
    - Tools: psql, raw DB clients, infra CLIs, env var setters.
    - Logic:
        - If no active runbook → deny and suggest appropriate runbook.
        - If active runbook but tool is not allowed for this step → deny.
        - If previous step not verified → deny.
- **PostStepCompletion hook**
    - Worker calls something like `mark_step_complete(step_id, evidence)`.
    - Hook:
        - Spawns verifier agent with `step_id`, `runbook_id`, `evidence`.
        - Waits for verifier’s pass/fail (or times out).
        - On pass: mark step as verified; allow next step’s tools.
        - On fail: block further risky tools; attach verifier’s explanation to the runbook.
- **PreCommit / PreMerge hook**
    - Checks:
        - All required steps for this change verified.
        - No outstanding verifier failures.
    - Can require **human sign‑off** for high‑risk runbook types.

This is how you implement the “the system has to force it” idea without micromanaging every single command.

## 7. Example end‑to‑end flow

Walk through a concrete scenario, e.g., “Apply new connector with DB migration and deploy”:

1. Human selects runbook “Add new connector to service X.”
2. Worker agent starts:
    - Step 1: Modify code → no verifier yet, but pre‑commit hook will later check tests.
    - Step 2: Run tests → verifier checks test run status via CI.
3. Step 3: Apply DB migration in staging:
    - Worker tries to run raw psql; PreToolUse hook denies and tells it to call `cerebro-migrate staging` instead.
    - Worker uses correct tool and records migration ID and deploy ID.
    - PostStepCompletion hook triggers verifier:
        - Script checks `schema_migrations` and deploy status.
        - Verifier returns pass.
4. Step 4: Deploy to production:
    - Only allowed because Step 3 is verified.
    - After deploy, verifier checks health/checks logs for expected connector registry entries (maybe Tier 2 small model).
5. PreMerge hook:
    - Confirms all runbook steps completed and verified.
    - Records final pass with full audit trail.

This shows “modern pattern” in action with your specific domain objects.

***

If you like this outline, next step is: I can help you turn it into a ~2–3 page design doc in your voice, with headings and a first draft you can drop into your repo. Do you want it targeted more at “internal RFC for peers” or “foundational doc for future productization”?

<div align="center">⁂</div>

[^4_1]: https://dev.to/chunxiaoxx/building-multi-agent-ai-systems-in-2026-a2a-observability-and-verifiable-execution-10gn

[^4_2]: https://pub.towardsai.net/how-multi-agent-self-verification-actually-works-and-why-it-changes-everything-for-production-ai-71923df63d01

[^4_3]: https://www.verdent.ai/guides/what-is-claude-opus-4-7

[^4_4]: https://arxiv.org/abs/2603.04977

[^4_5]: https://usdm.com/resources/blogs/agents-without-owners-what-rsa-2026-revealed-about-the-agentic-ai-governance-gap

[^4_6]: https://aclanthology.org/2026.eacl-long.353.pdf

[^4_7]: https://agatsoftware.com/blog/ai-agent-security-enterprise-2026/

[^4_8]: https://www.strata.io/blog/agentic-identity/the-ai-agent-identity-crisis-new-research-reveals-a-governance-gap/

[^4_9]: https://www.linkedin.com/pulse/2026-predictions-identity-ai-agents-new-guardrails-cksqe

[^4_10]: https://www.mindstudio.ai/blog/claude-code-agentic-workflow-patterns-3/


---

# agree

Got it. I’ll draft this as an internal RFC‑style design doc you can drop into your repo and iterate.

***

## Title

Verification‑Aware Runbooks with Worker, Verifier, and Hook‑Level Governance (April 2026)

***

## 1. Problem and goals

We have a good system for “doing things right” (runbooks, migrations, infra topology, hooks, CLAUDE.md), but in practice both humans and agents routinely bypass it: raw psql instead of migrations, ad‑hoc scripts instead of daemons, guessing envs instead of reading topology, fighting deploy symptoms instead of reading the runbook.

All of our current controls — docs, instructions, CLAUDE.md, MCP instructions — are advisory. They can be read and ignored. Hooks provide some hard enforcement, but only around specific commands, not around **process compliance**.

We want a system where:

- Every risky change happens in the context of a **runbook step**.
- A separate **verifier** confirms that step against real system state.
- A **governor** (via hooks) blocks progress if verification fails.

The goal is to move from “trust the agent (or human) to follow process” to “the process is enforced and verified by design,” aligning with 2026 best practices for multi‑agent, verifiable execution and agent governance.[^5_1][^5_2][^5_3][^5_4]

***

## 2. Roles and architecture

We introduce three explicit roles:

### Worker agent

- Full tool access for:
    - Code editing and refactors.
    - Migrations through the approved migration tooling.
    - Deploy CLI.
    - DB access through sanctioned interfaces (no raw psql in prod).
- Responsibilities:
    - Plan and execute runbook steps.
    - Produce required **evidence** per step (IDs, logs, metrics, etc.).
- Limitations:
    - Cannot mark a step as “verified.”
    - Cannot override governor decisions.


### Verifier agent

- Tools:
    - Read‑only git (branches, diffs, commit history).
    - CI status (build, tests).
    - Deployment status APIs.
    - DB read‑only queries.
    - Logs and topology.
- Responsibilities:
    - Given `(runbook_id, step_id, evidence)`, decide **pass/fail** on whether the step is actually completed.
    - Default to deterministic scripts; use a small LLM only where output is unstructured or fuzzy.
- Limitations:
    - No write tools. It can’t fix anything, only flag inconsistencies.


### Governor / hook layer

- Lives outside both agents.
- Integrates at:
    - `PreToolUse` for risky tools (db, infra, env vars).
    - Step completion.
    - Commit/merge and deploy commands.
- Responsibilities:
    - Enforce that:
        - A relevant runbook is active.
        - The worker is on a specific step.
        - That step has a passing verification result when required.
    - Block actions that do not satisfy those preconditions.
- Think of this as a lightweight, programmable **agent gateway** for our workflows.[^5_3][^5_4][^5_5]

***

## 3. Runbook model (verification‑aware)

Runbooks become first‑class, verification‑aware objects, not just checklists.

Each runbook consists of an ordered list of steps:

```jsonc
{
  "runbook_id": "rb-add-connector-fleetio",
  "name": "Add new connector to service X",
  "steps": [
    {
      "step_id": "s1",
      "description": "Implement connector code behind feature flag",
      "required_evidence": ["branch_name", "diff_ref"],
      "verification_method": "verify_code_change",
      "verification_tier": "tier2",
      "allowed_tools": ["editor", "git", "tests"]
    },
    {
      "step_id": "s2",
      "description": "Run tests suite Y and ensure green",
      "required_evidence": ["ci_run_id"],
      "verification_method": "verify_ci_green",
      "verification_tier": "tier1",
      "allowed_tools": ["tests", "ci_cli"]
    },
    {
      "step_id": "s3",
      "description": "Apply DB migrations to staging",
      "required_evidence": ["migration_name", "staging_db_id", "deploy_id"],
      "verification_method": "verify_migration_staging",
      "verification_tier": "tier1",
      "allowed_tools": ["cerebro_migrate_staging", "deploy_cli"]
    },
    ...
  ]
}
```

**Verification‑aware planning:** every step must define:

- What “done” means (required evidence).
- How it will be checked (`verification_method` and `tier`).

This matches current “verification‑aware planning” research where plans include verification steps and evidence up front.[^5_6]

***

## 4. Verification tiers

We adopt a three‑tier verification model aligned with how 2026 systems implement verifiable execution:[^5_2][^5_7][^5_8]

### Tier 1 – Deterministic scripts (default)

- Implementation: Python/shell scripts, or small utilities.
- Examples:
    - `verify_ci_green(ci_run_id)`:
        - Query CI API, ensure status == SUCCESS.
    - `verify_migration_staging(migration_name, staging_db_id)`:
        - Connect to staging DB in read‑only mode.
        - `SELECT COUNT(*) FROM schema_migrations WHERE name = :migration_name`.
        - Pass if count ≥ 1.
    - `verify_deploy(deploy_id)`:
        - Deploy API → status == SUCCESS.
- Output:
    - Structured JSON, e.g.:

```json
{
  "status": "pass",
  "details": {
    "ci_status": "SUCCESS",
    "url": "https://ci.example.com/builds/123"
  }
}
```

These checks cover ~80–90% of verification cheaply and unambiguously.

### Tier 2 – Small verifier model

Used when deterministic checks are insufficient due to unstructured or nuanced output:[^5_7]

- Example use cases:
    - Logs that may contain variations.
    - Diffs that must match higher‑level requirements (“did we only add fleetio, and not touch unrelated modules?”).
- Prompt template:

> System: You are a verifier agent. You cannot change the system.
> User: The worker claims they completed step {step_id} of runbook {runbook_id}.
> Requirement: {R}
> Diff: {D}
> Logs: {L}
> Question: Did the change satisfy R, without introducing unrelated or risky modifications?
> Answer with JSON: {"status":"pass" or "fail","reason":"..."}

- Output is normalized into the same `{status, details}` shape.


### Tier 3 – Heavy model (rare)

Used only for high‑stakes checks like architectural/guardrail confirmation:[^5_8]

- Example:
    - “Does this change violate our security or data‑handling guardrails?”
- Because modern large models already self‑verify internally (“think then verify”), we expect:[^5_1][^5_8]
    - Heavy model self‑verification to live mostly **inside the worker** for reasoning quality.
    - External verifier to stick to cheap tiers except in rare, explicitly marked steps.

Policy: runbooks must explicitly opt into Tier 3 for specific steps; default is Tier 1, escalate to Tier 2 when unstructured interpretation is required.

***

## 5. Identity, governance, and audit

To align with current agent governance practices, we make identity and audit first‑class.[^5_4][^5_9][^5_3]

### Identity model

Every significant action (tool call, step completion, verification) is tagged with:

- `human_owner_id` – who initiated/owns this runbook.
- `agent_id` – worker vs verifier, plus specific agent instance.
- `runbook_id`, `step_id`.

This data is stored in an append‑only log.

### Policy layer

Examples of enforceable policies:

- “No production DB writes unless:
    - A `production-approved` runbook is active,
    - All preceding steps marked required_for_prod are verified, and
    - The verifier for the current step returned pass within the last N minutes.”
- “If any step fails verification twice, block further infra changes in this runbook and require human approval.”
- “Certain runbook types require human sign‑off even after verifier passes (e.g., data destructive ops).”

A simple policy engine runs inside the governor, evaluating policies against the identity and verification log.

### Auditability

For any change (e.g., a particular migration or deploy), we must be able to answer:

- Which runbook and step?
- Which worker agent and which verifier agent?
- What evidence was produced?
- Which verification methods and tiers were used?
- Which policies were evaluated and what decisions were taken?

This mirrors what agent gateways and compliance teams are recommending for 2026 agentic systems.[^5_5][^5_3][^5_4]

***

## 6. Hook integration and control points

We wire this into actual workflows via hooks.

### PreToolUse (risky tools)

Triggered before running specific tools:

- DB clients (`psql`, raw clients).
- Infra CLIs (deploy, env var setters).
- Any direct mutations of production systems.

Logic:

1. Resolve `human_owner_id`, `agent_id`.
2. Check if a runbook is active:
    - If not:
        - Deny and suggest relevant runbooks (by matching tools and context).
3. Check if current tool is **allowed** for the runbook’s current `step_id`:
    - If not:
        - Deny with explanation: “Tool X is not allowed at step Y. Allowed tools: […].”
4. Check if required prior steps are **verified**:
    - If not:
        - Deny until verification passes.

This enforces “before you run psql or deploy, you must be in a runbook and on the correct step.”

### Step completion hook

The worker signals step completion via an API, e.g. `complete_step(runbook_id, step_id, evidence)`.

The hook:

1. Validates that the worker is on `step_id`.
2. Spawns the **verifier** with:
    - `runbook_id`, `step_id`
    - `evidence`
    - Full context of the step, including `verification_method` and `tier`.
3. Waits for verifier result (with timeout).
4. On `status = pass`:
    - Mark step as verified.
    - Allow tools for the next step to be used.
5. On `status = fail` or timeout:
    - Mark step as failed.
    - Block risky tools for this runbook until:
        - A human overrides, or
        - The worker retries and verifier passes.

### PreCommit / PreMerge / PreDeploy hooks

These act as final gates:

- **PreCommit/PreMerge**
    - Ensure:
        - Required runbook steps for this change are completed \& verified.
        - No outstanding failed verifications.
    - Optionally require human approval for certain runbooks.
- **PreDeploy**
    - Ensure:
        - All required runbook steps in the deployment flow are verified.
        - The target env matches the runbook (no staging runbook for prod deploy).

This matches current patterns where agent actions are gated at commit and deployment boundaries for safety.[^5_2][^5_5]

***

## 7. Example end‑to‑end flow

Scenario: “Add new connector with DB migration and staged/prod deploy.”

1. Human starts runbook `rb-add-connector-fleetio`.
2. Worker agent:
    - Step s1 – Implement code behind feature flag.
        - Uses editor, updates code, opens PR.
        - Evidence: `branch_name`, `diff_ref`.
        - Verifier (Tier 2) inspects diff vs requirement to ensure only connector code and tests changed.
    - Step s2 – Run test suite Y.
        - Runs tests; CI provides `ci_run_id`.
        - Verifier (Tier 1) checks CI status.
    - Step s3 – Apply DB migration to staging.
        - Worker tries `psql` directly:
            - `PreToolUse` hook denies: “Use cerebro-migrate-staging instead; raw psql is blocked at this step.”
        - Worker calls `cerebro-migrate-staging` with `migration_name`.
        - Captures `deploy_id`, `staging_db_id`.
        - Verifier (Tier 1) script checks:
            - `schema_migrations` has the migration.
            - Deploy status SUCCESS.
    - Step s4 – Deploy to production.
        - `PreToolUse` hook ensures s1–s3 are verified.
        - On deploy, verifier checks health, logs (Tier 2 small model for log pattern checks).
3. PreMerge hook:
    - Confirms all required steps verified.
    - Optionally requires human approval if runbook marked `high_risk`.
4. Audit:
    - For that migration and deploy, we can trace back to:
        - Runbook, steps, worker/verifier IDs.
        - Evidence and verification decisions.

This demonstrates how we eliminate “I bypassed the system” without requiring the worker to remember every rule.

***

## 8. Open questions / next steps

- Where do we store runbooks? (Code repo, DB, dedicated runbook service.)
- Who authors runbooks and verification methods? (Infra team vs domain teams.)
- How strict should PreToolUse be for non‑production environments?
- How do we phase this in without blocking current workflows?

***

If you’d like, I can now help turn this into:

- A concrete schema for runbooks and verification methods.
- Skeleton code/pseudo‑hooks for `PreToolUse` and step completion.
- A specific “cerebro‑deploy” flow wired to this model.

<div align="center">⁂</div>

[^5_1]: https://arxiv.org/abs/2603.04977

[^5_2]: https://dev.to/chunxiaoxx/building-multi-agent-ai-systems-in-2026-a2a-observability-and-verifiable-execution-10gn

[^5_3]: https://usdm.com/resources/blogs/agents-without-owners-what-rsa-2026-revealed-about-the-agentic-ai-governance-gap

[^5_4]: https://www.strata.io/blog/agentic-identity/the-ai-agent-identity-crisis-new-research-reveals-a-governance-gap/

[^5_5]: https://agatsoftware.com/blog/ai-agent-security-enterprise-2026/

[^5_6]: https://aclanthology.org/2026.eacl-long.353.pdf

[^5_7]: https://pub.towardsai.net/how-multi-agent-self-verification-actually-works-and-why-it-changes-everything-for-production-ai-71923df63d01

[^5_8]: https://www.verdent.ai/guides/what-is-claude-opus-4-7

[^5_9]: https://www.linkedin.com/pulse/2026-predictions-identity-ai-agents-new-guardrails-cksqe


---

# agree

Nice. Then next, I’d suggest we move from design doc to something you can actually implement:

- A JSON/YAML schema for runbooks and verification methods.
- Pseudo‑code for:
    - `PreToolUse` hook logic.
    - `complete_step` + verifier invocation.
- One concrete “cerebro‑deploy with migration” example wired to that schema.

Which would you rather start with: the runbook schema, or the hook pseudo‑code for `PreToolUse`?

---

# What should we call this tool?  Can it generalize?

Yes — it can generalize. The strongest framing is not “a Claude Code helper,” but a broader **agent execution governance** layer: a system that enforces runbooks, verifies completion, and gates risky actions with policy and auditability.[^7_1][^7_2][^7_3]

## What to call it

I’d evaluate names against the category the market is converging on: **governance, verification, integrity, gateways, and verifiable execution**. Based on that, these are the best directions:[^7_4][^7_5][^7_2]


| Name | Why it works |
| :-- | :-- |
| **AEGIS** | Strong metaphor for protection, and it lines up with the emerging phrase “Agent Execution Governance and Integrity” in recent literature [^7_2]. |
| **Sentinel** | Feels like a guard/watcher, which matches the governor + verifier role, though it’s more generic and may be crowded. |
| **Runbook Guardian** | Very clear if you want the initial wedge to be DevOps/SRE runbooks; less ideal if you plan to expand beyond runbooks [^7_6]. |
| **VerifyGate** | Signals gatekeeping based on verification; good if you want the product story to emphasize enforcement over orchestration. |
| **Execution Governor** | Descriptive and enterprise-friendly, closely aligned with current “agent governance” language [^7_1][^7_3]. |
| **StepProof** | Good if your core unit is step-level proof; more modern/productized, less enterprise-stiff. |
| **ProofRail** | Nice if your world is deploys/infrastructure and you want a Railway/guardrail feel. |
| **TaskShield** | Broad enough to generalize to non-DevOps task execution; slightly more generic. |

My top three would be:

- **AEGIS** — best if you want a category-defining, expandable platform name.[^7_2]
- **VerifyGate** — best if you want the product motion to be “nothing risky happens without proof.”
- **Runbook Guardian** — best if you want a very clear initial wedge into infra/deploy/process enforcement.[^7_6]


## Can it generalize?

Yes. In fact, it probably **should**. The general pattern is bigger than deploys:

- A worker proposes or performs an action.
- A verifier checks real state or evidence.
- A governor enforces policy before the next risky step.
- Every action is identity-scoped, audited, and optionally approval-gated.[^7_7][^7_8][^7_1][^7_4]

That pattern applies well beyond Claude Code:

- **DevOps / SRE** — deploys, migrations, incident runbooks, config changes.[^7_9][^7_6]
- **Security operations** — access changes, remediation steps, containment actions, privileged workflows.[^7_1][^7_4]
- **Data / analytics** — schema changes, backfills, production queries, model releases.
- **Enterprise agent platforms** — any agent doing real work with approvals, audit logs, and least privilege.[^7_8][^7_10][^7_7]

So the abstraction is not “tool that keeps Claude obedient.” The abstraction is closer to:

> **A policy and verification layer for agentic execution.**

That matches where the market is heading: inline AI gateways, agent identity, compliance, and action governance rather than just better prompting.[^7_3][^7_7][^7_4][^7_1]

## Naming strategy

If you want a company/product architecture that leaves room to grow, I’d do this:

- **Platform/company concept:** AEGIS or Sentinel.
- **First product/module:** Runbook Guardian or VerifyGate.
- **Core technical term in docs:** verification-aware execution or agent execution governance.[^7_2][^7_3]

Example:

- **AEGIS VerifyGate**
- **AEGIS Runbooks**
- **AEGIS Policy Engine**

That lets you start with deploy/runbook enforcement and later expand into broader enterprise agent governance without renaming the whole thing.[^7_1][^7_2]

## Positioning line

A clean positioning line could be:

- “A verification-aware governance layer for agentic execution.”[^7_3][^7_2]
- “An inline gateway that forces agents to prove each critical step before proceeding.”[^7_5][^7_4]
- “Runbook enforcement and real-time verification for AI agents operating production systems.”[^7_4][^7_6]

My recommendation: call the broader platform **AEGIS**, and call the first concrete product **VerifyGate** or **Runbook Guardian** depending on whether you want the emphasis on generalized enforcement or the DevOps wedge.[^7_6][^7_2]
<span style="display:none">[^7_11][^7_12][^7_13][^7_14][^7_15]</span>

<div align="center">⁂</div>

[^7_1]: https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/

[^7_2]: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6392459

[^7_3]: https://www.digitalapplied.com/blog/agent-governance-framework-policy-compliance-access

[^7_4]: https://usdm.com/resources/blogs/agents-without-owners-what-rsa-2026-revealed-about-the-agentic-ai-governance-gap

[^7_5]: https://www.linkedin.com/pulse/transition-from-theoretical-responsible-ai-verifiable-abufadda-5mybf

[^7_6]: https://oneuptime.com/blog/post/2026-01-26-effective-runbooks-guide/view

[^7_7]: https://www.strata.io/blog/agentic-identity/the-ai-agent-identity-crisis-new-research-reveals-a-governance-gap/

[^7_8]: https://jetruby.com/blog/enterprise-ai-agents/

[^7_9]: https://www.statuspal.io/blog/top-devops-tools-sre

[^7_10]: https://www.deloitte.com/us/en/insights/topics/technology-management/tech-trends/2026/agentic-ai-strategy.html

[^7_11]: https://www.vybe.build/blog/best-ai-agent-platforms-2026

[^7_12]: https://agentcenter.cloud/blogs/25-best-ai-agent-platforms-2026

[^7_13]: https://www.linkedin.com/posts/david-popoola-op_devops-sre-platformengineering-activity-7414805594106146816-M7hM

[^7_14]: https://cogitx.ai/blog/ai-agents-complete-overview-2026

[^7_15]: https://www.ksolves.com/blog/devops/top-tools


---

# StepProof is a cool name for this.  How might we construct it?

Yes. StepProof can be constructed as a **durable workflow engine + policy gate + verifier fabric** rather than just a hook script. That matches modern 2026 patterns: specialized roles, verifiable execution, and a stateless policy engine intercepting actions before they execute.[^8_1][^8_2][^8_3]

## Core architecture

At a high level, StepProof should have five parts:


| Component | Job |
| :-- | :-- |
| **Workflow engine** | Stores runbooks, step state, retries, timeouts, and evidence; durable execution is now a standard production pattern for multi-step AI workflows [^8_4][^8_5]. |
| **Policy engine** | Intercepts proposed actions and decides allow, deny, transform, or require approval before execution; that is how current agent governance toolkits are being built [^8_3][^8_2][^8_6]. |
| **Verifier fabric** | Runs step checks via deterministic scripts first, then a small verifier model when the evidence is unstructured [^8_1][^8_7]. |
| **Identity/audit layer** | Tracks human owner, worker agent, verifier agent, runbook ID, step ID, and decision history so actions are attributable and auditable [^8_1][^8_3]. |
| **Adapters** | Claude Code hooks, CI, deploy systems, DBs, logs, and cloud APIs; the adapters let StepProof generalize beyond any one coding tool [^8_1][^8_8]. |

The conceptual loop is:

1. A worker tries to perform an action.
2. StepProof checks whether the action is allowed for the current step.
3. If the worker claims the step is complete, StepProof gathers evidence and calls a verifier.
4. Only after verification does StepProof unlock the next step.

## Recommended build shape

I would build StepProof in three layers, not as one monolith:

### 1. Control plane

This is the source of truth:

- Runbook definitions.
- Workflow instances.
- Step states: `pending`, `in_progress`, `awaiting_verification`, `verified`, `failed`, `blocked`.
- Evidence records.
- Policy decisions.
- Audit log.

A durable workflow model is important because multi-step agent flows need retries, resumability, timeouts, and replay-safe state transitions. A good principle from current workflow systems is that business logic belongs in the workflow definition, while external side effects belong in activities/adapters.[^8_4][^8_5]

### 2. Runtime enforcement plane

This is what actually blocks things:

- A **policy engine** sitting in front of risky actions.
- Claude Code `PreToolUse` hooks for local/dev actions.
- CI/deploy gates for repo and infra boundaries.
- Optional HTTP middleware for API-driven agents.

Modern agent governance systems use a stateless engine that intercepts each action and evaluates policy with sub-millisecond overhead, often via YAML, OPA Rego, or Cedar rules. StepProof should copy that pattern.[^8_2][^8_3][^8_6]

### 3. Verification plane

This is how proof happens:

- **Tier 1 verifiers:** scripts, SQL checks, API status checks.
- **Tier 2 verifiers:** small LLM classifier for logs/diffs/output.
- **Tier 3 verifiers:** optional heavyweight review for rare guardrail questions.

2026 coding and multi-agent guidance is very clear that verifiers should demand **execution evidence**, not just static reasoning. So StepProof’s verifier interface should require concrete evidence inputs, not vague “did we do it?” prompts.[^8_7][^8_1]

## Suggested internal model

The core objects could look like this:

- **RunbookTemplate**
    - `template_id`
    - `name`
    - `steps[]`
    - `risk_level`
    - `allowed_environments`
- **StepTemplate**
    - `step_id`
    - `description`
    - `allowed_actions`
    - `required_evidence`
    - `verification_method`
    - `verification_tier`
    - `timeout`
    - `on_fail`
- **WorkflowRun**
    - `run_id`
    - `template_id`
    - `owner_id`
    - `agent_id`
    - `environment`
    - `current_step`
    - `status`
- **StepRun**
    - `run_id`
    - `step_id`
    - `status`
    - `evidence`
    - `verification_result`
- **PolicyDecision**
    - `action`
    - `decision`
    - `reason`
    - `policy_id`
    - `timestamp`

That structure generalizes well because it does not care whether the action is “run psql,” “rotate IAM key,” “approve payroll export,” or “publish model.”

## Policy model

StepProof should treat every attempted action as a normalized event:

```json
{
  "actor_type": "worker_agent",
  "actor_id": "claude-worker-17",
  "human_owner_id": "daniel",
  "run_id": "run_123",
  "step_id": "s3",
  "action_type": "database.write",
  "tool": "psql",
  "target_env": "staging",
  "payload_summary": "apply migration 20260420_add_connector"
}
```

The policy engine then evaluates rules like:

- Deny `database.write` unless current step explicitly allows it.
- Deny raw `psql` when approved wrapper `cerebro-migrate` exists.
- Require verification pass before `deploy.production`.
- Escalate to human approval for `destructive_data` actions.

This mirrors the current governance-toolkit approach of intent classification plus deterministic policy-as-code enforcement. For implementation, OPA/Rego or Cedar are both sensible because the market is already using them for workflow and agent governance.[^8_9][^8_8][^8_3][^8_2]

## Verifier interface

Every verifier should expose one contract:

```json
{
  "run_id": "run_123",
  "step_id": "s3",
  "method": "verify_migration_staging",
  "tier": "tier1",
  "evidence": {
    "migration_name": "20260420_add_connector",
    "deploy_id": "dep_456",
    "database": "staging-main"
  }
}
```

And return:

```json
{
  "status": "pass",
  "confidence": 0.99,
  "reason": "Migration exists in schema_migrations and deploy status is SUCCESS",
  "artifacts": {
    "query_result": "...",
    "deploy_status": "SUCCESS"
  }
}
```

A key modern pattern is that verifier outputs should be **machine-decisive** and structured, not prose-heavy, so the governor can consume them automatically.[^8_10][^8_1]

## Where it generalizes

StepProof generalizes well because “step proof” is a cross-domain primitive, not a DevOps-only one. The same architecture works for:[^8_11][^8_1]

- **DevOps/SRE:** migrations, deploys, incidents, rollback runbooks.
- **Security:** containment, access changes, secret rotation, exception approvals.
- **Data:** backfills, schema promotion, model deployment.
- **Enterprise workflows:** approvals, reconciliations, vendor onboarding, regulated operations.

The reason it generalizes is that all of these are really the same pattern: **durable workflow + bounded action permissions + evidence-based verification + audit trail**.[^8_3][^8_5][^8_12]

## MVP path

I would build it in this order:

1. **Single-node control plane**
    - Postgres tables for runbooks, workflow runs, step runs, and audit log.
2. **Claude Code hook adapter**
    - `PreToolUse` sends candidate action to StepProof policy API.
    - API returns allow/deny plus message.
3. **Step completion endpoint**
    - Worker submits evidence for current step.
    - StepProof dispatches verifier and updates state.
4. **Tier 1 verifier library**
    - Git checks, CI checks, deploy status, DB read-only queries.
5. **Tier 2 verifier**
    - Small model for logs/diffs.
6. **CI/deploy adapters**
    - GitHub Actions, Railway, cloud provider, incident systems.

That gives you the wedge fast: local agent enforcement plus proof-backed deploy/runbook completion. Then you can broaden into a general agent governance platform.

## Product framing

If you build it this way, StepProof is not “a tool that stops Claude from being sloppy.” It becomes:

**A runtime system that forces workers — human or agent — to prove each critical step before the next one is unlocked**.[^8_1][^8_2][^8_3]

A clean first-product positioning line would be:

**StepProof enforces runbooks by turning every risky step into a verifiable checkpoint.**[^8_5][^8_1]

The next artifact I’d create is a concrete technical spec: schema, APIs, hook payloads, and one example flow such as “DB migration + deploy.”
<span style="display:none">[^8_13][^8_14][^8_15][^8_16]</span>

<div align="center">⁂</div>

[^8_1]: https://dev.to/chunxiaoxx/building-multi-agent-ai-systems-in-2026-a2a-observability-and-verifiable-execution-10gn

[^8_2]: https://www.digitalapplied.com/blog/microsoft-agent-governance-toolkit-runtime-security

[^8_3]: https://opensource.microsoft.com/blog/2026/04/02/introducing-the-agent-governance-toolkit-open-source-runtime-security-for-ai-agents/

[^8_4]: https://blog.cloudflare.com/workflows-v2/

[^8_5]: https://www.taskade.com/blog/durable-execution-ai-workflows

[^8_6]: https://www.helpnetsecurity.com/2026/04/03/microsoft-ai-agent-governance-toolkit/

[^8_7]: https://www.augmentcode.com/guides/how-to-run-a-multi-agent-coding-workspace

[^8_8]: https://techcommunity.microsoft.com/blog/linuxandopensourceblog/agent-governance-toolkit-architecture-deep-dive-policy-engines-trust-and-sre-for/4510105

[^8_9]: https://www.firefly.ai/academy/enterprise-ai-workflow-automation

[^8_10]: https://arxiv.org/pdf/2603.11445.pdf

[^8_11]: https://www.moltbook.com/post/bc6f5036-ebf6-4213-9264-aea7f17b4fe0

[^8_12]: https://usdm.com/resources/blogs/agents-without-owners-what-rsa-2026-revealed-about-the-agentic-ai-governance-gap

[^8_13]: https://dev.to/chunxiaoxx/building-multi-agent-ai-systems-in-2026-a2a-observability-and-verifiable-execution-3hi

[^8_14]: https://resources.anthropic.com/hubfs/2026 Agentic Coding Trends Report.pdf

[^8_15]: https://aimultiple.com/agentic-frameworks

[^8_16]: https://github.com/caramaschiHG/awesome-ai-agents-2026


---

# This feels like a new tool that eidosagi.com as a company could release, and it would be a new repo that you help create with docs right now, and I will then boot up a claude code to finish it off.

Repo created. Now let me push all the scaffolding in one go.

---

# do it

Answer skipped.


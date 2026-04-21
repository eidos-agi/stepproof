# Tool-Use Constraints at the Request Layer

Function calling, Claude Code hooks, MCP permissions, and the
general pattern of "restrict what tools the agent can call on this
request." The lowest layer of runtime-side control — and the primitive
that StepProof's hook implementation builds on.

## What's in this category

- **OpenAI function calling / tool use.** API-level declaration of
  what tools the agent can call. The API refuses tools not declared
  in the request. Server-side allowlist.
- **Anthropic tool use / Claude tool use in API.** Similar shape;
  tools declared per-request, responses get routed back to the
  model. Also includes `disable_parallel_tool_use` and related
  primitives.
- **Claude Code hooks.** Pre/Post tool use, session start/end,
  prompt submit. Each is a callback the harness invokes with
  structured JSON; the hook can exit 0 (allow) or 2 (deny with
  stderr shown to the model). StepProof's enforcement mechanism is
  built on PreToolUse.
- **Claude Code `--allowed-tools` / `--disallowed-tools`.** CLI
  flags that scope which tools the agent can use at session level.
- **MCP (Model Context Protocol) permission model.** MCP tools
  declare their capabilities; clients can require approval for
  certain calls. Per-MCP-tool gating.
- **Cursor rules.** Project-level instructions that modify agent
  behavior. Not structural — advisory.

## What this category does well

- **Reduces accidental tool misuse.** An agent that doesn't have
  `Bash` in its allowlist cannot accidentally shell out.
- **Provides a coarse safety boundary.** Agent in read-only mode
  can't write files, period.
- **Enables per-session scoping** at the CLI level in Claude Code.
- **Provides the hook primitive** — without the PreToolUse hook,
  there would be no tool-call-time callback to build StepProof on.

## What it can't do

- **No concept of a step.** Per-request or per-session scoping, not
  per-step-in-a-ceremony. The agent's scope is static across the
  work; there's no "during s1 Edit is fine, during s3 Edit is
  forbidden."
- **No state carrying across calls.** Each hook invocation is a
  fresh process. Hooks don't naturally know "what step we're on" —
  they have to load that from shared state on disk. StepProof builds
  this state layer on top.
- **No evidence gating.** Hooks can deny a tool call, but they
  can't say "you can advance only after you prove X." Advancement
  is not a hook concept.
- **No verification against real external state.** Hooks are
  stdin/stdout gates. They don't query GitHub, the migration
  tracker, or the deploy platform. Verification is a separate layer.
- **No audit log at the ceremony level.** Hooks log their
  individual decisions (if you configure it), but they don't
  assemble those decisions into a causally-ordered trail of a
  multi-step run. That's a workflow-layer concern.
- **Easy to route around when paired with native tools.** If the
  harness exposes native tools (Claude Code's Read, Write, Edit,
  Bash), and you only restrict them via allowlists, a misconfigured
  allowlist leaks capability. StepProof addresses this by having the
  hook fire on every tool call regardless of source.

## How StepProof uses this category

StepProof is built *on top of* Claude Code hooks:

- The PreToolUse hook is the enforcement point. Every tool call
  goes through it.
- The hook reads `.stepproof/active-run.json` to know the current
  step's allowed_tools. Denial is decided against the current
  ceremony's scope, not a session-static allowlist.
- StepProof's classification layer (`action_classification.yaml`)
  extends what the hook can distinguish — bash patterns, path
  globs, MCP tool patterns — so the hook is smarter than a pure
  name-match allowlist.

## Adjacency lines

- The **session-level allowlist** (`--disallowed-tools`) pattern
  suggests an alternative StepProof v1 we considered: ship only as
  an MCP, disable all native tools, route everything through
  StepProof's wrapped tools. See
  [14_stepproof_positioning.md](14_stepproof_positioning.md) for
  why this isn't sufficient on its own (agent can skip the MCP).
- **MCP permissions** are per-tool; StepProof treats MCP tools
  the same as any other tool — classified, scoped per step. MCP's
  own permission model does not compose with the ceremony model
  unless you put a hook on top.

## Known unknowns

- Whether Claude Code's hook model will evolve to natively support
  ceremony state (e.g., a "session state carrier" that hooks can
  read without having to spelunk their own files). Currently no.
- Whether OpenAI's Agents SDK will expose an equivalent of
  PreToolUse hooks. As of this research's date, not fully
  productized in the same shape.
- Whether Cursor will expose a hook-equivalent primitive. Unclear.

## Representative sources

- Anthropic Claude Code documentation — hooks, settings.json,
  allowed-tools.
- Anthropic API reference — tool use / function calling.
- OpenAI API reference — function calling.
- Model Context Protocol spec — `modelcontextprotocol.io`.

## Date stamp

2026-04-20.

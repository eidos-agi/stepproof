# Per-Project `.stepproof/` Convention

StepProof is installed **once** at the user level — the MCP server and daemon are shared across every project the user opens. But **each project gets its own `.stepproof/` directory** for local state, runbook overrides, and audit buffering.

## Layout

```
<project-root>/
├── .stepproof/
│   ├── config.yaml              — per-project overrides (env, classification, shadow defaults)
│   ├── runbooks/                — project-specific runbook YAMLs (loaded alongside built-ins)
│   │   ├── rb-deploy-to-prod.yaml
│   │   └── rb-connector-ship.yaml
│   ├── sessions/                — one JSON per active Claude Code session
│   │   └── <session_id>.json
│   ├── audit-buffer.jsonl       — local append-only buffer when daemon unreachable
│   └── adapter-manifest.json    — what `stepproof install` wrote (for uninstall)
```

## Two scopes, clear split

| Scope | Location | What it holds |
|-------|----------|---------------|
| User-level | `~/.claude/mcp_settings.json` + StepProof daemon | MCP server registration, daemon binary, built-in runbook library, shared audit log |
| Per-project | `<project-root>/.stepproof/` | Active session state, project-specific runbook overrides, audit buffer for graceful-degradation, install manifest |

The user-level install never writes to a project. The per-project `.stepproof/` is the only thing the project owns.

## What lives where — decision table

| Concern | User-level | Per-project |
|---------|-----------|-------------|
| MCP server binary | ✅ | |
| Daemon process | ✅ | |
| Built-in runbook library (the 8 toys) | ✅ | |
| Project-specific runbook (e.g., `rb-example-deploy`) | | ✅ |
| Classification overrides (what does `Bash: terraform apply` mean *here*?) | | ✅ |
| Active session → run mapping | | ✅ |
| Audit log (authoritative, long-term) | ✅ (shared DB) | |
| Audit buffer (when daemon down) | | ✅ |
| Trust score baseline per human owner | ✅ | |
| Trust behavioral signals scoped to this project | | ✅ |

## Git tracking

- **Tracked:** `.stepproof/config.yaml`, `.stepproof/runbooks/*.yaml`.
  These are project contracts — versioned, peer-reviewed, part of the repo.
- **Ignored:** `.stepproof/sessions/`, `.stepproof/audit-buffer.jsonl`, `.stepproof/adapter-manifest.json`.
  These are runtime state — machine-specific, ephemeral.

The project's `.gitignore` should contain:
```
.stepproof/sessions/
.stepproof/audit-buffer.jsonl
.stepproof/adapter-manifest.json
```

## `stepproof init`

New CLI subcommand (Phase 2b) that creates the `.stepproof/` scaffold:

```bash
cd <project>
stepproof init
# creates .stepproof/config.yaml with sensible defaults
# creates .stepproof/runbooks/ (empty, ready for project runbooks)
# appends .stepproof/sessions/ etc to .gitignore
```

Safe to run multiple times — checks before overwriting.

## Why two scopes

- **One install, many projects.** User registers the MCP server once; it's available everywhere without per-project setup.
- **Projects stay authoritative for their own contracts.** A project's runbooks and classification live in the repo, versioned with the code they govern.
- **Session state is never shared.** Two sessions in two projects don't confuse each other's active runs.
- **Audit log is authoritative at user level.** Cross-project forensics ("when did I last rotate the Supabase token?") require a single shared log, not per-project shards.

## Config file shape (project-level)

```yaml
# .stepproof/config.yaml
version: 1

# What environment does this project run against by default?
default_environment: staging

# Extra runbook directories to load beyond the built-in library.
# Paths are relative to project root.
runbook_dirs:
  - .stepproof/runbooks

# Project-specific action classification overrides.
# Merged on top of the user-level classification.yaml.
classification_overrides:
  bash_patterns:
    - match: "^terraform\\s+(apply|destroy)"
      action_type: infra.write
      ring: 3
    - match: "^dbt\\s+run"
      action_type: data.transform
      ring: 2

# Shadow-mode: log-only enforcement while authoring new rules.
shadow: false

# Fail-closed rings for this project (default: fail-open per GUARD-003).
fail_closed_rings: []
```

## Live-session state (internal)

```json
// .stepproof/sessions/<session_id>.json — written by the MCP server, read by hooks
{
  "session_id": "claude-code-a1b2c3",
  "run_id": "uuid",
  "template_id": "rb-deploy-to-prod",
  "source": "declared",
  "current_step": "s3",
  "allowed_tools": ["cerebro_migrate_staging"],
  "denied_tools": ["psql", "pg_dump"],
  "heartbeat_expires_at": "2026-04-20T17:30:00Z",
  "updated_at": "2026-04-20T17:25:10Z"
}
```

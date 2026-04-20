# stepproof-mcp

Model Context Protocol server that exposes StepProof governance to MCP-speaking AI agents (Claude Code, Cursor, and anything else that speaks MCP).

## Modes

- **Embedded** (default): if `STEPPROOF_URL` is unset, the MCP server spawns an in-process StepProof runtime using SQLite. Zero-install, single-user, perfect for local dev and solo operators.
- **Hosted**: set `STEPPROOF_URL=https://your-runtime.example.com`. The MCP server becomes a thin HTTP client. Required for teams and centralized audit.

## Tools

- `stepproof_run_start(template_id, owner_id, environment)` → `{run_id, current_step}`
- `stepproof_run_status(run_id)` → full run state
- `stepproof_step_complete(run_id, step_id, evidence)` → `{status, next_step, verification_result}`
- `stepproof_policy_evaluate(action)` → `{decision, reason, policy_id, suggested_tool}`
- `stepproof_runbook_list()` → `[{template_id, name, risk_level, steps_count}, ...]`
- `stepproof_runbook_get(template_id)` → full template
- `stepproof_heartbeat(run_id, ttl_seconds=300)` → `{liveness_active, expires_at}`

## Run via Claude Code

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "stepproof": {
      "command": "uv",
      "args": ["run", "stepproof", "mcp"]
    }
  }
}
```

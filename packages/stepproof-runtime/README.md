# stepproof-runtime

Control plane for StepProof. FastAPI HTTP service with a filesystem-backed store (one directory per run, JSONL audit stream).

Exposes:

- `POST /runs` — start a workflow from a runbook template
- `POST /runs/:run_id/steps/:step_id/complete` — submit evidence for a step, dispatch verifier
- `POST /runs/:run_id/heartbeat` — register or refresh liveness TTL
- `POST /policy/evaluate` — evaluate a proposed action (called by adapters)
- `GET /runs` — list runs (cursor-paginated)
- `GET /runs/:run_id` — single run state
- `GET /runbooks` — list available runbook templates
- `GET /audit` — cursor-paginated audit log

## Run locally

```bash
uv run stepproof runtime
# => Uvicorn on http://127.0.0.1:8787
```

Set `STEPPROOF_STATE_DIR` to override the state directory (default: `./.stepproof`).
Set `STEPPROOF_RUNBOOKS_DIR` to point at a directory of YAML runbook templates (default: `./examples`).

## On-disk layout

```
.stepproof/
  runs/<run_id>/
    manifest.json      # run metadata; rewritten on status change
    step-<step_id>.json # per-step state + evidence + verifier result
    events.jsonl       # per-run append-only audit stream
    heartbeat.json     # liveness tracker
  events.jsonl          # global audit mirror across all runs
  runtime.url           # live runtime discovery
  active-run.json       # currently-bound run (written by MCP on plan accept)
```

Every write is atomic (tmp file + `os.replace`). Appends to `events.jsonl`
use `O_APPEND` with `fsync`. Single writer per run (the runtime), so
no locking layer is required.

## Package layout

- `stepproof_runtime.store` — filesystem-backed persistence
- `stepproof_runtime.models` — Pydantic models
- `stepproof_runtime.runbooks` — YAML runbook loader (in-memory registry)
- `stepproof_runtime.policy` — YAML policy engine + ring classifier
- `stepproof_runtime.verifiers` — Tier 1 verifier registry
- `stepproof_runtime.api` — FastAPI app
- `stepproof_runtime.cli` — entry point

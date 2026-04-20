# stepproof-runtime

Control plane for StepProof. FastAPI HTTP service with SQLite (embedded mode) or Postgres (hosted mode, later) backing store.

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

Set `STEPPROOF_DB_PATH` to override the SQLite location (default: `./.stepproof/runtime.db`).
Set `STEPPROOF_RUNBOOKS_DIR` to point at a directory of YAML runbook templates (default: `./examples`).

## Package layout

- `stepproof_runtime.db` — SQLite schema + connection
- `stepproof_runtime.models` — Pydantic models
- `stepproof_runtime.runbooks` — YAML runbook loader
- `stepproof_runtime.policy` — YAML policy engine + ring classifier
- `stepproof_runtime.verifiers` — Tier 1 verifier registry
- `stepproof_runtime.api` — FastAPI app
- `stepproof_runtime.cli` — entry point

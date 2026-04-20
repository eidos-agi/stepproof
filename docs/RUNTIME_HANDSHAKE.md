# Runtime Handshake

**Status:** increment 1 of the state-directory refactor. Ships the
`stepproof-state` package and wires it into the MCP server + PreToolUse hook.

## Problem

StepProof has several components — the MCP server (embedded runtime in
`_start_embedded_runtime`), a standalone `stepproof runtime` daemon, the
PreToolUse hook, the CLI — that each need to know the same two things about
the current project:

1. **Where the runtime is listening.** (Before increment 1, the hook
   hard-coded `http://127.0.0.1:8787`, while the MCP server bound a random
   free port. They never found each other.)
2. **Which run the agent is currently bound to.** The hook has to forward
   `run_id` and `current_step` on every policy call; enforcing `allowed_tools`
   requires knowing which step the agent promised to stay inside.

One process writes; the others read. Every writer must clean up after itself.
Every reader must tolerate a stale file from a writer that crashed.

## Contract

Two files inside `.stepproof/`:

```
.stepproof/
├── runtime.url        # runtime discovery (owned by whoever serves the runtime)
└── active-run.json    # active-run binding (owned by the MCP server)
```

### runtime.url

```json
{
  "url":        "http://127.0.0.1:54823",
  "pid":        41271,
  "started_at": "2026-04-20T16:24:01Z"
}
```

- **Writer:** the MCP server after embedded uvicorn binds its port, or a
  standalone `stepproof runtime` when it starts listening.
- **Cleanup:** the writer registers `atexit` and SIGTERM/SIGINT handlers that
  delete the file. SIGKILL bypasses both — hence the PID-liveness reaper on
  the read path.
- **Reader:** anyone who wants to talk to the runtime. Precedence:
  1. `STEPPROOF_URL` env var (operator override)
  2. `.stepproof/runtime.url` with a live PID
  3. `http://127.0.0.1:8787` fallback (legacy; will disappear when the
     standalone CLI migrates in increment 2)

### active-run.json

```json
{
  "run_id":        "5d9a7e37-...",
  "current_step":  "s2",
  "allowed_tools": ["Edit", "git"],
  "template_id":   "rb-declared-abc123"
}
```

- **Writer:** the MCP server on `stepproof_keep_me_honest` / `stepproof_run_start`
  acceptance and on each `stepproof_step_complete` that advances the step.
  Cleared when the run reaches a terminal state (`COMPLETED` / `FAILED` /
  `ABANDONED`).
- **Reader:** the hook, on every invocation, to forward `run_id` + `step_id`
  to `/policy/evaluate` and to enforce per-step `allowed_tools` structurally.

## Invariants

1. **Atomicity.** Every write goes through `atomic_write_json()` (tmp file in
   the same directory, fsync, `os.replace`). Readers never observe a partial
   file. Enforced by `test_atomic_write_never_exposes_partial_file`.
2. **Single writer for `runtime.url`.** Starting a second MCP in the same
   project overwrites the record; the earlier runtime continues to serve, but
   the project's canonical URL now points at the newer owner. Enforced by
   `test_two_mcp_starts_second_takes_ownership`.
3. **Stale-state reaping.** Readers resolving `runtime.url` confirm the
   writer's PID is alive (`os.kill(pid, 0)`) and delete the file if not.
   Enforced by `test_mcp_sigkill_stale_record_is_reaped`.
4. **Schema tolerance.** Unknown fields in `active-run.json` are ignored so
   future versions can add fields without breaking vendored hooks. Enforced
   by `test_active_run_unknown_fields_ignored`.
5. **Bootstrap.** First write to a nonexistent `.stepproof/` creates the
   directory. Enforced by `test_state_dir_bootstrapped_on_first_write`.
6. **State dir is overridable.** `STEPPROOF_STATE_DIR` relocates everything
   — required for test isolation and for users who keep runtime state outside
   the project tree. Enforced by `test_state_dir_respects_env_override`.

## Failure modes

| Failure                          | Detected by                 | Response                                      |
|----------------------------------|-----------------------------|-----------------------------------------------|
| Writer crashed (SIGKILL)         | PID-liveness on read         | Reap stale `runtime.url`, fall back to legacy |
| `runtime.url` corrupted JSON     | `json.loads` in read path    | Return `None`; caller falls back              |
| Runtime unreachable (any reason) | httpx timeout                | Hook buffers audit, fail-closed by default    |
| Tool outside `allowed_tools`     | Structural check in hook     | Exit 2, name the step and the allowed set     |

## The hook ships standalone

`stepproof install` copies `stepproof_pretooluse.py` into the user's
`.claude/hooks/`. The copy has no access to the uv workspace, so the hook
vendors the ~100 lines of state-directory logic inline (marked `BEGIN/END
vendored stepproof_state`). When the package evolves, that block must be
kept in lockstep — the dedicated tests in `test_runtime_handshake.py` run
the hook as a subprocess and will catch drift.

## Test matrix

The full integration matrix lives at `tests/integration/test_runtime_handshake.py`:

| #  | Test                                                            | Asserts                                   |
|----|-----------------------------------------------------------------|-------------------------------------------|
| 1  | `test_mcp_sigterm_cleans_runtime_url`                           | SIGTERM → atexit fires → file deleted      |
| 2  | `test_mcp_sigkill_stale_record_is_reaped`                       | Dead PID → reader reaps file               |
| 3  | `test_atexit_on_normal_exit_cleans_runtime_url`                 | Normal exit path cleans up                 |
| 4  | `test_two_mcp_starts_second_takes_ownership`                    | No silent dual-writer                      |
| 5  | `test_runtime_url_corrupt_json_is_tolerated`                    | Garbage in → `None` out, no crash          |
| 6  | `test_active_run_unknown_fields_ignored`                        | Forward-compat schema evolution            |
| 7  | `test_state_dir_bootstrapped_on_first_write`                    | Fresh project gets a correct directory     |
| 8  | `test_hook_allows_write_listed_in_allowed_tools`                | Declared tool is not blocked               |
| 9  | `test_hook_denies_dotenv_write_clientside`                      | `.env` rule fires independent of runtime   |
| 10 | `test_hook_fail_closed_when_no_runtime`                         | Ring 1+ without runtime → structural deny  |
| 11 | `test_hook_propagates_runtime_deny`                             | Runtime reachable, scoped deny reported    |
| 12 | `test_hook_denies_tool_outside_allowed_tools`                   | Per-step scoping names step + allowed set  |
| 13 | `test_atomic_write_never_exposes_partial_file`                  | Concurrent readers never see half-writes   |
| 14 | `test_state_dir_respects_env_override`                          | `STEPPROOF_STATE_DIR` works end-to-end     |

## What this increment does not do

- **CLI migration.** The standalone `stepproof runtime` CLI still operates
  under the same state-file contract, but its integration tests ship in
  increment 2 together with the removal of the legacy port-8787 fallback.
- **`events.jsonl` audit trail.** Designed for increment 3. Today, lifecycle
  events are observable only by reading the file and pinging the runtime.

## See also

- `docs/ADAPTER_BRIDGE.md` — the broader hook/runtime bridge design.
- `packages/stepproof-state/` — the library that implements this contract.
- `tests/integration/test_runtime_handshake.py` — the matrix above.

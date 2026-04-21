# StepProof dev commands.

# Install all workspace packages in editable mode.
setup:
    uv sync --all-packages

# Run the runtime locally (embedded SQLite).
runtime:
    uv run stepproof runtime

# Run the MCP server (stdio; used by Claude Code / Cursor).
mcp:
    uv run stepproof mcp

# Run the smoke test suite.
smoke:
    uv run pytest tests/smoke -v

# Run the integration test suite (runtime handshake + state lifecycle).
integration:
    uv run pytest tests/integration -v

# Full in-repo test matrix (smoke + integration).
test:
    uv run pytest tests -v

# End-to-end smoke (single-step plan): install, spawn MCP, exercise hook, uninstall.
e2e *ARGS:
    uv run python scripts/e2e_smoke.py {{ARGS}}

# End-to-end smoke (two-step plan): prove per-step scoping follows step transitions.
e2e2 *ARGS:
    uv run python scripts/e2e_smoke_2.py {{ARGS}}

# Complex #1 — verification-failure path (retry after failed verifier).
complex1 *ARGS:
    uv run python scripts/e2e_complex_1.py {{ARGS}}

# Complex #2 — three-step sequence with out-of-order attempts.
complex2 *ARGS:
    uv run python scripts/e2e_complex_2.py {{ARGS}}

# Level 4 — real Claude Code session against an installed StepProof project.
# Requires the `claude` CLI on PATH and network for the model call.
level4 *ARGS:
    uv run python scripts/e2e_level4.py {{ARGS}}

# Migration-bypass replay — real Claude Code session enacting the raw-psql
# shortcut pattern. Proves StepProof stops the bypass.
bypass *ARGS:
    uv run python scripts/e2e_bypass.py {{ARGS}}

# Blind trap — realistic task where the agent doesn't know the hook will fire
# until it reaches for a scoped-out tool during normal work.
blind *ARGS:
    uv run python scripts/e2e_blind_trap.py {{ARGS}}

# All smokes. Level-4-class tests are last because they invoke `claude -p`.
all-smokes: e2e e2e2 complex1 complex2 level4 bypass blind

# List registered runbook templates (requires runtime running).
runbooks:
    uv run stepproof runbooks

# Tail the audit log (requires runtime running).
audit:
    uv run stepproof audit

# Lint.
lint:
    uv run ruff check .

# Format.
fmt:
    uv run ruff format .

# Rebuild chart PNGs from the Mermaid sources in charts/src/.
charts:
    #!/usr/bin/env bash
    set -e
    mkdir -p charts/rendered
    for f in charts/src/*.mmd; do
        name=$(basename "$f" .mmd)
        echo "rendering $name"
        npx -y -p @mermaid-js/mermaid-cli mmdc -i "$f" -o "charts/rendered/$name.png" -w 1400 -b white
    done

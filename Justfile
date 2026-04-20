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

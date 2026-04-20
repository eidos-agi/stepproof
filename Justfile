# StepProof dev commands.

# Install all workspace packages in editable mode.
setup:
    uv sync --all-packages

# Run the runtime locally (embedded SQLite).
runtime:
    uv run --package stepproof-runtime stepproof-runtime

# Run the MCP server (stdio; used by Claude Code / Cursor).
mcp:
    uv run --package stepproof-mcp stepproof-mcp

# Run the smoke test suite.
smoke:
    uv run pytest tests/smoke -v

# Lint.
lint:
    uv run ruff check .

# Format.
fmt:
    uv run ruff format .

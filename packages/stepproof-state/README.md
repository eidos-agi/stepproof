# stepproof-state

Shared primitives for the StepProof `.stepproof/` state directory.

Every StepProof component (MCP server, hooks, CLI, standalone daemon) must
agree on:

- Where the runtime is listening (`.stepproof/runtime.url`)
- Which run is currently bound (`.stepproof/active-run.json`)
- How to write both atomically and clean them up on shutdown

This package is that contract. The hook ships standalone (via `stepproof
install`, which vendors the logic inline), so the module is also small enough
to copy verbatim.

See `docs/RUNTIME_HANDSHAKE.md` for the handshake protocol.

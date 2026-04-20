"""Entry point for `stepproof-runtime`."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("STEPPROOF_HOST", "127.0.0.1")
    port = int(os.getenv("STEPPROOF_PORT", "8787"))
    uvicorn.run("stepproof_runtime.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

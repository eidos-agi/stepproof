"""Subprocess driver: starts the MCP embedded runtime + state publishing,
prints the base URL on stdout, then waits until signaled.

Used by tests/integration/test_runtime_handshake.py to exercise the full
boot/shutdown lifecycle under SIGTERM, SIGKILL, and normal exit.

Optional argv:
    --self-exit-after SECONDS   terminate cleanly after N seconds (for the
                                atexit-on-normal-exit test).
"""

from __future__ import annotations

import asyncio
import signal
import sys

from stepproof_mcp.server import _install_cleanup, _start_embedded_runtime


async def _main() -> None:
    self_exit_after: float | None = None
    if "--self-exit-after" in sys.argv:
        idx = sys.argv.index("--self-exit-after")
        self_exit_after = float(sys.argv[idx + 1])

    url = await _start_embedded_runtime()
    _install_cleanup()

    # Announce the URL so the test can unblock once boot is done.
    sys.stdout.write(url + "\n")
    sys.stdout.flush()

    stop = asyncio.Event()

    def _trigger_stop(_signum: int, _frame: object) -> None:
        stop.set()

    # The server.py already installs raising signal handlers. For the
    # self-exit test we want a graceful asyncio shutdown; install a local
    # handler that just toggles the event.
    if self_exit_after is not None:
        signal.signal(signal.SIGTERM, _trigger_stop)
        signal.signal(signal.SIGINT, _trigger_stop)
        try:
            await asyncio.wait_for(stop.wait(), timeout=self_exit_after)
        except asyncio.TimeoutError:
            pass
    else:
        # Let the server.py-installed handlers raise SystemExit on SIGTERM/
        # SIGINT; just hang here.
        await stop.wait()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass

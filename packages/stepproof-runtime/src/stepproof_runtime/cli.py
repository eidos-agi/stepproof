"""Unified `stepproof` CLI.

Subcommands:
  stepproof runtime          — start the control plane (FastAPI + SQLite)
  stepproof mcp              — start the MCP server over stdio
  stepproof smoke            — run the smoke tests
  stepproof runbooks         — list runbook templates
  stepproof run start <id>   — start a run against a template
  stepproof run status <id>  — show current state of a run
  stepproof run list         — list recent runs
  stepproof step complete <run_id> <step_id> --evidence k=v ...
  stepproof audit            — tail the audit log
  stepproof install          — wire StepProof into the current project's Claude Code
  stepproof version

The CLI talks to the runtime over HTTP (STEPPROOF_URL) except for `runtime`/`mcp`
which are the daemon entrypoints themselves.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any

VERSION = "0.0.1"


def _http_get(path: str) -> Any:
    import httpx

    base = os.getenv("STEPPROOF_URL", "http://127.0.0.1:8787").rstrip("/")
    with httpx.Client(base_url=base, timeout=10.0) as c:
        r = c.get(path)
        r.raise_for_status()
        return r.json()


def _http_post(path: str, body: dict) -> Any:
    import httpx

    base = os.getenv("STEPPROOF_URL", "http://127.0.0.1:8787").rstrip("/")
    with httpx.Client(base_url=base, timeout=10.0) as c:
        r = c.post(path, json=body)
        r.raise_for_status()
        return r.json()


def cmd_runtime(args: argparse.Namespace) -> int:
    import uvicorn

    host = args.host or os.getenv("STEPPROOF_HOST", "127.0.0.1")
    port = args.port or int(os.getenv("STEPPROOF_PORT", "8787"))
    uvicorn.run("stepproof_runtime.api:app", host=host, port=port, reload=False)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from stepproof_mcp.server import main as mcp_main

    mcp_main()
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    return subprocess.call([sys.executable, "-m", "pytest", "tests/smoke", "-v"])


def cmd_runbooks(args: argparse.Namespace) -> int:
    data = _http_get("/runbooks")
    for rb in data["runbooks"]:
        print(
            f"  {rb['template_id']:40s}  v{rb['version']:6s}  "
            f"{rb['risk_level']:8s}  {rb['steps_count']} steps"
        )
    return 0


def cmd_run_start(args: argparse.Namespace) -> int:
    body = {
        "template_id": args.template_id,
        "owner_id": args.owner or os.getenv("USER", "unknown"),
        "agent_id": args.agent or "cli",
        "environment": args.env,
    }
    data = _http_post("/runs", body)
    print(json.dumps(data, indent=2))
    return 0


def cmd_run_status(args: argparse.Namespace) -> int:
    data = _http_get(f"/runs/{args.run_id}")
    print(json.dumps(data, indent=2))
    return 0


def cmd_run_list(args: argparse.Namespace) -> int:
    data = _http_get(f"/runs?limit={args.limit}")
    for r in data["runs"]:
        print(
            f"  {r['run_id']}  {r['template_id']:40s}  "
            f"{r['status']:10s}  step={r.get('current_step') or '-'}"
        )
    return 0


def _parse_evidence(pairs: list[str]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for p in pairs or []:
        if "=" not in p:
            raise SystemExit(f"Invalid --evidence: {p!r} (expected key=value)")
        k, v = p.split("=", 1)
        evidence[k] = v
    return evidence


def cmd_step_complete(args: argparse.Namespace) -> int:
    body = {"evidence": _parse_evidence(args.evidence)}
    data = _http_post(
        f"/runs/{args.run_id}/steps/{args.step_id}/complete", body
    )
    print(json.dumps(data, indent=2))
    return 0 if data["verification_result"]["status"] == "pass" else 1


def cmd_audit(args: argparse.Namespace) -> int:
    path = "/audit" + (f"?run_id={args.run_id}" if args.run_id else "")
    data = _http_get(path)
    for e in reversed(data["events"]):
        line = (
            f"[{e['timestamp']}] {e['action_type']:18s} "
            f"{e.get('decision') or '-':8s} "
            f"{e.get('policy_id') or '-':38s} "
            f"{e.get('reason') or ''}"
        )
        print(line)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    print("stepproof install: wiring Claude Code adapter is Phase 2 work.")
    print("See docs/ADAPTER_BRIDGE.md for the design.")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    print(VERSION)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stepproof", description="StepProof CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("runtime", help="Start the control plane")
    pr.add_argument("--host")
    pr.add_argument("--port", type=int)
    pr.set_defaults(func=cmd_runtime)

    pm = sub.add_parser("mcp", help="Start the MCP server over stdio")
    pm.set_defaults(func=cmd_mcp)

    ps = sub.add_parser("smoke", help="Run the smoke test suite")
    ps.set_defaults(func=cmd_smoke)

    prb = sub.add_parser("runbooks", help="List runbook templates")
    prb.set_defaults(func=cmd_runbooks)

    prun = sub.add_parser("run", help="Run lifecycle commands")
    prun_sub = prun.add_subparsers(dest="run_cmd", required=True)

    prun_start = prun_sub.add_parser("start", help="Start a run from a template")
    prun_start.add_argument("template_id")
    prun_start.add_argument("--owner")
    prun_start.add_argument("--agent")
    prun_start.add_argument("--env", default="staging")
    prun_start.set_defaults(func=cmd_run_start)

    prun_status = prun_sub.add_parser("status", help="Show a run's state")
    prun_status.add_argument("run_id")
    prun_status.set_defaults(func=cmd_run_status)

    prun_list = prun_sub.add_parser("list", help="List recent runs")
    prun_list.add_argument("--limit", type=int, default=50)
    prun_list.set_defaults(func=cmd_run_list)

    pstep = sub.add_parser("step", help="Step lifecycle commands")
    pstep_sub = pstep.add_subparsers(dest="step_cmd", required=True)

    pstep_complete = pstep_sub.add_parser("complete", help="Submit evidence for a step")
    pstep_complete.add_argument("run_id")
    pstep_complete.add_argument("step_id")
    pstep_complete.add_argument("--evidence", "-e", action="append", default=[])
    pstep_complete.set_defaults(func=cmd_step_complete)

    paudit = sub.add_parser("audit", help="Show recent audit events")
    paudit.add_argument("--run-id")
    paudit.set_defaults(func=cmd_audit)

    pinst = sub.add_parser("install", help="Wire StepProof into a Claude Code project")
    pinst.set_defaults(func=cmd_install)

    pver = sub.add_parser("version", help="Show version")
    pver.set_defaults(func=cmd_version)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()

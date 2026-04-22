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
  stepproof metrics          — off-rails rate + counters from events.jsonl
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
    """Install the cc-adapter: hook scripts, subagents, slash commands, settings.json."""
    try:
        from stepproof_cc_adapter.installer import install as _install
    except ImportError:
        print(
            "stepproof-cc-adapter package not installed; run `uv sync --all-packages` first.",
            file=sys.stderr,
        )
        return 1

    from pathlib import Path

    scope = args.scope
    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    manifest = _install(scope=scope, project_dir=project_dir)
    print(f"StepProof Claude Code adapter installed ({scope}).")
    print(f"  base_dir: {manifest.base_dir}")
    print(f"  hooks registered: {', '.join(manifest.hook_events_registered)}")
    print(f"  files written: {len(manifest.files_written)}")
    print(
        f"  manifest: {(project_dir or Path.cwd()).resolve()}/"
        ".stepproof/adapter-manifest.json"
    )
    print("\nNext: restart Claude Code so settings.json and hooks reload.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Reverse a prior install using the project's adapter-manifest.json."""
    try:
        from stepproof_cc_adapter.installer import uninstall as _uninstall
    except ImportError:
        print("stepproof-cc-adapter package not installed.", file=sys.stderr)
        return 1

    from pathlib import Path

    project_dir = Path(args.project_dir).resolve() if args.project_dir else None
    try:
        summary = _uninstall(project_dir=project_dir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print("StepProof Claude Code adapter uninstalled.")
    print(f"  scope: {summary['scope']}")
    print(f"  files removed: {len(summary['files_removed'])}")
    print(f"  events unregistered: {', '.join(summary['events_unregistered']) or 'none'}")
    return 0


DEFAULT_GITIGNORE_BLOCK = """\
# StepProof runtime state (machine-specific, ephemeral).
# NOTE: .stepproof/ itself is TRACKED — the layout mirrors .visionlog/.
# Only these child paths are runtime noise.
.stepproof/sessions/
.stepproof/audit-buffer.jsonl
.stepproof/adapter-manifest.json
.stepproof/runs/
.stepproof/events.jsonl
.stepproof/runtime.url
.stepproof/active-run.json
"""

# Directories mirror .visionlog's artifact-per-folder convention.
# Each dir gets a README so git tracks it even when empty.
TRACKED_DIRS = {
    "runbooks": (
        "# Project runbooks\n\n"
        "YAMLs in this directory are loaded into StepProof alongside the "
        "built-in library. See docs/RUNBOOKS.md for the schema.\n"
    ),
    "overrides": (
        "# Classification overrides\n\n"
        "YAML files here extend the user-level action classification with "
        "project-specific rules (e.g., `terraform apply` → Ring 3).\n"
    ),
    "plans": (
        "# Declared plans (audit trail)\n\n"
        "Approved `keep_me_honest` plan hashes land here for peer review. "
        "Tracked in git; becomes part of the project's compliance record.\n"
    ),
}

# Gitignored — session state, audit buffer, install manifest.
EPHEMERAL_DIRS = ("sessions",)


def _build_config(project_id: str, project_name: str, created: str) -> str:
    return f"""\
---
id: "{project_id}"
project: "{project_name}"
created: "{created}"
version: 1
---

# .stepproof/config.yaml — per-project StepProof configuration.
# See docs/PROJECT_STATE.md for the full shape. Mirrors .visionlog conventions.

default_environment: staging

runbook_dirs:
  - .stepproof/runbooks

override_dirs:
  - .stepproof/overrides

shadow: false
fail_closed_rings: []
"""


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize .stepproof/ in a project — mirrors .visionlog conventions.

    Creates:
      .stepproof/config.yaml       — project config with stable UUID
      .stepproof/runbooks/         — tracked; project runbook YAMLs
      .stepproof/overrides/        — tracked; classification overrides
      .stepproof/plans/            — tracked; approved declared-plan hashes
      .stepproof/sessions/         — ephemeral; gitignored
    """
    import uuid
    from datetime import date
    from pathlib import Path

    root = Path(args.path).resolve()
    sp_dir = root / ".stepproof"
    cfg_path = sp_dir / "config.yaml"
    gitignore_path = root / ".gitignore"

    sp_dir.mkdir(exist_ok=True)

    # Tracked subdirs with README.md sentinels.
    for name, readme_body in TRACKED_DIRS.items():
        d = sp_dir / name
        d.mkdir(exist_ok=True)
        readme = d / "README.md"
        if not readme.exists():
            readme.write_text(readme_body)

    # Ephemeral subdirs — dir itself is gitignored.
    for name in EPHEMERAL_DIRS:
        (sp_dir / name).mkdir(exist_ok=True)

    # Config — preserve existing id on re-init.
    if cfg_path.exists() and not args.force:
        print(f"{cfg_path} already exists; leaving it. (--force to regenerate)")
    else:
        project_id = str(uuid.uuid4())
        project_name = args.name or root.name
        created = date.today().isoformat()
        cfg_path.write_text(_build_config(project_id, project_name, created))
        print(f"wrote {cfg_path} (id={project_id})")

    # .gitignore hygiene.
    if gitignore_path.exists():
        current = gitignore_path.read_text()
        if ".stepproof/sessions/" not in current:
            with gitignore_path.open("a") as f:
                if not current.endswith("\n"):
                    f.write("\n")
                f.write("\n")
                f.write(DEFAULT_GITIGNORE_BLOCK)
            print(f"appended .stepproof/* ignore rules to {gitignore_path}")
        else:
            print(f"{gitignore_path} already ignores .stepproof runtime state; leaving it")
    else:
        gitignore_path.write_text(DEFAULT_GITIGNORE_BLOCK)
        print(f"wrote {gitignore_path}")

    print(f"\nStepProof initialized at {sp_dir}")
    print("Tracked: config.yaml, runbooks/, overrides/, plans/")
    print("Ignored: sessions/, audit-buffer.jsonl, adapter-manifest.json, runs/, events.jsonl, runtime.url, active-run.json")
    return 0


def cmd_audit_verify(args: argparse.Namespace) -> int:
    """Verify the hash chain of an events.jsonl file is intact."""
    from pathlib import Path

    from stepproof_runtime import store

    if args.run_id:
        path = store.run_dir(args.run_id) / "events.jsonl"
    elif args.path:
        path = Path(args.path).resolve()
    else:
        path = store.global_events_path()

    if not path.exists():
        print(f"no audit log at {path}")
        return 1

    ok, n, reason = store.verify_audit_chain(path)
    if ok:
        print(f"OK — {n} records, chain intact ({path})")
        return 0
    print(f"BROKEN — checked {n} records; {reason} ({path})")
    return 2


def cmd_metrics(args: argparse.Namespace) -> int:
    """Compute off-rails rate + related counters from events.jsonl.

    Runs locally against `.stepproof/runs/*/events.jsonl` — no HTTP, no
    runtime required. The point is that any team can point this at their
    own audit log after 2-3 weeks of use and get a ground-truth answer
    to the ROI question (Q1-Q5) rather than relying on modeled guesses.
    """
    from stepproof_runtime import metrics

    m = metrics.compute(run_id=args.run_id, days=args.days)
    if args.json:
        print(json.dumps(m, indent=2))
    else:
        print(metrics.format_report(m))
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
    paudit_sub = paudit.add_subparsers(dest="audit_cmd")
    paudit.add_argument("--run-id")
    paudit.set_defaults(func=cmd_audit)

    paudit_verify = paudit_sub.add_parser(
        "verify",
        help="Verify the audit log's hash chain is intact",
    )
    paudit_verify.add_argument("--run-id", help="Verify a single run's log")
    paudit_verify.add_argument(
        "--path", help="Verify an arbitrary events.jsonl file"
    )
    paudit_verify.set_defaults(func=cmd_audit_verify)

    pinst = sub.add_parser("install", help="Wire StepProof into Claude Code")
    pinst.add_argument("--scope", choices=["user", "project"], default="user",
                       help="user (~/.claude/) or project (<cwd>/.claude/). Default: user.")
    pinst.add_argument("--project-dir", help="Where to write the adapter-manifest.json (default: cwd).")
    pinst.set_defaults(func=cmd_install)

    puninst = sub.add_parser("uninstall", help="Reverse a prior install using the manifest")
    puninst.add_argument("--project-dir", help="Where to find adapter-manifest.json (default: cwd).")
    puninst.set_defaults(func=cmd_uninstall)

    pinit = sub.add_parser("init", help="Initialize .stepproof/ in a project")
    pinit.add_argument("path", nargs="?", default=".")
    pinit.add_argument("--name", help="Project name (defaults to directory name)")
    pinit.add_argument("--force", action="store_true",
                       help="Regenerate .stepproof/config.yaml (new UUID)")
    pinit.set_defaults(func=cmd_init)

    pmet = sub.add_parser(
        "metrics",
        help="Compute off-rails rate + related counters from events.jsonl",
    )
    pmet.add_argument("--run-id", help="Restrict to a single run")
    pmet.add_argument(
        "--days", type=int,
        help="Only include events within the last N days",
    )
    pmet.add_argument("--json", action="store_true", help="Emit raw JSON")
    pmet.set_defaults(func=cmd_metrics)

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

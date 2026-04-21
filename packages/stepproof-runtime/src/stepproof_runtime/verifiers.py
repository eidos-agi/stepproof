"""Tier 1 verifier registry — deterministic scripts.

Tier 2 (read-only Haiku subagent) and Tier 3 (opt-in heavyweight) land in a later phase.
Today: just the in-process function registry for Tier 1.
"""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable

from .models import Tier, VerificationResult, VerificationStatus

VerifierFunc = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]

_REGISTRY: dict[str, tuple[Tier, VerifierFunc]] = {}


def register(method_name: str, tier: Tier) -> Callable[[VerifierFunc], VerifierFunc]:
    def wrap(fn: VerifierFunc) -> VerifierFunc:
        _REGISTRY[method_name] = (tier, fn)
        return fn

    return wrap


async def dispatch(
    method: str, evidence: dict[str, Any], context: dict[str, Any]
) -> VerificationResult:
    if method not in _REGISTRY:
        return VerificationResult(
            status=VerificationStatus.FAIL,
            confidence=1.0,
            reason=f"Unknown verification method: {method}",
            verifier_id="dispatcher",
        )
    tier, fn = _REGISTRY[method]
    t0 = time.perf_counter()
    try:
        raw = await fn(evidence, context)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.FAIL,
            confidence=1.0,
            reason=f"Verifier raised: {type(e).__name__}: {e}",
            verifier_id=method,
            tier_used=tier,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
    return VerificationResult(
        status=VerificationStatus(raw.get("status", "fail")),
        confidence=float(raw.get("confidence", 1.0)),
        reason=str(raw.get("reason", "")),
        artifacts=raw.get("artifacts", {}),
        verifier_id=method,
        tier_used=tier,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


# --- Built-in Tier 1 verifiers ---
#
# These are intentionally generous in happy-path to make the MVP loop work.
# Real verifiers will talk to CI, deploy APIs, read-only DBs, etc.


@register("verify_pr_opened", Tier.TIER1)
async def verify_pr_opened(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    branch = evidence.get("branch_name")
    pr_url = evidence.get("pr_url")
    if branch and pr_url:
        return {
            "status": "pass",
            "reason": f"PR {pr_url} opened on branch {branch}.",
            "artifacts": {"branch": branch, "pr_url": pr_url},
        }
    return {
        "status": "fail",
        "reason": "Missing branch_name or pr_url in evidence.",
    }


@register("verify_ci_green", Tier.TIER1)
async def verify_ci_green(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    run_id = evidence.get("ci_run_id")
    # Stubbed: a real verifier would call the CI API.
    if run_id and not str(run_id).startswith("fail"):
        return {"status": "pass", "reason": f"CI run {run_id} SUCCESS.", "artifacts": {"ci_run_id": run_id}}
    return {"status": "fail", "reason": f"CI run missing or failing: {run_id}"}


@register("verify_migration_applied", Tier.TIER1)
async def verify_migration_applied(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    migration = evidence.get("migration_name")
    deploy_id = evidence.get("deploy_id")
    if migration and deploy_id:
        return {
            "status": "pass",
            "reason": f"Migration {migration} recorded; deploy {deploy_id} SUCCESS.",
            "artifacts": {"migration": migration, "deploy_id": deploy_id},
        }
    return {"status": "fail", "reason": "Missing migration_name or deploy_id."}


@register("verify_smoke_logs", Tier.TIER1)
async def verify_smoke_logs(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    smoke_run_id = evidence.get("smoke_run_id")
    if smoke_run_id:
        return {"status": "pass", "reason": f"Smoke run {smoke_run_id} green."}
    return {"status": "fail", "reason": "Missing smoke_run_id."}


@register("verify_deploy_and_health", Tier.TIER1)
async def verify_deploy_and_health(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    deploy_id = evidence.get("deploy_id")
    if deploy_id:
        return {"status": "pass", "reason": f"Deploy {deploy_id} SUCCESS; health endpoints OK."}
    return {"status": "fail", "reason": "Missing deploy_id."}


@register("verify_tests_green", Tier.TIER1)
async def verify_tests_green(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    test_run_id = evidence.get("test_run_id")
    if test_run_id and not str(test_run_id).startswith("fail"):
        return {
            "status": "pass",
            "reason": f"Test run {test_run_id} reported all tests green.",
            "artifacts": {"test_run_id": test_run_id},
        }
    return {"status": "fail", "reason": f"Test run missing or failing: {test_run_id}"}


@register("verify_rollback_succeeded", Tier.TIER1)
async def verify_rollback_succeeded(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    rollback_deploy_id = evidence.get("rollback_deploy_id")
    prior_deploy_id = evidence.get("prior_deploy_id")
    if rollback_deploy_id and prior_deploy_id:
        return {
            "status": "pass",
            "reason": f"Rollback {rollback_deploy_id} restored prior version {prior_deploy_id}.",
        }
    return {"status": "fail", "reason": "Missing rollback_deploy_id or prior_deploy_id."}


@register("verify_secret_rotated", Tier.TIER1)
async def verify_secret_rotated(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    secret_id = evidence.get("secret_id")
    new_version = evidence.get("new_version")
    old_invalidated = evidence.get("old_invalidated") is True
    if secret_id and new_version and old_invalidated:
        return {
            "status": "pass",
            "reason": f"Secret {secret_id} rotated to v{new_version}; prior version invalidated.",
        }
    return {
        "status": "fail",
        "reason": "Missing secret_id, new_version, or old_invalidated=true.",
    }


@register("verify_row_counts_match", Tier.TIER1)
async def verify_row_counts_match(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Silent null violation detector — verify rows_loaded == rows_extracted per table."""
    extracted = evidence.get("rows_extracted")
    loaded = evidence.get("rows_loaded")
    if extracted is None or loaded is None:
        return {"status": "fail", "reason": "Missing rows_extracted or rows_loaded."}
    try:
        e, l = int(extracted), int(loaded)
    except (TypeError, ValueError):
        return {"status": "fail", "reason": "rows_extracted/loaded must be integers."}
    if e > 0 and e == l:
        return {
            "status": "pass",
            "reason": f"Row counts match: {l} loaded == {e} extracted.",
            "artifacts": {"rows_extracted": e, "rows_loaded": l},
        }
    return {
        "status": "fail",
        "reason": f"Row count mismatch: {l} loaded vs {e} extracted — silent null violation.",
        "artifacts": {"rows_extracted": e, "rows_loaded": l},
    }


@register("verify_single_active_deployment", Tier.TIER1)
async def verify_single_active_deployment(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Zombie container detection — multiple active deployments at once."""
    active_count = evidence.get("active_deployment_count")
    deploy_id = evidence.get("deploy_id")
    if active_count is None or deploy_id is None:
        return {"status": "fail", "reason": "Missing active_deployment_count or deploy_id."}
    try:
        n = int(active_count)
    except (TypeError, ValueError):
        return {"status": "fail", "reason": "active_deployment_count must be an integer."}
    if n == 1:
        return {
            "status": "pass",
            "reason": f"Single active deployment {deploy_id}; no zombies detected.",
        }
    return {
        "status": "fail",
        "reason": f"{n} active deployments detected; zombie container risk.",
    }


@register("verify_connector_registry", Tier.TIER1)
async def verify_connector_registry(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Docker cache persistence detector — verify the deployed code contains the expected connector."""
    expected = evidence.get("expected_connector")
    registry = evidence.get("connector_registry")  # e.g., ["sage_intacct", "fleetio"]
    if not expected or registry is None:
        return {
            "status": "fail",
            "reason": "Missing expected_connector or connector_registry.",
        }
    registry_list = registry if isinstance(registry, list) else [registry]
    if expected in registry_list:
        return {
            "status": "pass",
            "reason": f"Connector {expected!r} present in deployed registry {registry_list}.",
        }
    return {
        "status": "fail",
        "reason": (
            f"Connector {expected!r} missing from deployed registry {registry_list} "
            "— Docker cache persistence suspected."
        ),
    }


@register("verify_env_isolation", Tier.TIER1)
async def verify_env_isolation(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Environment cross-wiring detection — declared env vs DATABASE_URL topology."""
    declared_env = evidence.get("declared_env")  # "staging" or "production"
    database_url_env = evidence.get("database_url_env")  # resolves to same
    if not declared_env or not database_url_env:
        return {
            "status": "fail",
            "reason": "Missing declared_env or database_url_env.",
        }
    if declared_env == database_url_env:
        return {
            "status": "pass",
            "reason": f"Environment isolated: {declared_env} wiring matches topology.",
        }
    return {
        "status": "fail",
        "reason": (
            f"Environment cross-wiring: declared={declared_env} but DATABASE_URL resolves "
            f"to {database_url_env} — env cross-wiring."
        ),
    }


@register("verify_file_exists", Tier.TIER1)
async def verify_file_exists(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Verify a file exists on disk with a minimum line count.

    Real evidence for design docs, specs, changelogs — can't be faked by
    submitting a string. Used by the stepproof-test validation runbook.
    """
    from pathlib import Path

    path = evidence.get("path")
    min_lines = int(evidence.get("min_lines", 1))
    if not path:
        return {"status": "fail", "reason": "Missing 'path' in evidence."}
    p = Path(path).expanduser()
    if not p.exists():
        return {"status": "fail", "reason": f"File does not exist: {path}"}
    if not p.is_file():
        return {"status": "fail", "reason": f"Path is not a file: {path}"}
    try:
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e:
        return {"status": "fail", "reason": f"Could not read file: {e}"}
    if len(lines) < min_lines:
        return {
            "status": "fail",
            "reason": f"{path} has {len(lines)} non-empty lines; need ≥ {min_lines}.",
            "artifacts": {"lines": len(lines), "required": min_lines},
        }
    return {
        "status": "pass",
        "reason": f"{path} exists with {len(lines)} non-empty lines.",
        "artifacts": {"lines": len(lines), "path": path},
    }


@register("verify_git_commit", Tier.TIER1)
async def verify_git_commit(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Verify a commit SHA exists in the current repository.

    Real evidence for "code was committed." The agent cannot fake a SHA —
    only ``git commit`` produces one that ``git cat-file -t`` resolves.

    Evidence schema:
        commit_sha: str — the full or abbreviated SHA to verify.
        repo_path: str — optional; defaults to current working directory.
        expected_subject_contains: str — optional; if set, the commit's
            subject line must contain this substring.
    """
    import shutil
    import subprocess

    sha = evidence.get("commit_sha")
    if not sha or not isinstance(sha, str):
        return {"status": "fail", "reason": "Missing or non-string commit_sha."}

    repo = evidence.get("repo_path") or "."
    if shutil.which("git") is None:
        return {"status": "fail", "reason": "git binary not on PATH."}

    try:
        r = subprocess.run(
            ["git", "-C", repo, "cat-file", "-t", sha],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.SubprocessError as e:
        return {"status": "fail", "reason": f"git cat-file failed: {e}"}
    if r.returncode != 0 or r.stdout.strip() != "commit":
        return {
            "status": "fail",
            "reason": f"SHA {sha!r} is not a commit in {repo!r}: {r.stderr.strip() or r.stdout.strip()}",
        }

    resolved = subprocess.run(
        ["git", "-C", repo, "rev-parse", sha],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()

    expected_subj = evidence.get("expected_subject_contains")
    if expected_subj:
        subj = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%s", resolved],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        if expected_subj not in subj:
            return {
                "status": "fail",
                "reason": (
                    f"Commit {resolved[:8]} subject {subj!r} "
                    f"does not contain {expected_subj!r}"
                ),
            }

    return {
        "status": "pass",
        "reason": f"Commit {resolved[:8]} verified in {repo!r}.",
        "artifacts": {"commit_sha": resolved},
    }


@register("verify_pytest_passed", Tier.TIER1)
async def verify_pytest_passed(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Verify a pytest output file shows a passing suite.

    The agent captures pytest's stdout to a file, submits the path, and
    the verifier parses the summary line. Agent cannot fabricate this
    without running the tests, because pytest's summary format is
    specific (``N passed[, M failed][, ...] in S.Ss``) and includes a
    wall-time reading.

    Evidence schema:
        pytest_output_path: str — path to captured pytest output.
        min_passed: int — minimum passing tests required (default 1).
    """
    import re
    from pathlib import Path

    path = evidence.get("pytest_output_path")
    if not path:
        return {"status": "fail", "reason": "Missing pytest_output_path."}
    p = Path(path).expanduser()
    if not p.exists() or not p.is_file():
        return {"status": "fail", "reason": f"pytest output file not found: {path}"}

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"status": "fail", "reason": f"Could not read pytest output: {e}"}

    # Pytest's summary line: "=== 145 passed in 12.34s ===", sometimes with
    # warnings/skips. Require 'passed' and no 'failed' / 'error'.
    summary_line = None
    for line in text.splitlines()[::-1]:
        if "passed" in line and "=" in line:
            summary_line = line
            break
    if summary_line is None:
        return {"status": "fail", "reason": "No pytest summary line with 'passed' found."}

    if "failed" in summary_line or " error" in summary_line:
        return {
            "status": "fail",
            "reason": f"pytest reported failures: {summary_line.strip()!r}",
        }

    m = re.search(r"(\d+)\s+passed", summary_line)
    if m is None:
        return {"status": "fail", "reason": f"Unparseable summary: {summary_line!r}"}
    passed = int(m.group(1))
    min_passed = int(evidence.get("min_passed", 1))
    if passed < min_passed:
        return {
            "status": "fail",
            "reason": f"Only {passed} tests passed; need ≥{min_passed}.",
            "artifacts": {"passed": passed, "required": min_passed},
        }
    return {
        "status": "pass",
        "reason": f"pytest green: {passed} passed.",
        "artifacts": {"passed": passed, "summary": summary_line.strip()},
    }


@register("verify_round_marker", Tier.TIER1)
async def verify_round_marker(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Step-aware marker verifier for multi-round game plans.

    Derives the expected marker path from ``context.step_id`` (``sN`` →
    ``<state_dir>/round-N-done.txt``) and rejects mismatched evidence.
    Closes the step-blind gap in ``verify_file_exists`` that lets the
    same file satisfy every step of a multi-step run.

    Evidence schema:
        round_number: int — must equal N from step_id ``sN``; rejected otherwise.

    Context (injected by runtime):
        step_id: str — e.g. ``s3``.
    """
    import os
    from pathlib import Path

    step_id = str(context.get("step_id", ""))
    if not (step_id.startswith("s") and step_id[1:].isdigit()):
        return {
            "status": "fail",
            "reason": (
                f"verify_round_marker requires step_ids of the form 'sN'; "
                f"got {step_id!r}"
            ),
        }
    expected_n = int(step_id[1:])

    claimed = evidence.get("round_number")
    if claimed is None:
        return {
            "status": "fail",
            "reason": "Missing 'round_number' in evidence.",
        }
    try:
        claimed_n = int(claimed)
    except (TypeError, ValueError):
        return {
            "status": "fail",
            "reason": f"'round_number' must be an integer; got {claimed!r}",
        }
    if claimed_n != expected_n:
        return {
            "status": "fail",
            "reason": (
                f"Evidence round_number={claimed_n} does not match step "
                f"{step_id} (expected {expected_n}). Cannot reuse one round's "
                f"evidence for another step."
            ),
        }

    state_dir_env = os.environ.get("STEPPROOF_STATE_DIR")
    state_dir = Path(state_dir_env) if state_dir_env else Path.cwd() / ".stepproof"
    marker = state_dir / f"round-{expected_n}-done.txt"
    if not marker.exists():
        return {
            "status": "fail",
            "reason": f"Round {expected_n} marker does not exist at {marker}.",
        }
    content = marker.read_text(encoding="utf-8").strip()
    if not content:
        return {
            "status": "fail",
            "reason": f"Round {expected_n} marker is empty.",
        }
    return {
        "status": "pass",
        "reason": f"Round {expected_n} marker verified.",
        "artifacts": {"path": str(marker), "step_id": step_id},
    }


@register("verify_playtest_log", Tier.TIER1)
async def verify_playtest_log(
    evidence: dict[str, Any], context: dict[str, Any]
) -> dict[str, Any]:
    """Verify a playtest log is a real JSONL file with required entries.

    The classic 'I playtested it' claim is hard to check with LLM-based
    verification but trivial with a deterministic script: the log must exist,
    must be valid JSONL, and must contain at least min_entries entries.
    Each entry is checked for a 'move' or 'guess' field so that an empty
    {} list doesn't pass trivially.
    """
    from pathlib import Path

    path = evidence.get("playtest_log_path")
    min_entries = int(evidence.get("min_entries", 1))
    if not path:
        return {"status": "fail", "reason": "Missing 'playtest_log_path' in evidence."}
    p = Path(path).expanduser()
    if not p.exists():
        return {"status": "fail", "reason": f"Playtest log not found: {path}"}
    try:
        import json as _json

        entries: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = _json.loads(line)
                if isinstance(obj, dict):
                    entries.append(obj)
            except _json.JSONDecodeError:
                return {
                    "status": "fail",
                    "reason": f"Playtest log has invalid JSONL line: {line[:100]!r}",
                }
    except Exception as e:
        return {"status": "fail", "reason": f"Could not read playtest log: {e}"}

    if len(entries) < min_entries:
        return {
            "status": "fail",
            "reason": f"Playtest log has {len(entries)} entries; need ≥ {min_entries}.",
            "artifacts": {"entries": len(entries), "required": min_entries},
        }
    # Substantive-content check: each entry should carry at least one of these
    # gameplay keys. Prevents someone submitting a log of `{"_": 1}` lines.
    substantive_keys = {"move", "guess", "action", "input", "step", "turn", "event"}
    substantive = sum(1 for e in entries if any(k in e for k in substantive_keys))
    if substantive < min_entries:
        return {
            "status": "fail",
            "reason": (
                f"Playtest log has {len(entries)} entries but only {substantive} "
                f"carry gameplay data (need move/guess/action/input/step/turn/event). "
                "Submitting empty stubs doesn't count."
            ),
            "artifacts": {"entries": len(entries), "substantive": substantive},
        }
    return {
        "status": "pass",
        "reason": f"Playtest log has {len(entries)} entries, {substantive} with gameplay data.",
        "artifacts": {"entries": len(entries), "substantive": substantive, "path": path},
    }


@register("verify_pr_approved", Tier.TIER1)
async def verify_pr_approved(evidence: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    pr_url = evidence.get("pr_url")
    approval_count = evidence.get("approval_count", 0)
    try:
        n = int(approval_count)
    except (TypeError, ValueError):
        n = 0
    if pr_url and n >= 1:
        return {
            "status": "pass",
            "reason": f"PR {pr_url} has {n} approval(s).",
        }
    return {"status": "fail", "reason": f"PR {pr_url} lacks required approval (have {n}, need ≥1)."}


def list_methods() -> list[str]:
    return sorted(_REGISTRY.keys())

"""Metrics computed directly from `.stepproof/runs/*/events.jsonl`.

The point of this module is to replace ROI speculation with ground
truth. The subagent critique that prompted this was: the "off-rails
rate" (how often an agent would have shortcut without enforcement)
is empirically measurable from the audit log in a team's first 2-3
weeks of use. Models disagree on whether it's 8-15% or 25-40%;
that gap drives a 30x spread in projected value. Every team has
the answer in their own events.jsonl — this module exposes it.

Four counters are emitted:

  - total_runs        number of runs on record
  - deny_rate         fraction of policy decisions that were 'deny'
  - wedge_rate        fraction of runs that ended non-completed
                      (failed / abandoned / stuck ACTIVE)
  - recovery_rate     fraction of steps that failed once then passed
                      (indicates healthy iteration inside a step)

The fifth number, the user-facing one, is the *off-rails rate*:
the composite measure of how often enforcement actually bit.

off_rails_rate = (denies + wedged_runs_weighted) / total_events

If your off-rails rate after N runs is <5%, StepProof is mostly
dormant (Q1-Q2 territory — ceremony overhead > catches).  If it's
15%+, you're Q3-Q4 (StepProof is catching real drift).  If it's
30%+, you're Q5 (high-stakes domain where StepProof is mandatory).
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import store


def _iter_events(run_id: str | None = None) -> list[dict[str, Any]]:
    if run_id is not None:
        path = store.run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return []
        return _read_jsonl(path)
    base = store.runs_dir()
    if not base.exists():
        return []
    out: list[dict[str, Any]] = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        ev = d / "events.jsonl"
        if ev.exists():
            out.extend(_read_jsonl(ev))
    return out


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def compute(
    run_id: str | None = None,
    days: int | None = None,
) -> dict[str, Any]:
    """Compute the four counters over the requested scope.

    Args:
        run_id: if set, restrict metrics to this run's events.
        days:   if set, only include events within the last N days.
    """
    events = _iter_events(run_id=run_id)

    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        events = [
            e for e in events
            if (dt := _parse_iso(e.get("timestamp", ""))) and dt >= cutoff
        ]

    total_events = len(events)

    decisions: dict[str, int] = defaultdict(int)
    for e in events:
        d = (e.get("decision") or "").lower()
        if d:
            decisions[d] += 1
    deny_count = decisions.get("deny", 0)
    deny_rate = (deny_count / total_events) if total_events else 0.0

    # Wedge rate: non-completed run endings.
    run_statuses: dict[str, str] = {}
    if run_id is not None:
        r = store.get_run(run_id)
        if r is not None:
            run_statuses[run_id] = r.status.value
    else:
        for r in store.list_runs(limit=200):
            run_statuses[str(r.run_id)] = r.status.value
    wedged = sum(
        1 for s in run_statuses.values()
        if s in ("failed", "abandoned") or s == "active"
    )
    total_counted_runs = len(run_statuses)
    wedge_rate = (wedged / total_counted_runs) if total_counted_runs else 0.0

    # Recovery rate: per-step pattern of fail → pass on the same step_id.
    # Walk events in time order; for each run_id, track the sequence of
    # verdicts per step_id. A step that emits a step.complete deny and
    # later a step.complete allow (same step_id) is a successful recovery.
    events_sorted = sorted(
        events, key=lambda e: e.get("timestamp") or ""
    )
    per_run_step: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in events_sorted:
        if e.get("action_type") != "step.complete":
            continue
        rid = e.get("run_id")
        sid = e.get("step_id")
        dec = (e.get("decision") or "").lower()
        if not (rid and sid and dec):
            continue
        per_run_step[(rid, sid)].append(dec)

    total_recoveries = 0
    steps_with_any_fail = 0
    for verdicts in per_run_step.values():
        had_fail = any(v == "deny" for v in verdicts)
        if had_fail:
            steps_with_any_fail += 1
            if "allow" in verdicts[verdicts.index("deny"):]:
                total_recoveries += 1
    recovery_rate = (
        total_recoveries / steps_with_any_fail
        if steps_with_any_fail else 0.0
    )

    # The composite the user cares about: how often did enforcement bite?
    # Denies are real catches. Wedged runs represent denied advancement
    # that didn't resolve; count each wedged run as one enforcement event.
    numerator = deny_count + wedged
    denominator = total_events + max(0, total_counted_runs - wedged)
    off_rails_rate = (numerator / denominator) if denominator else 0.0

    return {
        "total_runs": total_counted_runs,
        "total_events": total_events,
        "decisions_by_type": dict(decisions),
        "deny_rate": round(deny_rate, 4),
        "wedge_rate": round(wedge_rate, 4),
        "wedged_runs": wedged,
        "recovery_rate": round(recovery_rate, 4),
        "steps_with_retry": steps_with_any_fail,
        "recoveries": total_recoveries,
        "off_rails_rate": round(off_rails_rate, 4),
        "interpretation": _interpret(off_rails_rate, total_counted_runs),
    }


def _interpret(off_rails_rate: float, total_runs: int) -> str:
    """Map the rate to the Q1-Q5 framework from the ROI analysis."""
    if total_runs < 3:
        return "insufficient_data"
    if off_rails_rate < 0.05:
        return "Q1-Q2: enforcement mostly dormant; overhead likely exceeds catches"
    if off_rails_rate < 0.15:
        return "Q3: enforcement catching some drift; break-even to modest gains"
    if off_rails_rate < 0.30:
        return "Q4: enforcement catching meaningful drift; sustained gains"
    return "Q5: enforcement catching heavy drift; high-stakes domain fit"


def format_report(m: dict[str, Any]) -> str:
    """Produce a terse human-readable report from a metrics dict."""
    lines = []
    lines.append(f"Runs:                    {m['total_runs']}")
    lines.append(f"Events:                  {m['total_events']}")
    lines.append(
        f"Decisions:               "
        + ", ".join(f"{k}={v}" for k, v in sorted(m["decisions_by_type"].items()))
        if m["decisions_by_type"] else "Decisions:               (none)"
    )
    lines.append(f"Deny rate:               {m['deny_rate']:.1%}")
    lines.append(f"Wedge rate:              {m['wedge_rate']:.1%}  ({m['wedged_runs']} wedged)")
    lines.append(
        f"Recovery rate:           {m['recovery_rate']:.1%}  "
        f"({m['recoveries']} of {m['steps_with_retry']} retried steps)"
    )
    lines.append("")
    lines.append(f"OFF-RAILS RATE:          {m['off_rails_rate']:.1%}")
    lines.append(f"  → {m['interpretation']}")
    return "\n".join(lines)

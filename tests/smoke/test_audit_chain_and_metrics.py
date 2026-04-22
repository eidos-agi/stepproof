"""Unit tests for the hash-chained audit log and the metrics module.

These exercise `stepproof_runtime.store.append_event` (which now chains
each record with prev_hash + hash), `store.verify_audit_chain`, and the
`stepproof_runtime.metrics.compute` function.

The two invariants under test:

1. Every event appended to events.jsonl carries a SHA-256 `hash` plus
   the `prev_hash` of the previous record in that stream. Mutating any
   historical record must cause `verify_audit_chain` to fail.
2. The four counters emitted by `metrics.compute` reflect real events:
   deny_rate from Decision.DENY, recovery_rate from a step that denied
   then later allowed, off_rails_rate composite.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from stepproof_runtime import metrics, store
from stepproof_runtime.models import AuditEvent, Decision


@pytest.fixture
def isolated_state(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="sp-audit-chain-")
    monkeypatch.setenv("STEPPROOF_STATE_DIR", str(Path(tmp) / ".stepproof"))
    yield Path(tmp) / ".stepproof"


def _make_event(run_id, action: str, decision: str, step_id: str) -> AuditEvent:
    return AuditEvent(
        event_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        actor_type="agent",
        actor_id="test",
        human_owner_id="test",
        run_id=run_id,
        step_id=step_id,
        action_type=action,
        tool="",
        decision=Decision(decision),
        policy_id="test",
        reason="",
        compliance_tags=[],
        payload_hash="",
    )


def test_audit_chain_valid_on_append(isolated_state):
    rid = uuid4()
    for action, dec in [("run.start", "allow"), ("step.complete", "allow")]:
        store.append_event(_make_event(rid, action, dec, "s1"))

    ok, n, reason = store.verify_audit_chain(store.global_events_path())
    assert ok, reason
    assert n == 2

    ok, n, reason = store.verify_audit_chain(
        store.run_dir(rid) / "events.jsonl"
    )
    assert ok, reason
    assert n == 2


def test_audit_chain_detects_tamper(isolated_state):
    rid = uuid4()
    for _ in range(4):
        store.append_event(_make_event(rid, "step.complete", "allow", "s1"))

    path = store.global_events_path()
    lines = path.read_text().splitlines()
    tampered = json.loads(lines[2])
    tampered["reason"] = "rewritten after the fact"
    # Keep the tampered line's claimed `hash` — so the recomputed hash
    # will differ and verify_audit_chain must flag it.
    lines[2] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")

    ok, n, reason = store.verify_audit_chain(path)
    assert not ok
    assert reason is not None
    assert "line 3" in reason


def test_audit_chain_each_record_links_to_previous(isolated_state):
    rid = uuid4()
    for _ in range(3):
        store.append_event(_make_event(rid, "step.complete", "allow", "s1"))

    lines = store.global_events_path().read_text().splitlines()
    recs = [json.loads(l) for l in lines]
    assert recs[0]["prev_hash"] is None
    assert recs[1]["prev_hash"] == recs[0]["hash"]
    assert recs[2]["prev_hash"] == recs[1]["hash"]


def test_metrics_deny_and_recovery(isolated_state):
    rid = uuid4()
    # s1 fails once then passes — a recovery.
    store.append_event(_make_event(rid, "run.start", "allow", "s1"))
    store.append_event(_make_event(rid, "step.complete", "deny", "s1"))
    store.append_event(_make_event(rid, "step.complete", "allow", "s1"))
    # s2 passes clean.
    store.append_event(_make_event(rid, "step.complete", "allow", "s2"))

    m = metrics.compute()
    assert m["total_events"] == 4
    assert m["decisions_by_type"] == {"allow": 3, "deny": 1}
    assert m["deny_rate"] == pytest.approx(0.25, rel=1e-3)
    assert m["steps_with_retry"] == 1
    assert m["recoveries"] == 1
    assert m["recovery_rate"] == pytest.approx(1.0)


def test_metrics_scoped_to_run(isolated_state):
    rid_a = uuid4()
    rid_b = uuid4()
    store.append_event(_make_event(rid_a, "step.complete", "deny", "s1"))
    store.append_event(_make_event(rid_b, "step.complete", "allow", "s1"))

    m_a = metrics.compute(run_id=str(rid_a))
    assert m_a["total_events"] == 1
    assert m_a["decisions_by_type"] == {"deny": 1}

    m_b = metrics.compute(run_id=str(rid_b))
    assert m_b["total_events"] == 1
    assert m_b["decisions_by_type"] == {"allow": 1}


def test_metrics_empty_state(isolated_state):
    m = metrics.compute()
    assert m["total_events"] == 0
    assert m["off_rails_rate"] == 0.0
    assert m["interpretation"] == "insufficient_data"

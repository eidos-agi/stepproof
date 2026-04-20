"""YAML policy engine + ring classifier.

Deterministic evaluation per ADR-0001: no LLM in this path.
Ring classification per ADR-0002: unclassified → Ring 3 (conservative).
"""

from __future__ import annotations

from typing import Any

from .models import Decision, PolicyDecision, PolicyInput, Ring

# Minimal action→ring map. The real taxonomy lives in a RING_TAXONOMY.md followup.
# Unlisted actions default to Ring 3.
DEFAULT_RING_MAP: dict[str, Ring] = {
    # Ring 0 — sandbox / read-only
    "tool.read": Ring.SANDBOX,
    "tool.glob": Ring.SANDBOX,
    "tool.grep": Ring.SANDBOX,
    "tool.ls": Ring.SANDBOX,
    # Ring 1 — reversible, non-prod
    "filesystem.write": Ring.REVERSIBLE_NONPROD,
    # Ring 2 — non-reversible, non-prod
    "database.write": Ring.NONREVERSIBLE_NONPROD,
    # Ring 3 — production
    "deploy.production": Ring.PRODUCTION,
    "deploy.risky": Ring.PRODUCTION,
    "secrets.rotate": Ring.PRODUCTION,
}


def classify_ring(action_type: str, target_env: str | None) -> Ring:
    """Map an action to its execution ring. Unclassified → Ring 3."""
    base = DEFAULT_RING_MAP.get(action_type, Ring.PRODUCTION)
    # Production-env promotes rings upward.
    if target_env == "production" and base.value < Ring.PRODUCTION.value:
        return Ring.PRODUCTION
    return base


def _matches(condition: dict[str, Any], event: PolicyInput) -> bool:
    """Evaluate a single condition against the event. Conservative: unknown operators fail-safe."""
    field = condition.get("field", "")
    operator = condition.get("operator", "")
    value = condition.get("value", "")
    haystack = getattr(event, field, "") if hasattr(event, field) else ""
    if haystack is None:
        haystack = ""
    haystack = str(haystack)

    if operator == "contains_any":
        needles = [n.strip() for n in str(value).split(",") if n.strip()]
        return any(n.lower() in haystack.lower() for n in needles)
    if operator == "equals":
        return haystack == str(value)
    if operator == "in":
        choices = [c.strip() for c in str(value).split(",") if c.strip()]
        return haystack in choices
    if operator == "gte":
        try:
            return float(haystack) >= float(value)
        except (TypeError, ValueError):
            return False
    return False


class PolicyEngine:
    """Evaluates a policy document (list of rules + defaults) against a PolicyInput."""

    def __init__(self, rules: list[dict[str, Any]] | None = None, defaults: dict[str, Any] | None = None):
        self.rules = rules or []
        self.defaults = defaults or {"action": "allow"}

    def evaluate(self, event: PolicyInput, *, shadow_override: bool = False) -> PolicyDecision:
        # Sort by priority descending (100 highest).
        ordered = sorted(self.rules, key=lambda r: -int(r.get("priority", 0)))
        for rule in ordered:
            condition = rule.get("condition", {})
            if not _matches(condition, event):
                continue
            action = rule.get("action", "allow")
            decision = Decision(action) if action in Decision._value2member_map_ else Decision.ALLOW
            return PolicyDecision(
                decision=decision,
                reason=rule.get("message", ""),
                policy_id=rule.get("name", ""),
                priority=int(rule.get("priority", 0)),
                suggested_tool=rule.get("suggested_tool"),
                shadow=shadow_override,
            )

        default_action = self.defaults.get("action", "allow")
        return PolicyDecision(
            decision=Decision(default_action) if default_action in Decision._value2member_map_ else Decision.ALLOW,
            reason="default",
            policy_id="default",
            shadow=shadow_override,
        )


# --- Ring-level structural gates, applied BEFORE policy rules. ---


def structural_gate(event: PolicyInput, *, run_active: bool, prior_verified: bool) -> PolicyDecision | None:
    """Enforce ring-based preconditions per ADR-0002.

    Returns a PolicyDecision if the action is blocked structurally; None if it passes to rules.
    """
    ring = event.ring or classify_ring(event.action_type, event.target_env)

    if ring == Ring.SANDBOX:
        return None  # Always allowed

    if not run_active:
        return PolicyDecision(
            decision=Decision.DENY,
            reason=f"Ring {ring.value} action requires an active runbook. No run is active.",
            policy_id="structural.ring_requires_run",
            priority=1000,
            suggested_tool="stepproof run start <template_id>",
        )

    if ring in (Ring.NONREVERSIBLE_NONPROD, Ring.PRODUCTION) and not prior_verified:
        return PolicyDecision(
            decision=Decision.DENY,
            reason=(
                f"Ring {ring.value} action blocked: prior required steps are not verified. "
                "Complete the current step and wait for verifier pass before proceeding."
            ),
            policy_id="structural.prior_steps_unverified",
            priority=1000,
        )

    return None

"""Plan validation — structural checks for agent-declared plans.

Per docs/KEEP_ME_HONEST.md §Plan Validation. A plan is accepted only if every
step satisfies: verifiability, evidence specificity, ring coherence, allowed-
tools sanity, no verifier bypass. Guardrail-compliance is a follow-up.

Deterministic per ADR-0001 — no LLM in this path.
"""

from __future__ import annotations

from .models import PlanDeclaration, PlanValidationError, Ring, StepTemplate
from .verifiers import list_methods


# Ring-coherence rules: if a step's allowed_tools include any of these shell-
# like tools, the step must be at least this ring.
_TOOL_MIN_RING: dict[str, Ring] = {
    "Bash": Ring.NONREVERSIBLE_NONPROD,
    "psql": Ring.NONREVERSIBLE_NONPROD,
    "pg_dump": Ring.NONREVERSIBLE_NONPROD,
    "pg_restore": Ring.NONREVERSIBLE_NONPROD,
    "deploy_cli": Ring.PRODUCTION,
    "cerebro_migrate_production": Ring.PRODUCTION,
    "railguey_rollback": Ring.PRODUCTION,
}


def _step_ring(step: StepTemplate, environment: str) -> Ring:
    """Best-effort ring inference for a declared step.

    The agent doesn't declare a ring directly on StepTemplate (to keep the
    schema simple). We infer from allowed_tools and environment, matching
    policy.classify_ring semantics.
    """
    base = Ring.REVERSIBLE_NONPROD
    for tool in step.allowed_tools:
        if tool in _TOOL_MIN_RING:
            r = _TOOL_MIN_RING[tool]
            if r.value > base.value:
                base = r
    if environment == "production" and base.value < Ring.PRODUCTION.value:
        # Steps targeting production get promoted.
        base = Ring.PRODUCTION
    return base


def validate_plan(plan: PlanDeclaration) -> list[PlanValidationError]:
    """Return a list of validation errors. Empty list = valid."""
    errors: list[PlanValidationError] = []

    if not plan.intent.strip():
        errors.append(
            PlanValidationError(
                field="intent",
                code="intent.empty",
                message="Plan must declare a non-empty intent.",
            )
        )

    if not plan.steps:
        errors.append(
            PlanValidationError(
                field="steps",
                code="steps.empty",
                message="Plan must declare at least one step.",
            )
        )
        return errors

    if plan.environment not in {"staging", "production", "development", "test", "local"}:
        errors.append(
            PlanValidationError(
                field="environment",
                code="environment.unknown",
                message=f"Environment {plan.environment!r} is not recognized.",
            )
        )

    registered = set(list_methods())
    step_ids_seen: set[str] = set()

    for step in plan.steps:
        # No duplicate step_ids.
        if step.step_id in step_ids_seen:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="step_id",
                    code="step_id.duplicate",
                    message=f"Duplicate step_id {step.step_id!r}.",
                )
            )
        step_ids_seen.add(step.step_id)

        # Evidence contract (GUARD-002): required_evidence must not be empty.
        if not step.required_evidence:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="required_evidence",
                    code="required_evidence.empty",
                    message=(
                        f"Step {step.step_id!r} declares no required_evidence. "
                        "Free-text 'done' is not evidence (GUARD-002)."
                    ),
                )
            )

        # Verifiability: verification_method must reference a registered verifier.
        if step.verification_method not in registered:
            errors.append(
                PlanValidationError(
                    step_id=step.step_id,
                    field="verification_method",
                    code="verification_method.unknown",
                    message=(
                        f"Step {step.step_id!r} references unknown verification_method "
                        f"{step.verification_method!r}. Registered methods: "
                        f"{sorted(registered)}."
                    ),
                )
            )

        # Ring coherence: allowed_tools imply a minimum ring; ensure the step
        # doesn't sneak Ring 3 tools into a low-risk plan without the right
        # evidence contract (at least migration/deploy-class evidence).
        inferred_ring = _step_ring(step, plan.environment)
        if inferred_ring == Ring.PRODUCTION:
            risky_evidence = {"deploy_id", "migration_name", "rollback_deploy_id", "secret_id"}
            if not any(k in step.required_evidence for k in risky_evidence):
                errors.append(
                    PlanValidationError(
                        step_id=step.step_id,
                        field="required_evidence",
                        code="ring3.insufficient_evidence",
                        message=(
                            f"Step {step.step_id!r} is Ring 3 (production-facing) but "
                            f"required_evidence doesn't include any of {sorted(risky_evidence)}. "
                            "Ring 3 steps must be verifiable against concrete IDs."
                        ),
                    )
                )

    return errors

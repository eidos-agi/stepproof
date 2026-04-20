"""Pydantic models — the shapes that cross the API boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Ring(int, Enum):
    """Execution ring per ADR-0002. Lower = safer, higher = higher blast radius."""

    SANDBOX = 0
    REVERSIBLE_NONPROD = 1
    NONREVERSIBLE_NONPROD = 2
    PRODUCTION = 3


class Tier(str, Enum):
    TIER1 = "tier1"
    TIER2 = "tier2"
    TIER3 = "tier3"


class OnFail(str, Enum):
    BLOCK = "block"
    RETRY = "retry"
    ESCALATE_HUMAN = "escalate_human"


class StepTemplate(BaseModel):
    step_id: str
    description: str
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    verification_method: str
    verification_tier: Tier = Tier.TIER1
    timeout_seconds: int = 600
    on_fail: OnFail = OnFail.BLOCK
    on_fail_max_retries: int = 0


class RunbookTemplate(BaseModel):
    template_id: str
    version: str = "1.0.0"
    name: str
    description: str = ""
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    allowed_environments: list[str] = Field(default_factory=lambda: ["staging", "production"])
    requires_human_signoff: bool = False
    shadow: bool = False
    source: Literal["template", "declared"] = "template"
    steps: list[StepTemplate]


class PlanDeclaration(BaseModel):
    """An agent-declared plan submitted via `keep_me_honest`.

    Per docs/KEEP_ME_HONEST.md, the agent authors its own runbook inline.
    The plan is validated structurally at submission, then becomes the
    agent's contract for the session.
    """

    intent: str = Field(..., description="Plain-English goal; logged in the audit trail")
    steps: list[StepTemplate]
    environment: str = "staging"
    owner_id: str = "unknown"
    agent_id: str = "unknown"
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"


class PlanValidationError(BaseModel):
    step_id: str | None = None
    field: str | None = None
    code: str
    message: str


class RunStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    AWAITING_VERIFICATION = "awaiting_verification"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"


class VerificationResult(BaseModel):
    status: VerificationStatus
    confidence: float = 1.0
    reason: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    verifier_id: str = ""
    tier_used: Tier = Tier.TIER1
    latency_ms: int = 0


class WorkflowRun(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    template_id: str
    template_version: str
    owner_id: str
    agent_id: str = "unknown"
    environment: str
    current_step: str | None = None
    status: RunStatus = RunStatus.ACTIVE
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


class StepRun(BaseModel):
    run_id: UUID
    step_id: str
    status: StepStatus = StepStatus.PENDING
    evidence: dict[str, Any] = Field(default_factory=dict)
    verification_result: VerificationResult | None = None
    attempts: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    TRANSFORM = "transform"
    REQUIRE_APPROVAL = "require_approval"
    AUDIT = "audit"


class PolicyInput(BaseModel):
    """Normalized action event — the `input` in OPA terms (ADR references PRIOR_ART_DEEPER)."""

    actor_type: str = "worker_agent"
    actor_id: str = "unknown"
    human_owner_id: str = "unknown"
    tool: str = ""
    action_type: str = ""
    target_env: str | None = None
    payload_summary: str = ""
    message: str = ""  # Content-pattern matching field (ADR-style)
    run_id: UUID | None = None
    step_id: str | None = None
    ring: Ring | None = None


class PolicyDecision(BaseModel):
    decision: Decision
    reason: str = ""
    policy_id: str = ""
    priority: int = 0
    suggested_tool: str | None = None
    transformed_payload: dict[str, Any] | None = None
    approval_id: str | None = None
    trust_signals: dict[str, Any] = Field(default_factory=dict)
    shadow: bool = False  # If true, logged but not enforced
    skipped: bool = False  # Control-plane degraded-path marker


class LivenessStatus(str, Enum):
    UNKNOWN = "unknown"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"


class Heartbeat(BaseModel):
    run_id: UUID
    ttl_seconds: int = 300
    registered_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime
    status: LivenessStatus = LivenessStatus.ACTIVE


class AuditEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=utcnow)
    actor_type: str
    actor_id: str
    human_owner_id: str
    run_id: UUID | None = None
    step_id: str | None = None
    action_type: str
    tool: str | None = None
    decision: Decision | None = None
    policy_id: str = ""
    reason: str = ""
    compliance_tags: list[str] = Field(default_factory=list)
    payload_hash: str = ""

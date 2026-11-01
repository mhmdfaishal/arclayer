from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"

__all__ = [
    "SCHEMA_VERSION", "FaultClass", "OrchestrationPattern", "LabelSource", "Action", "Precondition",
    "Terminal", "PolicyKind", "FaultEventIn", "CandidateSpec", "ScoreOut", "GateRejectionOut",
    "RecoveryCommandOut", "ExecutionResultIn", "OutcomeAckOut", "FeatureSpecIn", "RewardWeightsIn",
    "BudgetCapsIn", "CreatePolicyIn", "PolicyOut", "PolicySnapshotOut", "VerificationOut",
    "IncidentOut", "OracleIn", "CandidateEnabledIn",
]


class FaultClass(StrEnum):
    TOOL_FAILURE = "tool_failure"
    TIMEOUT = "timeout"
    TOOL_OUTPUT_UNUSED = "tool_output_unused"
    HANDOFF_INCOMPLETE = "handoff_incomplete"
    PLAN_ERROR = "plan_error"
    INSUFFICIENT_VERIFICATION = "insufficient_verification"


class OrchestrationPattern(StrEnum):
    CENTRALIZED = "centralized"
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    DECENTRALIZED = "decentralized"


class LabelSource(StrEnum):
    DETERMINISTIC = "deterministic"
    INJECTOR = "injector"
    ATTRIBUTION = "attribution"


class Action(StrEnum):
    EXECUTE = "execute"
    SAFE_STOP = "safe_stop"
    ESCALATE = "escalate"


class Precondition(StrEnum):
    STEP_REPEATABLE = "STEP_REPEATABLE"
    TOOL_STATUS_AVAILABLE = "TOOL_STATUS_AVAILABLE"
    ORCHESTRATOR_MESSAGE_ACCESS = "ORCHESTRATOR_MESSAGE_ACCESS"
    STATE_SUMMARY_AVAILABLE = "STATE_SUMMARY_AVAILABLE"
    EVIDENCE_ARTIFACT_AVAILABLE = "EVIDENCE_ARTIFACT_AVAILABLE"
    CHECKPOINT_AVAILABLE = "CHECKPOINT_AVAILABLE"


class Terminal(StrEnum):
    TASK_COMPLETED = "task_completed"
    NEW_INCIDENT = "new_incident"
    BUDGET_EXHAUSTED = "budget_exhausted"
    EXECUTOR_ERROR = "executor_error"


class PolicyKind(StrEnum):
    B0 = "B0"
    B1 = "B1"
    B2 = "B2"
    B3 = "B3"
    B4 = "B4"
    P = "P"
    P_D = "P_D"
    P_F = "P_F"


class _Strict(BaseModel):
    # extra="forbid": adaptor tidak boleh menyelipkan field internal framework,
    # karena itu akan melanggar klaim framework-agnostic.
    model_config = ConfigDict(extra="forbid", frozen=True)


class FaultEventIn(_Strict):
    """Informasi minimum dari adaptor (Tabel 4 usulan)."""

    schema_version: Literal["1.0"] = "1.0"
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    step_index: int = Field(ge=0)
    step_total_estimate: int | None = Field(default=None, ge=0)
    occurred_at: datetime
    active_agent: str
    agent_role: str
    orchestration: OrchestrationPattern
    fault_class: FaultClass | None
    fault_confidence: float | None = Field(default=None, ge=0, le=1)
    label_source: LabelSource
    fault_description: str = Field(max_length=4000)
    last_messages_summary: str = Field(default="", max_length=4000)
    checkpoint_id: str | None = None
    checkpoint_restorable: bool = False
    step_repeatable: bool = True
    orchestrator_accessible: bool = False
    available_artifacts: list[str] = Field(default_factory=list)
    tool_name: str | None = None
    tool_error_code: str | None = None
    tool_duration_ms: int | None = Field(default=None, ge=0)
    budget_remaining_cost: float = Field(ge=0)
    budget_remaining_tokens: int | None = Field(default=None, ge=0)
    time_remaining_ms: int = Field(ge=0)
    prior_incidents_in_task: int = Field(ge=0)
    host_id: str
    policy_instance_id: str
    host_capabilities: list[str]


class CandidateSpec(_Strict):
    candidate_id: str = Field(min_length=1)
    version: str
    description: str
    capabilities: list[str]
    supported_classes: list[FaultClass] | Literal["*"]
    required_preconditions: list[Precondition] = Field(default_factory=list)
    optional_preconditions: list[Precondition] = Field(default_factory=list)
    required_host_capabilities: list[str] = Field(default_factory=list)
    max_cost: float = Field(gt=0)
    max_latency_ms: int = Field(gt=0)
    permissions: list[str]
    verifier_id: str
    enabled: bool = True


class CandidateEnabledIn(_Strict):
    enabled: bool


class ScoreOut(_Strict):
    candidate_id: str
    estimate: float
    bonus: float
    score: float


class GateRejectionOut(_Strict):
    candidate_id: str
    code: str


class RecoveryCommandOut(_Strict):
    incident_id: str
    action: Action
    candidate_id: str | None
    parameters: dict[str, Any]
    verification_conditions: list[str]
    scores: list[ScoreOut]
    excluded: list[GateRejectionOut]
    reason: str
    deadline_ms: int


class ExecutionResultIn(_Strict):
    incident_id: str
    candidate_id: str
    terminal: Terminal
    final_answer: str | None = None
    cost_used: float = Field(ge=0)
    tokens_used: int = Field(ge=0)
    # Diukur di sisi host: control plane tidak melihat durasi eksekusi kandidat.
    latency_ms: int = Field(ge=0)
    actions_performed: list[str] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)


class OutcomeAckOut(_Strict):
    incident_id: str
    status: Literal["recovered", "failed", "escalate"]
    reward: float
    policy_updated: bool


class FeatureSpecIn(_Strict):
    step_cap: int = Field(gt=0)
    budget_task_cap: float = Field(gt=0)
    n_max: int = Field(gt=0)


class RewardWeightsIn(_Strict):
    s: float = 1.0
    c: float = 0.2
    l: float = 0.1  # noqa: E741
    v: float = 1.0


class BudgetCapsIn(_Strict):
    incident_cost_cap: float = Field(gt=0)
    incident_latency_cap_ms: int = Field(gt=0)
    task_cost_cap: float = Field(gt=0)


class CreatePolicyIn(_Strict):
    kind: PolicyKind
    seed: int
    alpha: float = Field(default=0.675, ge=0)
    lam: float = Field(default=0.45, gt=0)
    feature_spec: FeatureSpecIn
    allowed_permissions: list[str]
    n_max: int = Field(gt=0)
    reward_weights: RewardWeightsIn = RewardWeightsIn()
    caps: BudgetCapsIn
    strict_sequential: bool = True
    retry_candidate_id: str = "h1_retry"
    static_map: dict[FaultClass, list[str]] = Field(default_factory=dict)
    static_default: list[str] = Field(default_factory=lambda: ["h1_retry"])
    policy_id: str | None = None
    init_state: dict[str, Any] | None = None
    experiment_id: str | None = None


class PolicyOut(_Strict):
    policy_id: str
    kind: PolicyKind
    seed: int
    alpha: float
    lam: float
    variant: str
    feature_hash: str
    embedding_model_id: str
    candidate_ids: list[str]
    frozen: bool
    strict_sequential: bool
    pending_incident_id: str | None
    experiment_id: str | None
    n_updates: dict[str, int]


class PolicySnapshotOut(_Strict):
    policy_id: str
    kind: PolicyKind
    feature_hash: str
    frozen: bool
    selector_state: dict[str, Any] | None


class VerificationOut(_Strict):
    S: int
    C: float
    L: float
    V: int


class IncidentOut(_Strict):
    incident_id: str
    policy_id: str
    task_id: str
    status: str
    action: Action | None
    chosen: str | None
    eligible: list[str]
    reward: float | None
    verification: VerificationOut | None


class OracleIn(_Strict):
    answer: str

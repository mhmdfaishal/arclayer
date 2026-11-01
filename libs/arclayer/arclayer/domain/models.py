"""Value object domain. Murni Python (tanpa Pydantic/SQLAlchemy) agar layer domain
tidak bergantung pada framework. Validasi skema masukan ada di layer interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from arclayer.domain.enums import (
    Action,
    FaultClass,
    LabelSource,
    OrchestrationPattern,
    Precondition,
    RejectionCode,
    Terminal,
)


@dataclass(frozen=True)
class FaultEvent:
    """Informasi minimum dari adaptor (Tabel 4 usulan).

    Tambahan terhadap plan: `step_repeatable` dan `orchestrator_accessible`,
    dibutuhkan untuk mengevaluasi prasyarat STEP_REPEATABLE dan
    ORCHESTRATOR_MESSAGE_ACCESS tanpa melihat objek internal host.
    """

    run_id: str
    task_id: str
    step_index: int
    step_total_estimate: int | None
    occurred_at: datetime
    active_agent: str
    agent_role: str
    orchestration: OrchestrationPattern
    fault_class: FaultClass | None
    fault_confidence: float | None
    label_source: LabelSource
    fault_description: str
    last_messages_summary: str
    checkpoint_id: str | None
    checkpoint_restorable: bool
    step_repeatable: bool
    orchestrator_accessible: bool
    available_artifacts: tuple[str, ...]
    tool_name: str | None
    tool_error_code: str | None
    tool_duration_ms: int | None
    budget_remaining_cost: float
    budget_remaining_tokens: int | None
    time_remaining_ms: int
    prior_incidents_in_task: int
    host_id: str
    policy_instance_id: str
    host_capabilities: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    """Kandidat agen pemulihan terdaftar (Tabel 6). Fungsi eksekusi sengaja tidak
    ada di sini: eksekusi milik host, control plane hanya memegang metadata."""

    candidate_id: str
    version: str
    description: str
    capabilities: tuple[str, ...]
    supported_classes: tuple[FaultClass, ...] | None  # None = semua kelas ("*")
    required_preconditions: tuple[Precondition, ...]
    optional_preconditions: tuple[Precondition, ...]
    required_host_capabilities: tuple[str, ...]
    max_cost: float
    max_latency_ms: int
    permissions: tuple[str, ...]
    verifier_id: str
    enabled: bool = True


@dataclass(frozen=True)
class GateRejection:
    candidate_id: str
    code: RejectionCode


@dataclass(frozen=True)
class ArmFeatures:
    """Fitur satu kandidat layak pada satu insiden. `cosine` disimpan terpisah
    (mentah, -1..1) karena dipakai langsung oleh baseline B4."""

    candidate_id: str
    x: tuple[float, ...]
    cosine: float


@dataclass(frozen=True)
class ScoreBreakdown:
    candidate_id: str
    estimate: float
    bonus: float
    score: float


@dataclass(frozen=True)
class Selection:
    candidate_id: str | None
    scores: tuple[ScoreBreakdown, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class RecoveryCommand:
    incident_id: str
    action: Action
    candidate_id: str | None
    parameters: dict[str, Any]
    verification_conditions: tuple[str, ...]
    scores: tuple[ScoreBreakdown, ...]
    excluded: tuple[GateRejection, ...]
    reason: str
    deadline_ms: int


@dataclass(frozen=True)
class ExecutionResult:
    incident_id: str
    candidate_id: str
    terminal: Terminal
    final_answer: str | None
    cost_used: float
    tokens_used: int
    latency_ms: int
    actions_performed: tuple[str, ...]
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Verification:
    S: int
    C: float
    L: float
    V: int
    details: dict[str, Any]


@dataclass(frozen=True)
class BudgetCaps:
    """Batas normalisasi C_t dan L_t (Persamaan 6) serta batas anggaran tugas."""

    incident_cost_cap: float
    incident_latency_cap_ms: int
    task_cost_cap: float


@dataclass(frozen=True)
class OutcomeAck:
    incident_id: str
    status: str
    reward: float
    policy_updated: bool

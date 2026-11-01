"""Entity domain (punya identitas dan siklus hidup)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from arclayer.domain.enums import FaultClass, FeatureVariant, IncidentStatus, PolicyKind
from arclayer.domain.features import FeatureSpec
from arclayer.domain.gate import GateConfig
from arclayer.domain.models import (
    ArmFeatures,
    BudgetCaps,
    Candidate,
    ExecutionResult,
    FaultEvent,
    GateRejection,
    OutcomeAck,
    RecoveryCommand,
    Verification,
)
from arclayer.domain.reward import RewardWeights
from arclayer.domain.state_machine import ensure_transition


@dataclass
class PolicyInstance:
    """Satu instance kebijakan = satu (kondisi, seed) pada eksperimen.

    `candidates` adalah snapshot registri saat instance dibuat, sehingga perubahan
    registri setelahnya tidak memengaruhi eksperimen yang sedang berjalan.
    """

    policy_id: str
    kind: PolicyKind
    seed: int
    alpha: float
    lam: float
    variant: FeatureVariant
    feature_spec: FeatureSpec
    feature_hash: str
    embedding_model_id: str
    candidates: tuple[Candidate, ...]
    gate_config: GateConfig
    reward_weights: RewardWeights
    caps: BudgetCaps
    strict_sequential: bool
    frozen: bool
    retry_candidate_id: str
    static_map: dict[FaultClass, tuple[str, ...]]
    static_default: tuple[str, ...]
    selector_state: dict[str, Any] | None
    rng_state: dict[str, Any]
    created_at: datetime
    experiment_id: str | None = None
    pending_incident_id: str | None = None

    def candidate(self, candidate_id: str) -> Candidate:
        for c in self.candidates:
            if c.candidate_id == candidate_id:
                return c
        raise KeyError(candidate_id)


@dataclass
class Incident:
    incident_id: str
    policy_id: str
    event: FaultEvent  # sudah diredaksi
    status: IncidentStatus
    received_at: datetime
    arms: tuple[ArmFeatures, ...] = ()
    rejections: tuple[GateRejection, ...] = ()
    command: RecoveryCommand | None = None
    decided_at: datetime | None = None
    result: ExecutionResult | None = None
    verification: Verification | None = None
    reward: float | None = None
    policy_updated: bool = False
    idempotency_key: str | None = None
    result_fingerprint: str | None = None
    ack: OutcomeAck | None = None
    result_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def transition(self, dst: IncidentStatus) -> None:
        ensure_transition(self.status, dst)
        self.status = dst

    def arm(self, candidate_id: str) -> ArmFeatures:
        for a in self.arms:
            if a.candidate_id == candidate_id:
                return a
        raise KeyError(candidate_id)

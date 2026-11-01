"""Penerjemah antara kontrak publik (arclayer.contracts, Pydantic) dan model domain.
Satu-satunya tempat yang mengenal kedua sisi; dipakai interface HTTP dan in-process."""

from __future__ import annotations

from typing import Any

import arclayer.contracts as C
from arclayer.usecases.policies import CreatePolicyCommand
from arclayer.domain import enums as D
from arclayer.domain.entities import Incident, PolicyInstance
from arclayer.domain.features import FeatureSpec
from arclayer.domain.gate import GateConfig
from arclayer.domain.models import (
    BudgetCaps,
    Candidate,
    ExecutionResult,
    FaultEvent,
    OutcomeAck,
    RecoveryCommand,
)
from arclayer.domain.reward import RewardWeights


def event_from_in(e: C.FaultEventIn) -> FaultEvent:
    return FaultEvent(
        run_id=e.run_id,
        task_id=e.task_id,
        step_index=e.step_index,
        step_total_estimate=e.step_total_estimate,
        occurred_at=e.occurred_at,
        active_agent=e.active_agent,
        agent_role=e.agent_role,
        orchestration=D.OrchestrationPattern(e.orchestration.value),
        fault_class=D.FaultClass(e.fault_class.value) if e.fault_class else None,
        fault_confidence=e.fault_confidence,
        label_source=D.LabelSource(e.label_source.value),
        fault_description=e.fault_description,
        last_messages_summary=e.last_messages_summary,
        checkpoint_id=e.checkpoint_id,
        checkpoint_restorable=e.checkpoint_restorable,
        step_repeatable=e.step_repeatable,
        orchestrator_accessible=e.orchestrator_accessible,
        available_artifacts=tuple(e.available_artifacts),
        tool_name=e.tool_name,
        tool_error_code=e.tool_error_code,
        tool_duration_ms=e.tool_duration_ms,
        budget_remaining_cost=e.budget_remaining_cost,
        budget_remaining_tokens=e.budget_remaining_tokens,
        time_remaining_ms=e.time_remaining_ms,
        prior_incidents_in_task=e.prior_incidents_in_task,
        host_id=e.host_id,
        policy_instance_id=e.policy_instance_id,
        host_capabilities=tuple(e.host_capabilities),
    )


def candidate_from_spec(s: C.CandidateSpec) -> Candidate:
    return Candidate(
        candidate_id=s.candidate_id,
        version=s.version,
        description=s.description,
        capabilities=tuple(s.capabilities),
        supported_classes=None if s.supported_classes == "*" else tuple(D.FaultClass(c.value) for c in s.supported_classes),
        required_preconditions=tuple(D.Precondition(p.value) for p in s.required_preconditions),
        optional_preconditions=tuple(D.Precondition(p.value) for p in s.optional_preconditions),
        required_host_capabilities=tuple(s.required_host_capabilities),
        max_cost=s.max_cost,
        max_latency_ms=s.max_latency_ms,
        permissions=tuple(s.permissions),
        verifier_id=s.verifier_id,
        enabled=s.enabled,
    )


def candidate_to_spec(c: Candidate) -> C.CandidateSpec:
    return C.CandidateSpec(
        candidate_id=c.candidate_id,
        version=c.version,
        description=c.description,
        capabilities=list(c.capabilities),
        supported_classes="*" if c.supported_classes is None else [C.FaultClass(x.value) for x in c.supported_classes],
        required_preconditions=[C.Precondition(p.value) for p in c.required_preconditions],
        optional_preconditions=[C.Precondition(p.value) for p in c.optional_preconditions],
        required_host_capabilities=list(c.required_host_capabilities),
        max_cost=c.max_cost,
        max_latency_ms=c.max_latency_ms,
        permissions=list(c.permissions),
        verifier_id=c.verifier_id,
        enabled=c.enabled,
    )


def command_to_out(cmd: RecoveryCommand) -> C.RecoveryCommandOut:
    return C.RecoveryCommandOut(
        incident_id=cmd.incident_id,
        action=C.Action(cmd.action.value),
        candidate_id=cmd.candidate_id,
        parameters=dict(cmd.parameters),
        verification_conditions=list(cmd.verification_conditions),
        scores=[C.ScoreOut(candidate_id=s.candidate_id, estimate=s.estimate, bonus=s.bonus, score=s.score) for s in cmd.scores],
        excluded=[C.GateRejectionOut(candidate_id=r.candidate_id, code=r.code.value) for r in cmd.excluded],
        reason=cmd.reason,
        deadline_ms=cmd.deadline_ms,
    )


def result_from_in(r: C.ExecutionResultIn) -> ExecutionResult:
    return ExecutionResult(
        incident_id=r.incident_id,
        candidate_id=r.candidate_id,
        terminal=D.Terminal(r.terminal.value),
        final_answer=r.final_answer,
        cost_used=r.cost_used,
        tokens_used=r.tokens_used,
        latency_ms=r.latency_ms,
        actions_performed=tuple(r.actions_performed),
        artifacts=dict(r.artifacts),
    )


def ack_to_out(a: OutcomeAck) -> C.OutcomeAckOut:
    return C.OutcomeAckOut(incident_id=a.incident_id, status=a.status, reward=a.reward, policy_updated=a.policy_updated)


def create_policy_cmd(p: C.CreatePolicyIn) -> CreatePolicyCommand:
    return CreatePolicyCommand(
        kind=D.PolicyKind(p.kind.value),
        seed=p.seed,
        alpha=p.alpha,
        lam=p.lam,
        feature_spec=FeatureSpec(step_cap=p.feature_spec.step_cap, budget_task_cap=p.feature_spec.budget_task_cap, n_max=p.feature_spec.n_max),
        gate_config=GateConfig(allowed_permissions=frozenset(p.allowed_permissions), n_max=p.n_max),
        reward_weights=RewardWeights(s=p.reward_weights.s, c=p.reward_weights.c, l=p.reward_weights.l, v=p.reward_weights.v),
        caps=BudgetCaps(
            incident_cost_cap=p.caps.incident_cost_cap,
            incident_latency_cap_ms=p.caps.incident_latency_cap_ms,
            task_cost_cap=p.caps.task_cost_cap,
        ),
        strict_sequential=p.strict_sequential,
        retry_candidate_id=p.retry_candidate_id,
        static_map={D.FaultClass(k.value): tuple(v) for k, v in p.static_map.items()},
        static_default=tuple(p.static_default),
        policy_id=p.policy_id,
        init_state=p.init_state,
        experiment_id=p.experiment_id,
    )


def policy_to_out(p: PolicyInstance) -> C.PolicyOut:
    n: dict[str, int] = dict((p.selector_state or {}).get("n", {}))
    return C.PolicyOut(
        policy_id=p.policy_id,
        kind=C.PolicyKind(p.kind.value),
        seed=p.seed,
        alpha=p.alpha,
        lam=p.lam,
        variant=p.variant.value,
        feature_hash=p.feature_hash,
        embedding_model_id=p.embedding_model_id,
        candidate_ids=[c.candidate_id for c in p.candidates],
        frozen=p.frozen,
        strict_sequential=p.strict_sequential,
        pending_incident_id=p.pending_incident_id,
        experiment_id=p.experiment_id,
        n_updates=n,
    )


def snapshot_to_out(s: dict[str, Any]) -> C.PolicySnapshotOut:
    return C.PolicySnapshotOut(**s)


def incident_to_out(i: Incident) -> C.IncidentOut:
    v = i.verification
    return C.IncidentOut(
        incident_id=i.incident_id,
        policy_id=i.policy_id,
        task_id=i.event.task_id,
        status=i.status.value,
        action=C.Action(i.command.action.value) if i.command else None,
        chosen=i.command.candidate_id if i.command else None,
        eligible=[a.candidate_id for a in i.arms],
        reward=i.reward,
        verification=C.VerificationOut(S=v.S, C=v.C, L=v.L, V=v.V) if v else None,
    )

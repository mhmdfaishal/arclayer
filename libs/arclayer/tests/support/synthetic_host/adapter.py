"""HostAdapter sintetis: menerjemahkan insiden dunia sintetis ke FaultEventIn dan
menyediakan enam executor yang hasilnya ditentukan model tersembunyi."""

from __future__ import annotations

from typing import Any, Mapping

import arclayer.contracts as C
from tests.support.synthetic_host.candidates import synthetic_candidates
from tests.support.synthetic_host.world import SyntheticIncident, SyntheticWorld

HOST_CAPABILITIES = ["retry_step", "repair_tool", "replan", "resend_handoff", "review_answer", "rollback"]


class SyntheticExecutor:
    def __init__(self, world: SyntheticWorld, spec: C.CandidateSpec) -> None:
        self.world = world
        self.spec = spec
        self.candidate_id = spec.candidate_id

    def execute(self, command: C.RecoveryCommandOut, native_context: Any) -> C.ExecutionResultIn:
        inc: SyntheticIncident = native_context
        d = self.world.draw(inc, self.candidate_id)
        return C.ExecutionResultIn(
            incident_id=command.incident_id,
            candidate_id=self.candidate_id,
            terminal=C.Terminal.TASK_COMPLETED,
            final_answer="PASS" if d.success else "FAIL",
            cost_used=d.cost,
            tokens_used=0,
            latency_ms=d.latency_ms,
            # Hanya aksi yang diizinkan: host sintetis tidak pernah memicu V=1.
            actions_performed=list(self.spec.permissions),
        )


class SyntheticHostAdapter:
    host_id = "synthetic-host"

    def __init__(self, world: SyntheticWorld) -> None:
        self.world = world
        self.capabilities = list(HOST_CAPABILITIES)
        self._executors = {s.candidate_id: SyntheticExecutor(world, s) for s in synthetic_candidates()}

    def to_fault_event(self, native_fault: SyntheticIncident, policy_instance_id: str) -> C.FaultEventIn:
        i = native_fault
        return C.FaultEventIn(
            run_id=f"synthetic-{self.world.seed}",
            task_id=i.task_id,
            step_index=i.step_index,
            step_total_estimate=i.step_total_estimate,
            occurred_at=i.occurred_at,
            active_agent="synthetic_agent",
            agent_role="worker",
            orchestration=C.OrchestrationPattern(i.orchestration.value),
            fault_class=C.FaultClass(i.fault_class.value),
            label_source=C.LabelSource.INJECTOR,
            fault_description=i.fault_description,
            last_messages_summary=i.last_messages_summary,
            checkpoint_id=i.checkpoint_id,
            checkpoint_restorable=i.checkpoint_restorable,
            step_repeatable=i.step_repeatable,
            orchestrator_accessible=i.orchestrator_accessible,
            available_artifacts=list(i.available_artifacts),
            tool_name=i.tool_name,
            tool_error_code=i.tool_error_code,
            tool_duration_ms=i.tool_duration_ms,
            budget_remaining_cost=i.budget_remaining_cost,
            time_remaining_ms=i.time_remaining_ms,
            prior_incidents_in_task=0,
            host_id=self.host_id,
            policy_instance_id=policy_instance_id,
            host_capabilities=list(self.capabilities),
        )

    def executors(self) -> Mapping[str, SyntheticExecutor]:
        return self._executors

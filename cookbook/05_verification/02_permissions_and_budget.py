"""Violations cancel success.

ArcLayer computes S (success), C (cost), L (latency) and V (violation) itself from what the host
reports, so a host cannot shape its own reward. Doing something outside the candidate's
`permissions`, or spending more than its `max_cost`, sets V to 1 and wipes out the credit for
succeeding. The executor must report `actions_performed` truthfully.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/05_verification/02_permissions_and_budget.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

BEHAVIOURS = {
    "honest": dict(actions=["rerun_step"], cost=0.05),
    "outside its permissions": dict(actions=["rerun_step", "delete_files"], cost=0.05),
    "above its max_cost": dict(actions=["rerun_step"], cost=0.5),  # max_cost is 0.2
}


class Retry:
    candidate_id = "retry"

    def execute(self, command, fault):
        behaviour = BEHAVIOURS[fault["behaviour"]]
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id="retry", terminal=Terminal.TASK_COMPLETED,
            cost_used=behaviour["cost"], tokens_used=0, latency_ms=100, actions_performed=behaviour["actions"],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = ["retry_step"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["behaviour"], step_index=1, occurred_at=datetime.now(timezone.utc),
            active_agent="researcher", agent_role="worker", orchestration="sequential",
            fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"retry": Retry()}


layer = ArcLayer(None, candidates=[CandidateSpec(
    candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
    supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["rerun_step"], verifier_id="task_completed",
)])
policy_id = layer.create_policy("P", seed=1)

print(f"{'the executor acted':<26}{'S':>3}{'C':>7}{'L':>8}{'V':>3}   reward")
for name in BEHAVIOURS:
    outcome = layer.handle_fault({"behaviour": name}, Adapter(), policy_id)
    v = layer.incident(outcome.command.incident_id).verification
    print(f"{name:<26}{v.S:>3}{v.C:>7.3f}{v.L:>8.4f}{v.V:>3}   {outcome.ack.reward:7.3f}")

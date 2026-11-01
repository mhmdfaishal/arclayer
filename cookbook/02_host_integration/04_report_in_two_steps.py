"""Reporting in two steps.

When the recovery runs somewhere else, or later, call `post_incident` now and `post_result` when it
finishes. The idempotency key makes a repeated report safe: the same key and payload return the
stored acknowledgement, and a different payload under the same key is rejected.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/02_host_integration/04_report_in_two_steps.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer, Conflict
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

layer = ArcLayer(None, candidates=[CandidateSpec(
    candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
    supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["rerun_step"], verifier_id="task_completed",
)])
policy_id = layer.create_policy("P", seed=1)

# Step 1: the fault happens, ArcLayer decides.
command = layer.post_incident(FaultEventIn(
    run_id="run-1", task_id="task-1", step_index=1, occurred_at=datetime.now(timezone.utc),
    active_agent="researcher", agent_role="worker", orchestration="sequential", fault_class="tool_failure",
    label_source="deterministic", fault_description="tool timeout", budget_remaining_cost=2.0,
    time_remaining_ms=120_000, prior_incidents_in_task=0, host_id="cookbook", policy_instance_id=policy_id,
    host_capabilities=["retry_step"],
))
print("decided:", command.action.value, command.candidate_id)
print("incident status:", layer.incident(command.incident_id).status)

# ... your host runs the recovery elsewhere, then reports what happened.
result = ExecutionResultIn(
    incident_id=command.incident_id, candidate_id=command.candidate_id, terminal=Terminal.TASK_COMPLETED,
    cost_used=0.05, tokens_used=0, latency_ms=300, actions_performed=["rerun_step"],
)
ack = layer.post_result(result, idempotency_key="incident-1-attempt-1")
print("reported:", ack.status, "| policy updated:", ack.policy_updated)

# Step 2 repeated, for example after a timeout on your side: the same answer, no second update.
again = layer.post_result(result, idempotency_key="incident-1-attempt-1")
print("same report again returns the same acknowledgement:", again == ack)
print("policy updates after the repeat:", layer.get_policy(policy_id).n_updates)

try:
    layer.post_result(result.model_copy(update={"final_answer": "other"}), idempotency_key="incident-1-attempt-1")
except Conflict:
    print("a different payload under the same key: Conflict")

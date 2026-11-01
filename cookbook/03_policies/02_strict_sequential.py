"""Overlapping incidents and strict mode.

By default a policy accepts a new incident while an earlier one is still waiting for its result, so
agents running in parallel can share it. `strict_sequential=True` refuses instead (PolicyBusy), which
experiments use to keep runs reproducible.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/03_policies/02_strict_sequential.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer, PolicyBusy
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

layer = ArcLayer(None, candidates=[CandidateSpec(
    candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
    supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["rerun_step"], verifier_id="task_completed",
)])


def event(task_id, policy_id):
    return FaultEventIn(
        run_id="run-1", task_id=task_id, step_index=1, occurred_at=datetime.now(timezone.utc),
        active_agent="researcher", agent_role="worker", orchestration="concurrent",
        fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
        budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
        host_id="cookbook", policy_instance_id=policy_id, host_capabilities=["retry_step"],
    )


def done(command):
    return ExecutionResultIn(
        incident_id=command.incident_id, candidate_id=command.candidate_id, terminal=Terminal.TASK_COMPLETED,
        cost_used=0.05, tokens_used=0, latency_ms=100, actions_performed=["rerun_step"],
    )


open_policy = layer.create_policy("P", seed=1)  # strict_sequential=False is the default
first = layer.post_incident(event("task-1", open_policy))
second = layer.post_incident(event("task-2", open_policy))  # task-1 has not reported yet
print("default policy: two incidents in flight ->", first.action.value, second.action.value)

strict = layer.create_policy("P", seed=2, strict_sequential=True)
waiting = layer.post_incident(event("task-1", strict))
try:
    layer.post_incident(event("task-2", strict))
except PolicyBusy:
    print("strict policy: the second incident is refused (PolicyBusy)")
layer.post_result(done(waiting), idempotency_key="k1")
layer.post_incident(event("task-2", strict))
print("strict policy: accepted once the first result was reported")

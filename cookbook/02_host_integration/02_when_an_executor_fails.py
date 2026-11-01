"""When recovery itself goes wrong.

Three things can go wrong on the host side, and ArcLayer treats each one differently:
1. the executor raises: it is reported as executor_error, scored, and the policy learns from it;
2. the host has no executor for the chosen candidate: HostMisconfigured, nothing is reported,
   because a wiring mistake is not the candidate's fault;
3. a result never arrives: the incident waits, and censoring closes it without teaching the policy.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/02_host_integration/02_when_an_executor_fails.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer, HostMisconfigured
from arclayer.contracts import CandidateSpec, FaultEventIn


class Boom:
    candidate_id = "retry"

    def execute(self, command, fault):
        raise RuntimeError("the rerun crashed")


class Adapter:
    host_id = "cookbook"
    capabilities = ["retry_step"]

    def __init__(self, executors):
        self._executors = executors

    def to_fault_event(self, fault, policy_instance_id):
        return event(fault["task"], policy_instance_id)

    def executors(self):
        return self._executors


def event(task_id, policy_id):
    return FaultEventIn(
        run_id="run-1", task_id=task_id, step_index=1, occurred_at=datetime.now(timezone.utc),
        active_agent="researcher", agent_role="worker", orchestration="sequential",
        fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
        budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
        host_id="cookbook", policy_instance_id=policy_id, host_capabilities=["retry_step"],
    )


layer = ArcLayer(None, candidates=[CandidateSpec(
    candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
    supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
    permissions=["rerun_step"], verifier_id="task_completed",
)])
policy_id = layer.create_policy("P", seed=1)

print("1. the executor raises")
outcome = layer.handle_fault({"task": "task-1"}, Adapter({"retry": Boom()}), policy_id)
print("   reported terminal:", outcome.result.terminal.value, "| reward:", outcome.ack.reward)
print("   policy updates:", layer.get_policy(policy_id).n_updates)

print("2. the host has no executor for the chosen candidate")
try:
    layer.handle_fault({"task": "task-2"}, Adapter({}), policy_id)
except HostMisconfigured:
    print("   HostMisconfigured raised, nothing reported")
print("   policy updates:", layer.get_policy(policy_id).n_updates)
stranded = layer.censor_expired(ttl_s=0)  # the decision was made, so the incident is still waiting
print("   the incident left waiting is closed by censoring:", len(stranded))

print("3. a result never arrives")
layer.post_incident(event("task-3", policy_id))  # decided, and then the host dies
closed = layer.censor_expired(ttl_s=0)
print("   incidents closed by censoring:", len(closed), "| status:", layer.incident(closed[0]).status)
print("   policy updates:", layer.get_policy(policy_id).n_updates)

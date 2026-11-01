"""Hello, recovery.

The smallest complete integration: one recovery candidate (retry), a host that fakes a fault, and
one call to ArcLayer. ArcLayer decides, your executor acts, ArcLayer scores the result.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/00_quickstart/01_hello_recovery.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

# What ArcLayer may choose from. One CandidateSpec per recovery your host knows how to run.
retry = CandidateSpec(
    candidate_id="retry",
    version="1",
    description="Run the failed step again on the same agent",
    capabilities=["retry_step"],
    supported_classes="*",
    required_preconditions=["STEP_REPEATABLE"],
    required_host_capabilities=["retry_step"],
    max_cost=0.2,
    max_latency_ms=60_000,
    permissions=["rerun_step"],
    verifier_id="task_completed",
)


class RetryExecutor:
    """Runs the recovery inside your process. ArcLayer only says when."""

    candidate_id = "retry"

    def execute(self, command, fault):
        recovered = fault["rerun"]()  # your framework's own retry logic
        return ExecutionResultIn(
            incident_id=command.incident_id,
            candidate_id=self.candidate_id,
            terminal=Terminal.TASK_COMPLETED if recovered else Terminal.NEW_INCIDENT,
            cost_used=0.05,
            tokens_used=800,
            latency_ms=300,
            actions_performed=["rerun_step"],
        )


class MyAdapter:
    """Translates a fault from your host into the contract ArcLayer understands."""

    host_id = "cookbook"
    capabilities = ["retry_step"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1",
            task_id=fault["task"],
            step_index=3,
            occurred_at=datetime.now(timezone.utc),
            active_agent="researcher",
            agent_role="worker",
            orchestration="sequential",
            fault_class="tool_failure",
            label_source="deterministic",
            fault_description=fault["error"],
            budget_remaining_cost=2.0,
            time_remaining_ms=120_000,
            prior_incidents_in_task=0,
            host_id=self.host_id,
            policy_instance_id=policy_instance_id,
            host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"retry": RetryExecutor()}


layer = ArcLayer(None, candidates=[retry])  # None keeps everything in memory
policy_id = layer.create_policy("P", seed=1)

fault = {"task": "task-1", "error": "tool timeout", "rerun": lambda: True}
outcome = layer.handle_fault(fault, MyAdapter(), policy_id)

print("action:", outcome.command.action.value)
print("candidate:", outcome.command.candidate_id)
print("status:", outcome.ack.status)
print("reward:", outcome.ack.reward)

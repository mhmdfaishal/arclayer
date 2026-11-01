"""Scoring an answer against ground truth.

With `verifier_id="benchmark_task_pass"`, success means the host's final answer matches the ground
truth that ArcLayer holds. The truth never leaves ArcLayer: it is not in the command the host
receives, and it is not in any object the host can read back.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/05_verification/01_ground_truth.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

TRUTH = {"task-right": "the-answer-is-forty-two", "task-wrong": "the-answer-is-seven"}


class Retry:
    candidate_id = "retry"

    def execute(self, command, fault):
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id="retry", terminal=Terminal.TASK_COMPLETED,
            final_answer=fault["answer"], cost_used=0.05, tokens_used=0, latency_ms=100,
            actions_performed=["rerun_step"],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = ["retry_step"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["task"], step_index=1, occurred_at=datetime.now(timezone.utc),
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
    permissions=["rerun_step"], verifier_id="benchmark_task_pass",
)])
for task_id, answer in TRUTH.items():
    layer.register_ground_truth(task_id, answer)
policy_id = layer.create_policy("P", seed=1)

for task_id, host_answer in [("task-right", "the-answer-is-forty-two"), ("task-wrong", "a wrong answer")]:
    outcome = layer.handle_fault({"task": task_id, "answer": host_answer}, Adapter(), policy_id)
    shown = [outcome.command, outcome.ack, layer.incident(outcome.command.incident_id), layer.get_policy(policy_id)]
    leaked = any(truth in item.model_dump_json() for item in shown for truth in TRUTH.values())
    print(f"{task_id}: status={outcome.ack.status:<9} reward={outcome.ack.reward:6.3f}   truth visible to the host: {leaked}")

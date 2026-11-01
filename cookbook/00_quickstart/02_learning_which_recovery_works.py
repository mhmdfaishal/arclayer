"""Learning which recovery works.

The host has two recoveries: retry, which never helps because the tool stays down, and use_backup,
which always works. ArcLayer starts without knowing that and learns from the outcome of every fault.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/00_quickstart/02_learning_which_recovery_works.py
"""

from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

DESCRIPTIONS = {"retry": "Run the failed step again", "use_backup": "Use the backup tool instead"}


def candidate(candidate_id):
    return CandidateSpec(
        candidate_id=candidate_id, version="1", description=DESCRIPTIONS[candidate_id],
        capabilities=[candidate_id], supported_classes="*", required_host_capabilities=[candidate_id],
        max_cost=0.2, max_latency_ms=60_000, permissions=[candidate_id], verifier_id="task_completed",
    )


class Executor:
    def __init__(self, candidate_id, works):
        self.candidate_id, self.works = candidate_id, works

    def execute(self, command, fault):
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id,
            terminal=Terminal.TASK_COMPLETED if self.works else Terminal.NEW_INCIDENT,
            cost_used=0.05, tokens_used=0, latency_ms=100, actions_performed=[self.candidate_id],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = ["retry", "use_backup"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["task"], step_index=1, occurred_at=datetime.now(timezone.utc),
            active_agent="researcher", agent_role="worker", orchestration="sequential",
            fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"retry": Executor("retry", works=False), "use_backup": Executor("use_backup", works=True)}


layer = ArcLayer(None, candidates=[candidate("retry"), candidate("use_backup")])
policy_id = layer.create_policy("P", seed=1)

for i in range(10):
    outcome = layer.handle_fault({"task": f"task-{i}"}, Adapter(), policy_id)
    print(f"fault {i}: ran {outcome.command.candidate_id:<10} -> {outcome.ack.status}")

print("times each recovery ran:", layer.snapshot_policy(policy_id).selector_state["n"])

"""Persisting what was learned.

With a SQLite file, a policy survives a restart: a new ArcLayer opened on the same file finds the
same learned state and keeps going. Pass an absolute path in real use, because a relative one
depends on the folder you start from.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/04_persistence/01_persist_and_resume.py
"""

import tempfile
from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

WORKS = {"retry": False, "use_backup": True}


def candidate(candidate_id):
    return CandidateSpec(
        candidate_id=candidate_id, version="1", description=f"Recovery {candidate_id}",
        capabilities=[candidate_id], supported_classes="*", required_host_capabilities=[candidate_id],
        max_cost=0.2, max_latency_ms=60_000, permissions=[candidate_id], verifier_id="task_completed",
    )


class Executor:
    def __init__(self, candidate_id):
        self.candidate_id = candidate_id

    def execute(self, command, fault):
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id,
            terminal=Terminal.TASK_COMPLETED if WORKS[self.candidate_id] else Terminal.NEW_INCIDENT,
            cost_used=0.05, tokens_used=0, latency_ms=100, actions_performed=[self.candidate_id],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = list(WORKS)

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["task"], step_index=1, occurred_at=datetime.now(timezone.utc),
            active_agent="researcher", agent_role="worker", orchestration="sequential",
            fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {name: Executor(name) for name in WORKS}


with tempfile.TemporaryDirectory() as folder:
    database = f"sqlite:///{folder}/arclayer.db"

    layer = ArcLayer(database, candidates=[candidate(name) for name in WORKS])
    policy_id = layer.create_policy("P", seed=1)
    for i in range(20):
        layer.handle_fault({"task": f"task-{i}"}, Adapter(), policy_id)
    learned = layer.snapshot_policy(policy_id).selector_state
    print("times each recovery ran:", learned["n"])

    restarted = ArcLayer(database)  # what a new process does: open the same file
    print("same learned state after reopening:", restarted.snapshot_policy(policy_id).selector_state == learned)

    restarted.handle_fault({"task": "after-restart"}, Adapter(), policy_id)
    print("keeps learning:", restarted.snapshot_policy(policy_id).selector_state["n"])

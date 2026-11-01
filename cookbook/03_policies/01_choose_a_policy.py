"""Choosing a policy.

The same stream of faults is handled by five policies. B0 never recovers, B1 always retries, B2
follows a fixed table from fault class to recovery, B3 picks at random, and P (LinUCB) learns from
outcomes. Here retry never works, use_backup fixes tool failures and replan fixes plan errors.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/03_policies/01_choose_a_policy.py
"""

import random
from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

FIXES = {"tool_failure": "use_backup", "plan_error": "replan"}  # the recovery that works for each class
SUITS = {"retry": "*", "use_backup": ["tool_failure", "timeout"], "replan": ["plan_error"]}


def candidate(candidate_id):
    return CandidateSpec(
        candidate_id=candidate_id, version="1", description=f"Recovery {candidate_id}",
        capabilities=[candidate_id], supported_classes=SUITS[candidate_id], required_host_capabilities=[candidate_id],
        max_cost=0.2, max_latency_ms=60_000, permissions=[candidate_id], verifier_id="task_completed",
    )


class Executor:
    def __init__(self, candidate_id):
        self.candidate_id = candidate_id

    def execute(self, command, fault):
        works = FIXES[fault["class"]] == self.candidate_id
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id=self.candidate_id,
            terminal=Terminal.TASK_COMPLETED if works else Terminal.NEW_INCIDENT,
            cost_used=0.05, tokens_used=0, latency_ms=100, actions_performed=[self.candidate_id],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = list(SUITS)

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["task"], step_index=1, occurred_at=datetime.now(timezone.utc),
            active_agent="researcher", agent_role="worker", orchestration="sequential",
            fault_class=fault["class"], label_source="deterministic", fault_description=fault["class"],
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {name: Executor(name) for name in SUITS}


random.seed(7)
faults = [{"task": f"task-{i}", "class": random.choice(list(FIXES))} for i in range(200)]
static_table = {fault_class: [fix] for fault_class, fix in FIXES.items()}  # what B2 follows

for kind, options in [("B0", {}), ("B1", {}), ("B2", {"static_map": static_table}), ("B3", {}), ("P", {})]:
    layer = ArcLayer(None, candidates=[candidate(name) for name in SUITS])
    policy_id = layer.create_policy(kind, seed=1, **options)
    rewards, recovered = [], 0
    for fault in faults:
        outcome = layer.handle_fault(fault, Adapter(), policy_id)
        rewards.append(outcome.ack.reward if outcome.ack else 0.0)
        recovered += bool(outcome.ack and outcome.ack.status == "recovered")
    print(f"{kind}: mean reward {sum(rewards) / len(rewards):6.3f}   recovered {recovered}/{len(faults)}")

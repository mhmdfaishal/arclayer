"""Warm start and freeze.

Learn on one stream of faults (calibration), take a snapshot of what the policy learned, and start a
new policy from it. The warm policy begins where the calibration ended; a cold one starts from
nothing. A frozen policy keeps deciding but stops learning.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/03_policies/03_warm_start_and_freeze.py
"""

import random
from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal

FIXES = {"tool_failure": "use_backup", "plan_error": "replan"}
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


def stream(prefix, count, seed):
    rng = random.Random(seed)
    return [{"task": f"{prefix}-{i}", "class": rng.choice(list(FIXES))} for i in range(count)]


def run(layer, policy_id, faults):
    rewards = [layer.handle_fault(f, Adapter(), policy_id).ack.reward for f in faults]
    return sum(rewards) / len(rewards)


layer = ArcLayer(None, candidates=[candidate(name) for name in SUITS])

calibration = layer.create_policy("P", seed=1)
run(layer, calibration, stream("calibration", 150, seed=1))
learned = layer.snapshot_policy(calibration).selector_state  # the learned state: A, b and counts per candidate

evaluation = stream("evaluation", 100, seed=2)
cold = layer.create_policy("P", seed=3)
warm = layer.create_policy("P", seed=3, init_state=learned)  # same candidates as the registry, or ValueError
print(f"cold start: mean reward {run(layer, cold, evaluation):.3f}")
print(f"warm start: mean reward {run(layer, warm, evaluation):.3f}")

layer.freeze_policy(warm)
outcome = layer.handle_fault({"task": "after-freeze", "class": "plan_error"}, Adapter(), warm)
print("frozen policy still decides:", outcome.command.candidate_id, "| policy updated:", outcome.ack.policy_updated)

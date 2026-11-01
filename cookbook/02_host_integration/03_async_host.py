"""An async host.

Several tasks hit a fault at the same time and share one policy. `handle_fault_async` runs the loop
in a worker thread, so the event loop is never blocked, and policies accept overlapping incidents
by default.

Run from the repository root:
    PYTHONPATH=libs/arclayer python cookbook/02_host_integration/03_async_host.py
"""

import asyncio
import time
from datetime import datetime, timezone

from arclayer import ArcLayer
from arclayer.contracts import CandidateSpec, ExecutionResultIn, FaultEventIn, Terminal


class Retry:
    candidate_id = "retry"

    def execute(self, command, fault):
        time.sleep(0.05)  # stands in for real recovery work
        return ExecutionResultIn(
            incident_id=command.incident_id, candidate_id="retry", terminal=Terminal.TASK_COMPLETED,
            cost_used=0.05, tokens_used=0, latency_ms=50, actions_performed=["rerun_step"],
        )


class Adapter:
    host_id = "cookbook"
    capabilities = ["retry_step"]

    def to_fault_event(self, fault, policy_instance_id):
        return FaultEventIn(
            run_id="run-1", task_id=fault["task"], step_index=1, occurred_at=datetime.now(timezone.utc),
            active_agent="researcher", agent_role="worker", orchestration="concurrent",
            fault_class="tool_failure", label_source="deterministic", fault_description="tool timeout",
            budget_remaining_cost=2.0, time_remaining_ms=120_000, prior_incidents_in_task=0,
            host_id=self.host_id, policy_instance_id=policy_instance_id, host_capabilities=self.capabilities,
        )

    def executors(self):
        return {"retry": Retry()}


async def main():
    layer = ArcLayer(None, candidates=[CandidateSpec(
        candidate_id="retry", version="1", description="Run the failed step again", capabilities=["retry_step"],
        supported_classes="*", required_host_capabilities=["retry_step"], max_cost=0.2, max_latency_ms=60_000,
        permissions=["rerun_step"], verifier_id="task_completed",
    )])
    policy_id = layer.create_policy("P", seed=1)
    adapter = Adapter()

    outcomes = await asyncio.gather(
        *(layer.handle_fault_async({"task": f"task-{i}"}, adapter, policy_id) for i in range(6))
    )

    print("statuses:", [outcome.ack.status for outcome in outcomes])
    print("policy updates:", layer.get_policy(policy_id).n_updates)


asyncio.run(main())
